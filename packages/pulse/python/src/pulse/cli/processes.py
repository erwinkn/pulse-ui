from __future__ import annotations

import contextlib
import os
import pty
import select
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from io import TextIOBase
from typing import cast

from rich.console import Console

from pulse.cli.helpers import os_family
from pulse.cli.models import CommandSpec

ANSI_CODES = {
	"cyan": "\033[36m",
	"orange1": "\033[38;5;208m",
	"default": "\033[90m",
}


def execute_commands(
	commands: Sequence[CommandSpec],
	*,
	console: Console,
	tag_colors: Mapping[str, str] | None = None,
) -> int:
	"""Run the provided commands, streaming tagged output to stdout."""
	if not commands:
		return 0

	color_lookup = dict(tag_colors or {})

	if os_family() == "windows" or not hasattr(pty, "fork"):
		return _run_without_pty(commands, console=console, colors=color_lookup)

	return _run_with_pty(commands, console=console, colors=color_lookup)


def _run_with_pty(
	commands: Sequence[CommandSpec],
	*,
	console: Console,
	colors: Mapping[str, str],
) -> int:
	procs: list[tuple[str, int, int]] = []
	fd_to_name: dict[int, str] = {}
	buffers: dict[int, bytearray] = {}

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
				fd_to_name[fd] = spec.name
				buffers[fd] = bytearray()
				if spec.on_spawn:
					try:
						spec.on_spawn()
					except Exception:
						pass

		while procs:
			for tag, pid, fd in list(procs):
				try:
					wpid, status = os.waitpid(pid, os.WNOHANG)
					if wpid == pid:
						procs.remove((tag, pid, fd))
						_close_fd(fd)
				except ChildProcessError:
					procs.remove((tag, pid, fd))
					_close_fd(fd)

			if not procs:
				break

			readable = [fd for _, _, fd in procs]
			try:
				ready, _, _ = select.select(readable, [], [], 0.1)
			except (OSError, ValueError):
				break

			for fd in ready:
				try:
					data = os.read(fd, 4096)
					if not data:
						continue
					buffers[fd].extend(data)
					while b"\n" in buffers[fd]:
						line, remainder = buffers[fd].split(b"\n", 1)
						buffers[fd] = remainder
						decoded = line.decode(errors="replace")
						if decoded:
							_write_tagged_line(fd_to_name[fd], decoded, colors)
				except OSError:
					continue

		exit_codes: list[int] = []
		for _tag, pid, fd in procs:
			try:
				_, status = os.waitpid(pid, 0)
				exit_codes.append(os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1)
			except Exception:
				pass
			_close_fd(fd)

		return max(exit_codes) if exit_codes else 0

	except KeyboardInterrupt:
		for _tag, pid, _fd in procs:
			try:
				os.kill(pid, signal.SIGTERM)
			except Exception:
				pass
		return 130
	finally:
		for _tag, pid, fd in procs:
			try:
				os.kill(pid, signal.SIGKILL)
			except Exception:
				pass
			_close_fd(fd)


def _run_without_pty(
	commands: Sequence[CommandSpec],
	*,
	console: Console,
	colors: Mapping[str, str],
) -> int:
	from selectors import EVENT_READ, DefaultSelector

	procs: list[tuple[str, subprocess.Popen[str]]] = []
	completed_codes: list[int] = []
	selector = DefaultSelector()

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
			)
			if spec.on_spawn:
				try:
					spec.on_spawn()
				except Exception:
					pass
			if proc.stdout:
				selector.register(proc.stdout, EVENT_READ, data=spec.name)
			procs.append((spec.name, proc))

		while procs:
			events = selector.select(timeout=0.1)
			for key, _mask in events:
				name = key.data
				stream = key.fileobj
				if isinstance(stream, int):
					continue
				# stream is now guaranteed to be a file-like object
				line = cast(TextIOBase, stream).readline()
				if line:
					_write_tagged_line(name, line.rstrip("\n"), colors)
				else:
					selector.unregister(stream)
			remaining: list[tuple[str, subprocess.Popen[str]]] = []
			for name, proc in procs:
				code = proc.poll()
				if code is None:
					remaining.append((name, proc))
				else:
					completed_codes.append(code)
					if proc.stdout:
						with contextlib.suppress(Exception):
							selector.unregister(proc.stdout)
							proc.stdout.close()
			procs = remaining
	except KeyboardInterrupt:
		for _name, proc in procs:
			with contextlib.suppress(Exception):
				proc.terminate()
		return 130
	finally:
		for _name, proc in procs:
			with contextlib.suppress(Exception):
				proc.terminate()
			with contextlib.suppress(Exception):
				proc.wait(timeout=1)
		for key in list(selector.get_map().values()):
			with contextlib.suppress(Exception):
				selector.unregister(key.fileobj)
		selector.close()

	exit_codes = completed_codes + [proc.returncode or 0 for _name, proc in procs]
	return max(exit_codes) if exit_codes else 0


def _write_tagged_line(name: str, message: str, colors: Mapping[str, str]) -> None:
	color = ANSI_CODES.get(colors.get(name, ""), ANSI_CODES["default"])
	sys.stdout.write(f"{color}[{name}]\033[0m {message}\n")
	sys.stdout.flush()


def _close_fd(fd: int) -> None:
	with contextlib.suppress(Exception):
		os.close(fd)
