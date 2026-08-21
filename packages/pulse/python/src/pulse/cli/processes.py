from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from typing import IO, Any, cast, final

from pulse.cli.helpers import os_family
from pulse.cli.logging import TagMode
from pulse.cli.models import CommandSpec

PROCESS_STOP_TIMEOUT = 4.0
PROCESS_KILL_TIMEOUT = 1.0

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
ANSI_TERMINAL_CONTROL = re.compile(
	r"\x1B(?:\[[0-?]*[ -/]*(?:[@-l]|[n-~])"
	+ r"|\][^\x07\x1B]*(?:\x07|\x1B\\)?"
	+ r"|[PX^_][^\x1B]*(?:\x1B\\)?"
	+ r"|(?!\[)[ -/]*[0-~])"
)


@final
class _WindowsJob:
	"""Own a Windows process tree and terminate every descendant on close."""

	def __init__(self, process: subprocess.Popen[str]) -> None:
		import ctypes
		from ctypes import wintypes

		@final
		class IO_COUNTERS(ctypes.Structure):
			_fields_ = [
				("ReadOperationCount", ctypes.c_ulonglong),
				("WriteOperationCount", ctypes.c_ulonglong),
				("OtherOperationCount", ctypes.c_ulonglong),
				("ReadTransferCount", ctypes.c_ulonglong),
				("WriteTransferCount", ctypes.c_ulonglong),
				("OtherTransferCount", ctypes.c_ulonglong),
			]

		@final
		class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
			_fields_ = [
				("PerProcessUserTimeLimit", ctypes.c_longlong),
				("PerJobUserTimeLimit", ctypes.c_longlong),
				("LimitFlags", wintypes.DWORD),
				("MinimumWorkingSetSize", ctypes.c_size_t),
				("MaximumWorkingSetSize", ctypes.c_size_t),
				("ActiveProcessLimit", wintypes.DWORD),
				("Affinity", ctypes.c_size_t),
				("PriorityClass", wintypes.DWORD),
				("SchedulingClass", wintypes.DWORD),
			]

		@final
		class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
			_fields_ = [
				("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
				("IoInfo", IO_COUNTERS),
				("ProcessMemoryLimit", ctypes.c_size_t),
				("JobMemoryLimit", ctypes.c_size_t),
				("PeakProcessMemoryUsed", ctypes.c_size_t),
				("PeakJobMemoryUsed", ctypes.c_size_t),
			]

		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
		kernel32.CreateJobObjectW.restype = wintypes.HANDLE
		kernel32.SetInformationJobObject.argtypes = [
			wintypes.HANDLE,
			ctypes.c_int,
			wintypes.LPVOID,
			wintypes.DWORD,
		]
		kernel32.SetInformationJobObject.restype = wintypes.BOOL
		kernel32.AssignProcessToJobObject.argtypes = [
			wintypes.HANDLE,
			wintypes.HANDLE,
		]
		kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
		kernel32.OpenProcess.argtypes = [
			wintypes.DWORD,
			wintypes.BOOL,
			wintypes.DWORD,
		]
		kernel32.OpenProcess.restype = wintypes.HANDLE
		kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
		kernel32.TerminateJobObject.restype = wintypes.BOOL
		kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
		kernel32.CloseHandle.restype = wintypes.BOOL

		job = kernel32.CreateJobObjectW(None, None)
		if not job:
			raise ctypes.WinError(ctypes.get_last_error())

		info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
		info.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
		if not kernel32.SetInformationJobObject(
			job, 9, ctypes.byref(info), ctypes.sizeof(info)
		):
			kernel32.CloseHandle(job)
			raise ctypes.WinError(ctypes.get_last_error())

		process_handle = kernel32.OpenProcess(
			0x0001 | 0x0100,  # PROCESS_TERMINATE | PROCESS_SET_QUOTA
			False,
			process.pid,
		)
		if not process_handle:
			kernel32.CloseHandle(job)
			raise ctypes.WinError(ctypes.get_last_error())
		try:
			if not kernel32.AssignProcessToJobObject(job, process_handle):
				raise ctypes.WinError(ctypes.get_last_error())
		except BaseException:
			kernel32.CloseHandle(job)
			raise
		finally:
			kernel32.CloseHandle(process_handle)

		self._kernel32 = kernel32
		self._handle = job

	def terminate(self) -> None:
		if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
			import ctypes

			raise ctypes.WinError(ctypes.get_last_error())

	def close(self) -> None:
		if self._handle:
			self._kernel32.CloseHandle(self._handle)
			self._handle = None


@final
class ManagedProcess:
	"""A subprocess whose complete descendant tree has one lifecycle owner."""

	def __init__(
		self,
		process: subprocess.Popen[str],
		job: _WindowsJob | None,
	) -> None:
		self.process = process
		self._output_thread: threading.Thread | None = None
		self._wait_thread: threading.Thread | None = None
		self._job = job
		self._exit_code: int | None = None

	@classmethod
	def start(
		cls,
		spec: CommandSpec,
		on_output: Callable[[str], None],
		on_exit: Callable[[int], None],
		*,
		pass_fds: tuple[int, ...] = (),
	) -> ManagedProcess:
		"""Start a managed process with optional inherited descriptors.

		On Windows, pass_fds contains inheritable OS handles rather than CRT
		descriptors; callers own their inheritability. On POSIX, pass_fds
		contains file descriptors passed through subprocess.
		"""
		windows = os_family() == "windows"
		creationflags = 0
		args = spec.args
		kwargs: dict[str, object] = {}
		if windows:
			creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
			launcher = os.path.join(os.path.dirname(__file__), "_windows_launcher.py")
			args = [sys.executable, "-I", launcher, *spec.args]
			if pass_fds:
				kwargs["close_fds"] = False
		else:
			kwargs["start_new_session"] = True
			if pass_fds:
				kwargs["pass_fds"] = pass_fds
		process = subprocess.Popen(
			args,
			cwd=spec.cwd,
			env=spec.env,
			stdout=subprocess.PIPE,
			stdin=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			bufsize=1,
			creationflags=creationflags,
			**cast(Any, kwargs),
		)
		job: _WindowsJob | None = None
		try:
			if windows:
				job = _WindowsJob(process)
				if process.stdin is None:
					raise RuntimeError("launcher stdin is not available")
				process.stdin.write("\0")
				process.stdin.flush()
		except BaseException:
			if job is not None:
				job.close()
			with contextlib.suppress(Exception):
				process.kill()
			process.wait()
			raise

		def read_output(stream: IO[str] | None) -> None:
			if stream is None:
				return
			for line in stream:
				on_output(line.rstrip("\n"))

		managed = cls(process, job)

		def wait_for_exit() -> None:
			if windows:
				code = process.wait()
			else:
				# Observe the exit without reaping (WNOWAIT): the zombie leader
				# keeps the pid and pgid pinned until close() reaps it, so
				# signalling the process group is always race-free.
				try:
					info = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
				except ChildProcessError:
					info = None
				if info is not None and info.si_code == os.CLD_EXITED:
					code = info.si_status
				elif info is not None:
					code = -info.si_status
				else:
					code = process.wait()
			managed._exit_code = code
			on_exit(code)

		output_thread = threading.Thread(
			target=read_output,
			args=(process.stdout,),
			name=f"pulse-{spec.name}-output",
			daemon=True,
		)
		wait_thread = threading.Thread(
			target=wait_for_exit,
			name=f"pulse-{spec.name}-wait",
			daemon=True,
		)
		output_thread.start()
		wait_thread.start()
		managed._output_thread = output_thread
		managed._wait_thread = wait_thread
		_call_on_spawn(spec)
		return managed

	@property
	def returncode(self) -> int | None:
		if os_family() == "windows":
			return self.process.poll()
		# Never poll() on POSIX: reaping is deferred to close() so the zombie
		# leader keeps its pgid ours for the lifetime of this object.
		return self._exit_code

	def is_alive(self) -> bool:
		return self.returncode is None

	def request_stop(self) -> None:
		if os_family() == "windows":
			if not self.is_alive():
				return
			ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
			if ctrl_break is not None:
				with contextlib.suppress(OSError):
					self.process.send_signal(ctrl_break)
					return
			self.process.terminate()
			return
		# Safe even after the leader exits: it stays a zombie (pinning the
		# pgid) until close() reaps it, so this cannot hit a reused pgid.
		with contextlib.suppress(ProcessLookupError, PermissionError):
			os.killpg(self.process.pid, signal.SIGTERM)

	def send_line(self, line: str) -> None:
		if self.process.stdin is None:
			raise RuntimeError("process stdin is not available")
		self.process.stdin.write(line + "\n")
		self.process.stdin.flush()

	def kill_tree(self) -> None:
		if self._job is not None:
			self._job.terminate()
			return
		if os_family() == "windows":
			return
		# Kills surviving group members (e.g. grandchildren of a crashed
		# leader) too: the zombie leader pins the pgid until close() reaps it.
		with contextlib.suppress(ProcessLookupError, PermissionError):
			os.killpg(self.process.pid, signal.SIGKILL)

	def close(self) -> None:
		if self.process.stdin is not None:
			with contextlib.suppress(Exception):
				self.process.stdin.close()
		# Wait for death and drain stdout before closing the pipe, otherwise a
		# traceback printed as the child exits can be swallowed.
		if self._wait_thread is not None:
			self._wait_thread.join(timeout=1)
		if self._output_thread is not None:
			self._output_thread.join(timeout=1)
			if self._output_thread.is_alive() and self.process.stdout is not None:
				with contextlib.suppress(Exception):
					self.process.stdout.close()
				self._output_thread.join(timeout=1)
		if self.process.stdout is not None:
			with contextlib.suppress(Exception):
				self.process.stdout.close()
		if os_family() != "windows":
			# Reap the leader last so its pgid stayed ours for every kill above.
			with contextlib.suppress(ChildProcessError):
				self.process.wait()
		if self._job is not None:
			self._job.close()
			self._job = None


def execute_commands(
	commands: Sequence[CommandSpec],
	*,
	tag_mode: TagMode = "colored",
) -> int:
	"""Run the provided commands, streaming tagged output to stdout.

	Returns when any command exits; the others are stopped gracefully and then
	killed with their descendant trees. Children see pipes, not a terminal;
	command environments carry FORCE_COLOR when color output is wanted.

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

	previous_sigterm = signal.signal(signal.SIGTERM, interrupt_on_sigterm)
	processes: list[ManagedProcess] = []
	self_exit_codes: dict[str, int] = {}
	first_exit_code: int | None = None
	exited = threading.Event()
	stopping = threading.Event()

	def start(spec: CommandSpec) -> ManagedProcess:
		ready = threading.Event()

		def on_output(line: str) -> None:
			write_tagged_line(spec.name, line, tag_mode)
			if spec.ready_pattern and not ready.is_set() and _matches_ready(spec, line):
				ready.set()
				if spec.on_ready:
					try:
						spec.on_ready()
					except Exception:
						pass

		def on_exit(code: int) -> None:
			nonlocal first_exit_code
			# Codes reported after the shutdown began are stop-induced (e.g.
			# 0xFFFFFFFF from a terminated Windows survivor) and must not mask
			# or fabricate a failure.
			if not stopping.is_set():
				self_exit_codes[spec.name] = code
			if first_exit_code is None:
				first_exit_code = code
			exited.set()

		return ManagedProcess.start(spec, on_output, on_exit)

	try:
		for spec in commands:
			processes.append(start(spec))
		# Poll the event instead of blocking forever: on Windows a bare
		# Event.wait() would swallow Ctrl+C.
		while not exited.wait(0.2):
			pass
		stopping.set()
		# _stop_processes is idempotent for the finally below.
		_stop_processes(processes)
		if self_exit_codes:
			return max(self_exit_codes.values())
		return first_exit_code if first_exit_code is not None else 0
	except KeyboardInterrupt:
		sys.stdout.write("\nShutting down...\n")
		sys.stdout.flush()
		return 130
	finally:
		_stop_processes(processes)
		signal.signal(signal.SIGTERM, previous_sigterm)


def _stop_processes(processes: list[ManagedProcess]) -> None:
	"""Stop processes gracefully, then terminate every owned descendant tree.

	Output threads keep draining throughout, so full pipes cannot prevent a
	child from completing its shutdown hooks. A second Ctrl+C skips the grace
	period and goes straight to the kill.
	"""
	for process in processes:
		process.request_stop()
	with contextlib.suppress(KeyboardInterrupt):
		deadline = time.monotonic() + PROCESS_STOP_TIMEOUT
		while (
			any(process.is_alive() for process in processes)
			and time.monotonic() < deadline
		):
			time.sleep(0.05)
	for process in processes:
		process.kill_tree()
	deadline = time.monotonic() + PROCESS_KILL_TIMEOUT
	while (
		any(process.is_alive() for process in processes) and time.monotonic() < deadline
	):
		time.sleep(0.05)
	for process in processes:
		process.close()


def _call_on_spawn(spec: CommandSpec) -> None:
	"""Call the on_spawn callback if it exists."""
	if spec.on_spawn:
		try:
			spec.on_spawn()
		except Exception:
			pass


def _matches_ready(spec: CommandSpec, line: str) -> bool:
	return bool(
		spec.ready_pattern and re.search(spec.ready_pattern, ANSI_ESCAPE.sub("", line))
	)


def write_tagged_line(name: str, message: str, tag_mode: TagMode) -> None:
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
