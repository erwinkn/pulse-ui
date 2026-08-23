from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, final

from watchfiles import Change, awatch

from pulse.cli.logging import TagMode
from pulse.cli.models import CommandSpec
from pulse.cli.processes import ManagedProcess, write_tagged_line
from pulse.env import ENV_PULSE_LISTEN_FDS, ENV_PULSE_READY_FD, ENV_PULSE_VITE_READY_FD

IGNORED_DIRECTORIES = frozenset(
	{
		".git",
		".hg",
		".mypy_cache",
		".pytest_cache",
		".ruff_cache",
		".tox",
		".venv",
		"__pycache__",
		"build",
		"dist",
		"node_modules",
		"venv",
	}
)
PYTHON_EXTENSIONS = frozenset({".py", ".pyx", ".pyd"})
VITE_PLUGIN_TIMEOUT = 15.0
# A descendant that escaped the process group can still hold a readiness pipe's
# write end; shutdown abandons the reader rather than waiting on it forever.
READY_PIPE_DRAIN_TIMEOUT = 5.0

Wait = Literal["shutdown", "changed", "backend", "web", "ready"]


@dataclass(slots=True)
class PulseWatchFilter:
	application_roots: tuple[Path, ...]
	ignored_roots: tuple[Path, ...]
	registered_sources: set[Path] = field(default_factory=set)

	def __post_init__(self) -> None:
		self.application_roots = tuple(
			path.resolve() for path in self.application_roots
		)
		self.ignored_roots = tuple(path.resolve() for path in self.ignored_roots)
		self.registered_sources = {path.resolve() for path in self.registered_sources}

	def __call__(self, _change: Change, raw_path: str) -> bool:
		path = Path(raw_path).resolve()
		if path in self.registered_sources:
			return True
		if any(
			path == root or path.is_relative_to(root) for root in self.ignored_roots
		):
			return False
		if path.suffix not in PYTHON_EXTENSIONS:
			return False
		return any(
			path.is_relative_to(root)
			and not any(
				part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts
			)
			for root in self.application_roots
		)


