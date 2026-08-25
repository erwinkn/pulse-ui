from __future__ import annotations

import asyncio
import contextlib
import signal
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, final

from watchfiles import Change, awatch

from pulse.cli.helpers import os_family
from pulse.cli.logging import TagMode
from pulse.cli.models import CommandSpec
from pulse.cli.processes import (
	ManagedProcess,
	normalize_exit_code,
	stop_processes,
	write_tagged_line,
)
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
VITE_LISTENING_TIMEOUT = 30.0
DEV_STOP_GRACE = 1.0

Wait = Literal["shutdown", "changed", "backend", "web", "ready"]
WaitName = Literal["changed", "backend", "web"]
BackendStart = Literal["ready", "failed", "changed"]


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
		self._backend_ready = asyncio.Event()
		self._web_exit = asyncio.Event()
		self._backend_gen = 0
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
					return normalize_exit_code(130)
				if self._web_code is not None:
					return normalize_exit_code(self._web_code)
			while not self.shutdown.is_set():
				if self._web_code is not None:
					return normalize_exit_code(self._web_code)
				self.changed.clear()
				backend_start = await self._replace_backend()
				if self.shutdown.is_set():
					break
				if self._web_code is not None:
					return normalize_exit_code(self._web_code)
				if backend_start != "ready":
					if backend_start == "failed":
						print(
							"Backend failed to start. Waiting for changes to retry...",
							flush=True,
						)
					await self._race("changed", "web")
					continue
				if self.backend_spec.on_ready is not None:
					self.backend_spec.on_ready()
				result = await self._race("changed", "backend", "web")
				if result == "web":
					return normalize_exit_code(
						self._web_code if self._web_code is not None else 1
					)
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
			return normalize_exit_code(130 if self.shutdown.is_set() else 0)
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
		if self.shutdown.is_set():
			if self.backend is not None:
				self.backend.kill_tree()
			if self.web is not None:
				self.web.kill_tree()
		else:
			self.shutdown.set()

	def _note_backend_ready(self, gen: int) -> None:
		# A late marker relayed by a replaced generation's output thread must
		# not mark the current backend ready.
		if gen != self._backend_gen:
			return
		self._backend_ready.set()

	def _note_backend_exit(self, gen: int, code: int) -> None:
		# A previous generation's exit callback can fire after its process was
		# replaced (close() joins its wait thread with a timeout); it must not
		# flag the current backend as exited.
		if gen != self._backend_gen:
			return
		self._backend_code = code
		self._backend_exit.set()

	async def _replace_backend(self) -> BackendStart:
		await self._stop(self.backend)
		self.backend = None
		self._backend_gen += 1
		gen = self._backend_gen
		self._backend_exit.clear()
		self._backend_ready.clear()
		self._backend_code = None
		if self.shutdown.is_set():
			# The caller re-checks shutdown before interpreting this outcome.
			return "changed"
		env = dict(self.backend_spec.env)
		env[ENV_PULSE_LISTEN_FDS] = ",".join(
			f"{listener.family}:{listener.fileno()}" for listener in self.listeners
		)
		for listener in self.listeners:
			listener.set_inheritable(True)
		pass_fds = tuple(listener.fileno() for listener in self.listeners)
		loop = asyncio.get_running_loop()

		def on_output(line: str) -> None:
			messages, text = parse(line)
			# Suppress only the padding newlines around markers, not genuine
			# blank lines from the child.
			if text or not messages:
				write_tagged_line(self.backend_spec.name, text, self.tag_mode)
			if WORKER_READY in messages:
				loop.call_soon_threadsafe(self._note_backend_ready, gen)

		def on_exit(code: int) -> None:
			loop.call_soon_threadsafe(self._note_backend_exit, gen, code)

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
		finally:
			for listener in self.listeners:
				listener.set_inheritable(False)
		result = await self._race(
			"changed",
			"backend",
			"web",
			ready=self._backend_ready,
		)
		if result == "ready":
			return "ready"
		await self._stop(self.backend)
		self.backend = None
		return "changed" if result == "changed" else "failed"

	async def _wait_vite_signal(
		self, event: asyncio.Event, *, timeout: float | None
	) -> bool:
		if timeout is None:
			result = await self._race("web", ready=event)
		else:
			async with asyncio.timeout(timeout):
				result = await self._race("web", ready=event)
		return result == "ready"

	async def _start_web(self) -> None:
		assert self.web_spec is not None
		web_spec = self.web_spec
		self._web_exit.clear()
		self._web_code = None
		loop = asyncio.get_running_loop()

		def on_output(line: str) -> None:
			messages, text = parse(line)
			if text or not messages:
				write_tagged_line(web_spec.name, text, self.tag_mode)
			if VITE_CONFIGURED in messages:
				loop.call_soon_threadsafe(self._vite_configured.set)
			if VITE_LISTENING in messages:
				loop.call_soon_threadsafe(self._vite_listening.set)

		def on_exit(code: int) -> None:
			loop.call_soon_threadsafe(self._note_web_exit, code)

		env = dict(web_spec.env)
		env[ENV_PULSE_SUPERVISED] = "1"
		web_args = web_spec.args
		if os_family() != "windows":
			# POSIX uses guard for orphan cleanup; Windows job objects reap descendants.
			web_args = [
				sys.executable,
				"-m",
				"pulse.cli.guard",
				"--",
				*web_spec.args,
			]
		spec = CommandSpec(
			name=web_spec.name,
			args=web_args,
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
		try:
			got = await self._wait_vite_signal(
				self._vite_listening, timeout=VITE_LISTENING_TIMEOUT
			)
		except TimeoutError:
			if not self.shutdown.is_set() and self._web_code is None:
				print(
					"Vite loaded pulse() but never reported listening within "
					+ f"{VITE_LISTENING_TIMEOUT:g}s.",
					flush=True,
				)
				await self._stop(self.web)
				self.web = None
				self._web_code = 1
			return
		if not got:
			return
		if web_spec.on_ready is not None:
			web_spec.on_ready()

	def _note_web_exit(self, code: int) -> None:
		self._web_code = code
		self._web_exit.set()

	async def _race(
		self,
		*names: WaitName,
		ready: asyncio.Event | None = None,
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
		if ready is not None:
			waiters["ready"] = asyncio.create_task(ready.wait())
		try:
			done, _pending = await asyncio.wait(
				waiters.values(), return_when=asyncio.FIRST_COMPLETED
			)
		finally:
			for task in waiters.values():
				if not task.done():
					task.cancel()
			await asyncio.gather(*waiters.values(), return_exceptions=True)
		for name, task in waiters.items():
			if task in done and not task.cancelled():
				return cast(Wait, name)
		raise asyncio.CancelledError

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
		await asyncio.to_thread(stop_processes, [process], grace=DEV_STOP_GRACE)
