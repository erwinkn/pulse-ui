from __future__ import annotations

import contextlib
import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from io import TextIOBase
from selectors import EVENT_READ, BaseSelector, DefaultSelector
from typing import TypeVar, cast

from pulse.cli.helpers import os_family
from pulse.cli.logging import TagMode
from pulse.cli.models import CommandSpec

_K = TypeVar("_K", int, str)

# ANSI color codes for tagged output
ANSI_CODES = {
	"cyan": "\033[36m",
	"orange1": "\033[38;5;208m",
	"reset": "\033[0m",
}

# Tag colors mapping (used only in colored mode)
TAG_COLORS = {"server": "cyan", "web": "orange1"}

# Regex to strip ANSI escape codes
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Strip terminal controls while preserving SGR formatting (CSI ... m).
# Covers CSI (except SGR), OSC/DCS/SOS/PM/APC strings including their payloads
# (e.g. terminal-title updates ending in BEL or ST), and two-byte escapes.
ANSI_TERMINAL_CONTROL = re.compile(
	r"\x1B(?:\[[0-?]*[ -/]*(?:[@-l]|[n-~])"
	+ r"|\][^\x07\x1B]*(?:\x07|\x1B\\)?"
	+ r"|[PX^_][^\x1B]*(?:\x1B\\)?"
	+ r"|(?!\[)[ -/]*[0-~])"
)


def execute_commands(
	commands: Sequence[CommandSpec],
	*,
	tag_mode: TagMode = "colored",
) -> int:
	"""Run the provided commands, streaming tagged output to stdout.

	Args:
		commands: List of command specifications to run
		tag_mode: How to display process tags:
			- "colored": Show [server]/[web] with ANSI colors (dev mode)
			- "plain": Show [server]/[web] without colors (ci/prod mode)
	"""
	if not commands:
		return 0

	def interrupt_on_sigterm(_signum: int, _frame: object) -> None:
		raise KeyboardInterrupt

	# Children run in their own sessions, so a SIGTERM aimed at this CLI never
	# reaches them; convert it to KeyboardInterrupt so the graceful teardown
	# below runs instead of leaving orphans holding the ports.
	previous_sigterm = signal.signal(signal.SIGTERM, interrupt_on_sigterm)
	try:
		# Avoid pty.fork() in multi-threaded environments (like pytest) to prevent
		# "DeprecationWarning: This process is multi-threaded, use of forkpty() may lead to deadlocks"
		# Also skip pty on Windows or if fork is unavailable
		in_pytest = "pytest" in sys.modules
		if os_family() == "windows" or not hasattr(pty, "fork") or in_pytest:
			return _run_without_pty(commands, tag_mode=tag_mode)

		return _run_with_pty(commands, tag_mode=tag_mode)
	finally:
		signal.signal(signal.SIGTERM, previous_sigterm)


def _call_on_spawn(spec: CommandSpec) -> None:
	"""Call the on_spawn callback if it exists."""
	if spec.on_spawn:
		try:
			spec.on_spawn()
		except Exception:
			pass


def _check_on_ready(
	spec: CommandSpec,
	line: str,
	ready_flags: dict[_K, bool],
	key: _K,
) -> None:
	"""Check if line matches ready_pattern and call on_ready if needed."""
	if spec.ready_pattern and not ready_flags[key]:
		if _matches_ready(spec, line):
			ready_flags[key] = True
			if spec.on_ready:
				try:
					spec.on_ready()
				except Exception:
					pass


def _matches_ready(spec: CommandSpec, line: str) -> bool:
	return bool(
		spec.ready_pattern and re.search(spec.ready_pattern, ANSI_ESCAPE.sub("", line))
	)