@final
class DevSupervisor:
	"""Own the public listen sockets. Restart only the Uvicorn worker on save."""

	def __init__(
		self,
		*,
		backend: CommandSpec,
		web: CommandSpec | None,
		watch_roots: tuple[Path, ...],
		ignored_roots: tuple[Path, ...],
		registered_sources: set[Path],
		tag_mode: TagMode,
		listeners: tuple[socket.socket, ...],
		web_root: Path | None = None,
		vite_plugin_timeout: float = VITE_PLUGIN_TIMEOUT,
	) -> None:
		self.backend_spec = backend
		self.web_spec = web
		self.watch_roots = tuple(path.resolve() for path in watch_roots)
		self.filter = PulseWatchFilter(
			self.watch_roots,
			ignored_roots,
			registered_sources,
		)
		self.tag_mode: TagMode = tag_mode
		self.listeners = listeners
		self.web_root = web_root.resolve() if web_root is not None else None
		self.vite_plugin_timeout = vite_plugin_timeout
		self.changed = asyncio.Event()
		self.shutdown = asyncio.Event()
		self.backend: ManagedProcess | None = None
		self.web: ManagedProcess | None = None
		self._backend_exit = asyncio.Event()
		self._web_exit = asyncio.Event()
		self._backend_gen = 0
		self._backend_code: int | None = None
		self._web_code: int | None = None
		self._vite_configured = asyncio.Event()
		self._vite_listening = asyncio.Event()
		self._vite_ready_r: int | None = None
		self._vite_drain: asyncio.Task[None] | None = None
		for listener in listeners:
			listener.set_inheritable(False)

	async def run(self) -> int:
		loop = asyncio.get_running_loop()
		previous_handlers: dict[int, object] = {}

		def request_shutdown(_signum: int, _frame: object) -> None:
			loop.call_soon_threadsafe(self._handle_interrupt)

		for signum in (signal.SIGINT, signal.SIGTERM):
			previous_handlers[signum] = signal.signal(signum, request_shutdown)

		watch_task: asyncio.Task[None] | None = None
		try:
			watch_task = asyncio.create_task(self._watch())
			if self.web_spec is not None:
				await self._start_web()
				if self.shutdown.is_set():
					return 130
				if self._web_code is not None:
					return self._web_code
			while not self.shutdown.is_set():
				if self._web_code is not None:
					return self._web_code
				self.changed.clear()
				started = await self._replace_backend()
				if self.shutdown.is_set():
					break
				if self._web_code is not None:
					return self._web_code
				if not started:
					await self._race("changed", "web")
					continue
				if self.backend_spec.on_ready is not None:
					self.backend_spec.on_ready()
				result = await self._race("changed", "backend", "web")
				if result == "web":
					return self._web_code if self._web_code is not None else 1
				if result == "shutdown":
					break
				if result == "backend" and not self.changed.is_set():
					print(
						"Reload error: backend exited"
						+ (
							f" with code {self._backend_code}."
							if self._backend_code is not None
							else "."
						)
						+ " Waiting for changes to restart...",
						flush=True,
					)
					await self._race("changed", "web")
			return 130 if self.shutdown.is_set() else 0
		finally:
			if watch_task is not None:
				watch_task.cancel()
				with contextlib.suppress(asyncio.CancelledError):
					await watch_task
			await self._stop(self.backend)
			self.backend = None
			await self._stop(self.web)
			self.web = None
			await self._await_vite_drain()
			for signum, handler in previous_handlers.items():
				signal.signal(signum, cast(Any, handler))

	def _handle_interrupt(self) -> None:
		self.shutdown.set()
		if self.backend is not None:
			self.backend.kill_tree()
		if self.web is not None:
			self.web.kill_tree()

	def _note_backend_exit(self, gen: int, code: int) -> None:
		# A previous generation's exit callback can fire after its process was
		# replaced (close() joins its wait thread with a timeout); it must not
		# flag the current backend as exited.
		if gen != self._backend_gen:
			return
		self._backend_code = code
		self._backend_exit.set()

	async def _replace_backend(self) -> bool:
		await self._stop(self.backend)
		self.backend = None
		self._backend_gen += 1
		gen = self._backend_gen
		self._backend_exit.clear()
		self._backend_code = None
		if self.shutdown.is_set():
			return False
		ready_r, ready_w = os.pipe()
		os.set_inheritable(ready_w, True)
		os.set_inheritable(ready_r, False)
		env = dict(self.backend_spec.env)
		env[ENV_PULSE_LISTEN_FDS] = ",".join(
			f"{listener.family}:{listener.fileno()}" for listener in self.listeners
		)
		env[ENV_PULSE_READY_FD] = str(ready_w)
		for listener in self.listeners:
			listener.set_inheritable(True)
		pass_fds = tuple(listener.fileno() for listener in self.listeners) + (ready_w,)
		loop = asyncio.get_running_loop()

		def on_output(line: str) -> None:
			write_tagged_line(self.backend_spec.name, line, self.tag_mode)

		def on_exit(code: int) -> None:
			loop.call_soon_threadsafe(self._note_backend_exit, gen, code)

		spec = CommandSpec(
			name=self.backend_spec.name,
			args=self.backend_spec.args,
			cwd=self.backend_spec.cwd,
			env=env,
		)
		ready: asyncio.Task[bytes] | None = None
		try:
			try:
				self.backend = ManagedProcess.start(
					spec, on_output, on_exit, pass_fds=pass_fds
				)
			finally:
				os.close(ready_w)
				for listener in self.listeners:
					listener.set_inheritable(False)
			ready = asyncio.create_task(asyncio.to_thread(os.read, ready_r, 1))
			result = await self._race("changed", "backend", "web", extra=ready)
			if result == "ready":
				try:
					ok = ready.result() == b"1"
				except OSError:
					ok = False
				if not ok:
					await self._stop(self.backend)
					self.backend = None
				return ok
			await self._stop(self.backend)
			self.backend = None
			return False
		finally:
			# Await the reader before closing its fd: the write end lives only
			# in the child, so once the child is stopped the read returns EOF
			# promptly. Closing first could hand the fd number to a concurrent
			# open while the pool thread still reads from it. Bounded: a
			# group-escaping descendant holding the write end must not wedge
			# the supervisor.
			if ready is not None and not ready.done():
				with contextlib.suppress(Exception):
					await asyncio.wait_for(
						asyncio.shield(ready), timeout=READY_PIPE_DRAIN_TIMEOUT
					)
			if ready is None or ready.done():
				with contextlib.suppress(OSError):
					os.close(ready_r)
			else:
				# A descendant escaped the process group and still holds the
				# write end: the reader thread and fd stay pinned until it dies.
				print(
					"Warning: a leftover backend descendant holds the readiness pipe open; leaking its reader until it exits.",
					flush=True,
				)

	def _close_vite_ready_fd(self) -> None:
		fd = self._vite_ready_r
		self._vite_ready_r = None
		if fd is not None:
			os.close(fd)

	async def _drain_vite_ready(self) -> None:
		ready_r = self._vite_ready_r
		if ready_r is None:
			return
		try:
			while True:
				try:
					chunk = await asyncio.to_thread(os.read, ready_r, 8)
				except OSError:
					return
				if not chunk:
					return
				if b"c" in chunk:
					self._vite_configured.set()
				if b"1" in chunk:
					self._vite_listening.set()
		finally:
			self._close_vite_ready_fd()

	async def _await_vite_drain(self) -> None:
		drain = self._vite_drain
		self._vite_drain = None
		if drain is None:
			self._close_vite_ready_fd()
			return
		# Bounded: the drain only sees EOF once every copy of the write end is
		# closed, so a web descendant that escaped the process group would
		# otherwise wedge shutdown. Abandon the reader instead — it closes the
		# fd itself once the straggler exits.
		with contextlib.suppress(Exception):
			await asyncio.wait_for(
				asyncio.shield(drain), timeout=READY_PIPE_DRAIN_TIMEOUT
			)
		if not drain.done():
			print(
				"Warning: a leftover web descendant holds the readiness pipe open; leaking its reader until it exits.",
				flush=True,
			)

	async def _wait_vite_signal(
		self, event: asyncio.Event, *, timeout: float | None
	) -> bool:
		waiter = asyncio.create_task(event.wait())
		try:
			if timeout is None:
				result = await self._race("web", extra=waiter)
			else:
				async with asyncio.timeout(timeout):
					result = await self._race("web", extra=waiter)
			return result == "ready"
		finally:
			if not waiter.done():
				waiter.cancel()
				with contextlib.suppress(asyncio.CancelledError):
					await waiter

	async def _start_web(self) -> None:
		assert self.web_spec is not None
		web_spec = self.web_spec
		self._web_exit.clear()
		self._web_code = None
		ready_r, ready_w = os.pipe()
		os.set_inheritable(ready_w, True)
		os.set_inheritable(ready_r, False)
		self._vite_ready_r = ready_r
		loop = asyncio.get_running_loop()

		def on_output(line: str) -> None:
			write_tagged_line(web_spec.name, line, self.tag_mode)

		def on_exit(code: int) -> None:
			self._web_code = code
			loop.call_soon_threadsafe(self._web_exit.set)

		env = dict(web_spec.env)
		env[ENV_PULSE_VITE_READY_FD] = str(ready_w)
		spec = CommandSpec(
			name=web_spec.name,
			args=[
				sys.executable,
				"-m",
				"pulse.cli.guard",
				"--",
				*web_spec.args,
			],
			cwd=web_spec.cwd,
			env=env,
		)
		try:
			self.web = ManagedProcess.start(
				spec, on_output, on_exit, pass_fds=(ready_w,)
			)
		except BaseException:
			self._close_vite_ready_fd()
			raise
		finally:
			os.close(ready_w)
		self._vite_drain = asyncio.create_task(self._drain_vite_ready())
		try:
			got = await self._wait_vite_signal(
				self._vite_configured, timeout=self.vite_plugin_timeout
			)
		except TimeoutError:
			if not self.shutdown.is_set() and self._web_code is None:
				vite_config: Path | None = None
				if self.web_root is not None:
					for filename in (
						"vite.config.ts",
						"vite.config.mts",
						"vite.config.js",
						"vite.config.mjs",
						"vite.config.cts",
						"vite.config.cjs",
					):
						candidate = self.web_root / filename
						if candidate.is_file():
							vite_config = candidate.resolve()
							break
				config_location = (
					f" in {vite_config}"
					if vite_config is not None
					else " in vite.config.ts"
				)
				print(
					"Vite did not load pulse() within "
					+ f"{self.vite_plugin_timeout:g}s. Add it to the plugins "
					+ "array"
					+ config_location
					+ '. Add `import { pulse } from "pulse-ui-client/vite";` '
					+ "and include it as `plugins: [..., pulse()]`.",
					flush=True,
				)
				await self._stop(self.web)
				self.web = None
				self._web_code = 1
			return
		if not got:
			return
		if not await self._wait_vite_signal(self._vite_listening, timeout=None):
			return
		if web_spec.on_ready is not None:
			web_spec.on_ready()

	async def _race(
		self,
		*names: str,
		extra: asyncio.Task[Any] | None = None,
	) -> Wait:
		waiters: dict[str, asyncio.Task[Any]] = {
			"shutdown": asyncio.create_task(self.shutdown.wait()),
		}
		if "changed" in names:
			waiters["changed"] = asyncio.create_task(self.changed.wait())
		if "backend" in names and self.backend is not None:
			waiters["backend"] = asyncio.create_task(self._backend_exit.wait())
		if "web" in names and self.web is not None:
			waiters["web"] = asyncio.create_task(self._web_exit.wait())
		if extra is not None:
			waiters["ready"] = extra
		try:
			done, _pending = await asyncio.wait(
				waiters.values(), return_when=asyncio.FIRST_COMPLETED
			)
		finally:
			owned = [task for task in waiters.values() if task is not extra]
			for task in owned:
				if not task.done():
					task.cancel()
			await asyncio.gather(*owned, return_exceptions=True)
		for name, task in waiters.items():
			if task in done and not task.cancelled():
				return cast(Wait, name)
		return "shutdown"

	async def _watch(self) -> None:
		async for _changes in awatch(
			*self.watch_roots,
			watch_filter=self.filter,
			debounce=300,
			step=50,
		):
			message = "Changes detected, reloading..."
			if self.tag_mode != "plain":
				message = (
					"\033[1;33mChanges detected,\033[0m " + "\033[1mreloading...\033[0m"
				)
			print(message, flush=True)
			self.changed.set()

	async def _stop(self, process: ManagedProcess | None) -> None:
		if process is None:
			return
		process.kill_tree()
		await asyncio.to_thread(process.close)
