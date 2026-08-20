from __future__ import annotations

import asyncio
import contextlib
import signal
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, final

from watchfiles import Change, awatch

from pulse.cli.logging import TagMode
from pulse.cli.models import CommandSpec
from pulse.cli.processes import ManagedProcess, write_tagged_line
from pulse.cli.protocol import VITE_CONFIGURED, VITE_LISTENING, WORKER_READY, parse
from pulse.env import ENV_PULSE_LISTEN_FDS, ENV_PULSE_SUPERVISED

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
		self.vite_plugin_timeout = vite_plugin_timeout
		self.changed = asyncio.Event()
		self.shutdown = asyncio.Event()
		self.backend: ManagedProcess | None = None
		self.web: ManagedProcess | None = None
		self._backend_exit = asyncio.Event()
		self._backend_ready = asyncio.Event()
		self._web_exit = asyncio.Event()
		self._backend_code: int | None = None
		self._web_code: int | None = None
		self._vite_configured = asyncio.Event()
		self._vite_listening = asyncio.Event()
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
					return self._web_code or 1
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
			for signum, handler in previous_handlers.items():
				signal.signal(signum, cast(Any, handler))

	def _handle_interrupt(self) -> None:
		self.shutdown.set()
		if self.backend is not None:
			self.backend.kill_tree()
		if self.web is not None:
			self.web.kill_tree()

	async def _replace_backend(self) -> bool:
		await self._stop(self.backend)
		self.backend = None
		self._backend_exit.clear()
		self._backend_ready.clear()
		self._backend_code = None
		if self.shutdown.is_set():
			return False
		env = dict(self.backend_spec.env)
		env[ENV_PULSE_LISTEN_FDS] = ",".join(
			f"{listener.family}:{listener.fileno()}" for listener in self.listeners
		)
		for listener in self.listeners:
			listener.set_inheritable(True)
		pass_fds = tuple(listener.fileno() for listener in self.listeners)
		loop = asyncio.get_running_loop()

		def on_output(line: str) -> None:
			message, text = parse(line)
			if text:
				write_tagged_line(self.backend_spec.name, text, self.tag_mode)
			if message == WORKER_READY:
				loop.call_soon_threadsafe(self._backend_ready.set)

		def on_exit(code: int) -> None:
			self._backend_code = code
			loop.call_soon_threadsafe(self._backend_exit.set)

		spec = CommandSpec(
			name=self.backend_spec.name,
			args=self.backend_spec.args,
			cwd=self.backend_spec.cwd,
			env=env,
		)
		try:
			self.backend = ManagedProcess.start(
				spec, on_output, on_exit, pass_fds=pass_fds
			)
			result = await self._race(
				"changed",
				"backend",
				"web",
				extra=asyncio.create_task(self._backend_ready.wait()),
			)
			if result == "ready":
				return True
			await self._stop(self.backend)
			self.backend = None
			return False
		finally:
			for listener in self.listeners:
				listener.set_inheritable(False)

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
		loop = asyncio.get_running_loop()

		def on_output(line: str) -> None:
			message, text = parse(line)
			if text:
				write_tagged_line(web_spec.name, text, self.tag_mode)
			if message == VITE_CONFIGURED:
				loop.call_soon_threadsafe(self._vite_configured.set)
			elif message == VITE_LISTENING:
				loop.call_soon_threadsafe(self._vite_listening.set)

		def on_exit(code: int) -> None:
			self._web_code = code
			loop.call_soon_threadsafe(self._web_exit.set)

		env = dict(web_spec.env)
		env[ENV_PULSE_SUPERVISED] = "1"
		spec = CommandSpec(
			name=web_spec.name,
			args=web_spec.args,
			cwd=web_spec.cwd,
			env=env,
		)
		self.web = ManagedProcess.start(spec, on_output, on_exit)
		try:
			got = await self._wait_vite_signal(
				self._vite_configured, timeout=self.vite_plugin_timeout
			)
		except TimeoutError:
			if not self.shutdown.is_set() and self._web_code is None:
				print(
					"Vite did not load pulse() within "
					+ f"{self.vite_plugin_timeout:g}s. Add it to the plugins "
					+ "array in vite.config.ts.",
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
		if extra is not None and extra in done and not extra.cancelled():
			return "ready"
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