def _run_with_pty(
	commands: Sequence[CommandSpec],
	*,
	tag_mode: TagMode,
) -> int:
	procs: list[tuple[str, int, int]] = []
	completed_codes: list[int] = []
	fd_to_spec: dict[int, CommandSpec] = {}
	buffers: dict[int, bytearray] = {}
	ready_flags: dict[int, bool] = {}

	try:
		for spec in commands:
			pid, fd = pty.fork()
			if pid == 0:
				if spec.cwd:
					os.chdir(spec.cwd)
				os.execvpe(spec.args[0], spec.args, spec.env)
			else:
				fcntl = __import__("fcntl")
				fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)
				procs.append((spec.name, pid, fd))
				fd_to_spec[fd] = spec
				buffers[fd] = bytearray()
				ready_flags[fd] = False
				_call_on_spawn(spec)

		while procs:
			for tag, pid, fd in list(procs):
				try:
					wpid, status = os.waitpid(pid, os.WNOHANG)
					if wpid == pid:
						_signal_process_tree(pid, signal.SIGKILL)
						procs.remove((tag, pid, fd))
						completed_codes.append(
							os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1
						)
						_close_fd(fd)
				except ChildProcessError:
					procs.remove((tag, pid, fd))
					completed_codes.append(1)
					_close_fd(fd)

			if completed_codes or not procs:
				break

			if not _pump_pty_output(
				procs, fd_to_spec, buffers, ready_flags, tag_mode, timeout=0.1
			):
				break

		return max(completed_codes) if completed_codes else 0

	except KeyboardInterrupt:
		sys.stdout.write("\nShutting down...\n")
		sys.stdout.flush()
		for _tag, pid, _fd in procs:
			with contextlib.suppress(Exception):
				_signal_process_tree(pid, signal.SIGTERM)
		deadline = time.monotonic() + 4
		with contextlib.suppress(KeyboardInterrupt):
			while procs and time.monotonic() < deadline:
				# Keep draining the pty while waiting: a child blocked writing to
				# a full buffer can never exit, and its final logs would be lost.
				_pump_pty_output(
					procs, fd_to_spec, buffers, ready_flags, tag_mode, timeout=0.05
				)
				for proc_info in list(procs):
					_tag, pid, fd = proc_info
					with contextlib.suppress(ChildProcessError):
						waited, _status = os.waitpid(pid, os.WNOHANG)
						if waited == pid:
							procs.remove(proc_info)
							_close_fd(fd)
		return 130
	finally:
		for _tag, pid, fd in procs:
			try:
				_signal_process_tree(pid, signal.SIGKILL)
			except Exception:
				pass
			_close_fd(fd)


def _pump_pty_output(
	procs: list[tuple[str, int, int]],
	fd_to_spec: dict[int, CommandSpec],
	buffers: dict[int, bytearray],
	ready_flags: dict[int, bool],
	tag_mode: TagMode,
	*,
	timeout: float,
) -> bool:
	"""Read and print available child output; False when select is unusable."""
	readable = [fd for _, _, fd in procs]
	try:
		ready, _, _ = select.select(readable, [], [], timeout)
	except (OSError, ValueError):
		return False

	for fd in ready:
		try:
			data = os.read(fd, 4096)
		except OSError:
			continue
		if not data:
			continue
		buffers[fd].extend(data)
		while b"\n" in buffers[fd]:
			line, remainder = buffers[fd].split(b"\n", 1)
			buffers[fd] = remainder
			decoded = line.decode(errors="replace")
			if decoded:
				spec = fd_to_spec[fd]
				if not (spec.suppress_ready_output and _matches_ready(spec, decoded)):
					_write_tagged_line(spec.name, decoded, tag_mode)
				_check_on_ready(spec, decoded, ready_flags, fd)
	return True


def _pump_selector_output(
	selector: BaseSelector,
	procs: list[tuple[str, subprocess.Popen[str], CommandSpec]],
	ready_flags: dict[str, bool],
	tag_mode: TagMode,
	*,
	timeout: float,
) -> None:
	"""Read and print available child output from the registered pipes."""
	events = selector.select(timeout=timeout)
	for key, _mask in events:
		name = key.data
		stream = key.fileobj
		if isinstance(stream, int):
			continue
		# stream is now guaranteed to be a file-like object
		line = cast(TextIOBase, stream).readline()
		if line:
			spec = next((s for n, _, s in procs if n == name), None)
			if spec:
				if not (spec.suppress_ready_output and _matches_ready(spec, line)):
					_write_tagged_line(name, line.rstrip("\n"), tag_mode)
				_check_on_ready(spec, line, ready_flags, name)
			else:
				_write_tagged_line(name, line.rstrip("\n"), tag_mode)
		else:
			selector.unregister(stream)


def _run_without_pty(
	commands: Sequence[CommandSpec],
	*,
	tag_mode: TagMode,
) -> int:
	procs: list[tuple[str, subprocess.Popen[str], CommandSpec]] = []
	completed_codes: list[int] = []
	selector = DefaultSelector()
	ready_flags: dict[str, bool] = {}

	try:
		for spec in commands:
			proc = subprocess.Popen(
				spec.args,
				cwd=spec.cwd,
				env=spec.env,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				bufsize=1,
				universal_newlines=True,
				start_new_session=os_family() != "windows",
			)
			_call_on_spawn(spec)
			if proc.stdout:
				selector.register(proc.stdout, EVENT_READ, data=spec.name)
			ready_flags[spec.name] = False
			procs.append((spec.name, proc, spec))

		while procs:
			_pump_selector_output(selector, procs, ready_flags, tag_mode, timeout=0.1)
			remaining: list[tuple[str, subprocess.Popen[str], CommandSpec]] = []
			for name, proc, spec in procs:
				code = proc.poll()
				if code is None:
					remaining.append((name, proc, spec))
				else:
					_signal_process_tree(proc.pid, signal.SIGKILL)
					completed_codes.append(code)
					if proc.stdout:
						with contextlib.suppress(Exception):
							selector.unregister(proc.stdout)
							proc.stdout.close()
			procs = remaining
			if completed_codes:
				break
	except KeyboardInterrupt:
		sys.stdout.write("\nShutting down...\n")
		sys.stdout.flush()
		return 130
	finally:
		# Signal every child up front so their graceful shutdowns overlap.
		for _name, proc, _spec in procs:
			with contextlib.suppress(Exception):
				_signal_process_tree(proc.pid, signal.SIGTERM)
		deadline = time.monotonic() + 4
		with contextlib.suppress(KeyboardInterrupt):
			while (
				any(proc.poll() is None for _name, proc, _spec in procs)
				and time.monotonic() < deadline
			):
				# Keep draining pipes while waiting: a child blocked writing to
				# a full pipe can never exit, and its final logs would be lost.
				with contextlib.suppress(Exception):
					_pump_selector_output(
						selector, procs, ready_flags, tag_mode, timeout=0.05
					)
		for _name, proc, _spec in procs:
			if proc.poll() is None:
				with contextlib.suppress(Exception):
					_signal_process_tree(proc.pid, signal.SIGKILL)
				with contextlib.suppress(Exception):
					proc.wait(timeout=1)
		for key in list(selector.get_map().values()):
			with contextlib.suppress(Exception):
				selector.unregister(key.fileobj)
		selector.close()

	exit_codes = completed_codes + [
		proc.returncode or 0 for _name, proc, _spec in procs
	]
	return max(exit_codes) if exit_codes else 0


def _write_tagged_line(name: str, message: str, tag_mode: TagMode) -> None:
	"""Write a line of output with optional process tag.

	Args:
		name: Process name (e.g., "server", "web")
		message: The line of output to write
		tag_mode: How to display the tag:
			- "colored": Show [name] with ANSI colors
			- "plain": Show [name] without colors
	"""
	# Filter out unwanted web server messages
	clean_message = ANSI_ESCAPE.sub("", message)
	if (
		"Network: use --host to expose" in clean_message
		or "press h + enter to show help" in clean_message
		or "➜  Local:" in clean_message
		or "/__manifest" in clean_message
		or "?import" in clean_message
	):
		return

	message = ANSI_TERMINAL_CONTROL.sub("", message)

	if tag_mode == "colored":
		color = ANSI_CODES.get(TAG_COLORS.get(name, ""), "")
		if color:
			sys.stdout.write(f"{color}[{name}]{ANSI_CODES['reset']} {message}\n")
		else:
			sys.stdout.write(f"[{name}] {message}\n")
	else:
		# Plain mode: tags without color
		sys.stdout.write(f"[{name}] {message}\n")
	sys.stdout.flush()


def _close_fd(fd: int) -> None:
	with contextlib.suppress(Exception):
		os.close(fd)


def _signal_process_tree(pid: int, sig: signal.Signals) -> None:
	with contextlib.suppress(ProcessLookupError, PermissionError):
		if os_family() == "windows":
			os.kill(pid, sig)
		else:
			os.killpg(pid, sig)
