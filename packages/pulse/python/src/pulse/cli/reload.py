from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import socket
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, cast, final

from watchfiles import Change, awatch

from pulse.cli.logging import TagMode
from pulse.cli.models import CommandSpec
from pulse.cli.processes import ANSI_ESCAPE, ManagedProcess, write_tagged_line
from pulse.env import ENV_PULSE_LISTEN_FDS, ENV_PULSE_READY_FD

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

	def add_sources(self, sources: list[str]) -> None:
		self.registered_sources.update(Path(source).resolve() for source in sources)

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


class _Wait(Enum):
	CHANGED = auto()
	SHUTDOWN = auto()
	BACKEND_EXIT = auto()
	WEB_EXIT = auto()
	READY = auto()


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
		web_first: bool = False,
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
		self.web_first = web_first
		self.desired = 0
		self.changed = asyncio.Event()
		self.shutdown = asyncio.Event()
		self.backend: ManagedProcess | None = None
		self.web: ManagedProcess | None = None
		self._backend_exit = asyncio.Event()
		self._web_exit = asyncio.Event()
		self._backend_code: int | None = None
		self._web_code: int | None = None
		self._ready_read: int | None = None
		self.filter.add_sources([str(source) for source in registered_sources])

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
			if self.web_spec is not None and self.web_first:
				await self._start_web()
				if self.shutdown.is_set():
					return 130
				if self._web_code is not None:
					return self._web_code
			self.desired = 1
			self.changed.set()
			while not self.shutdown.is_set():
				await self._wait_until_changed()
				if self.shutdown.is_set():
					break
				if self._web_code is not None:
					return self._web_code
				revision = self.desired
				self.changed.clear()
				started = await self._replace_backend()
				if self.shutdown.is_set():
					break
				if self._web_code is not None:
					return self._web_code
				if not started:
					if self.desired != revision:
						self.changed.set()
					continue
				if self.web_spec is not None and self.web is None:
					await self._start_web()
					if self._web_code is not None:
						return self._web_code
				if self.backend_spec.on_ready is not None:
					self.backend_spec.on_ready()
				result = await self._wait_while_running(revision)
				if result is _Wait.WEB_EXIT:
					return self._web_code or 1
				if result is _Wait.SHUTDOWN:
					break
				if result is _Wait.BACKEND_EXIT and self.desired == revision:
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
			self._close_ready()
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
		self._backend_code = None
		if self.shutdown.is_set():
			return False
		ready_r, ready_w = os.pipe()
		os.set_inheritable(ready_w, True)
		os.set_inheritable(ready_r, False)
		self._close_ready()
		self._ready_read = ready_r
		env = dict(self.backend_spec.env)
		env[ENV_PULSE_LISTEN_FDS] = ",".join(
			f"{listener.family}:{listener.fileno()}" for listener in self.listeners
		)
		env[ENV_PULSE_READY_FD] = str(ready_w)
		pass_fds = tuple(listener.fileno() for listener in self.listeners) + (ready_w,)
		loop = asyncio.get_running_loop()

		def on_output(line: str) -> None:
			write_tagged_line(self.backend_spec.name, line, self.tag_mode)

		def on_exit(code: int) -> None:
			self._backend_code = code

			def publish() -> None:
				self._backend_exit.set()

			loop.call_soon_threadsafe(publish)

		spec = CommandSpec(
			name=self.backend_spec.name,
			args=self.backend_spec.args,
			cwd=self.backend_spec.cwd,
			env=env,
		)
		self.backend = ManagedProcess.start(
			spec, on_output, on_exit, pass_fds=pass_fds
		)
		os.close(ready_w)
		revision = self.desired
		ready = asyncio.create_task(asyncio.to_thread(os.read, ready_r, 1))
		try:
			while True:
				result = await self._wait_any(
					changed=True,
					backend=True,
					web=True,
					extra=ready,
				)
				if result is _Wait.READY:
					self._close_ready()
					try:
						return ready.result() == b"1"
					except OSError:
						return False
				if result is _Wait.SHUTDOWN or result is _Wait.WEB_EXIT:
					await self._stop(self.backend)
					self.backend = None
					return False
				if result is _Wait.BACKEND_EXIT:
					self._close_ready()
					await self._stop(self.backend)
					self.backend = None
					return False
				if result is _Wait.CHANGED and self.desired != revision:
					await self._stop(self.backend)
					self.backend = None
					return False
		finally:
			if not ready.done():
				self._close_ready()
				with contextlib.suppress(Exception):
					await ready

	async def _start_web(self) -> None:
		assert self.web_spec is not None
		web_spec = self.web_spec
		self._web_exit.clear()
		self._web_code = None
		loop = asyncio.get_running_loop()
		ready = asyncio.Event()

		def on_output(line: str) -> None:
			write_tagged_line(web_spec.name, line, self.tag_mode)
			if (
				web_spec.ready_pattern
				and not ready.is_set()
				and _matches_ready(web_spec.ready_pattern, line)
			):
				ready.set()
				if web_spec.on_ready is not None:
					web_spec.on_ready()

		def on_exit(code: int) -> None:
			self._web_code = code

			def publish() -> None:
				self._web_exit.set()
				if not ready.is_set():
					ready.set()

			loop.call_soon_threadsafe(publish)

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
			env=web_spec.env,
		)
		self.web = ManagedProcess.start(spec, on_output, on_exit)
		ready_task = asyncio.create_task(ready.wait())
		try:
			while not ready.is_set() and not self.shutdown.is_set():
				result = await self._wait_any(web=True, extra=ready_task)
				if result is _Wait.SHUTDOWN or result is _Wait.WEB_EXIT:
					break
		finally:
			if not ready_task.done():
				ready_task.cancel()
				with contextlib.suppress(asyncio.CancelledError):
					await ready_task
		if self._web_code is not None and web_spec.ready_pattern is not None:
			await self._stop(self.web)
			self.web = None

	async def _wait_until_changed(self) -> None:
		while not self.changed.is_set() and not self.shutdown.is_set():
			result = await self._wait_any(changed=True, web=True)
			if result is _Wait.WEB_EXIT or result is _Wait.SHUTDOWN:
				return

	async def _wait_while_running(self, revision: int) -> _Wait:
		while True:
			if self.shutdown.is_set():
				return _Wait.SHUTDOWN
			if self._web_code is not None:
				return _Wait.WEB_EXIT
			if self.desired != revision:
				return _Wait.CHANGED
			if self._backend_exit.is_set():
				return _Wait.BACKEND_EXIT
			result = await self._wait_any(changed=True, backend=True, web=True)
			if result is not _Wait.CHANGED or self.desired != revision:
				return result

	async def _wait_any(
		self,
		*,
		changed: bool = False,
		backend: bool = False,
		web: bool = False,
		extra: asyncio.Task[Any] | None = None,
	) -> _Wait:
		tasks: list[asyncio.Task[Any]] = [
			asyncio.create_task(self.shutdown.wait()),
		]
		kinds = [_Wait.SHUTDOWN]
		if changed:
			tasks.append(asyncio.create_task(self.changed.wait()))
			kinds.append(_Wait.CHANGED)
		if backend:
			tasks.append(asyncio.create_task(self._backend_exit.wait()))
			kinds.append(_Wait.BACKEND_EXIT)
		if web:
			tasks.append(asyncio.create_task(self._web_exit.wait()))
			kinds.append(_Wait.WEB_EXIT)
		if extra is not None:
			tasks.append(extra)
			kinds.append(_Wait.READY)
		try:
			done, _pending = await asyncio.wait(
				tasks, return_when=asyncio.FIRST_COMPLETED
			)
		finally:
			owned = [task for task in tasks if task is not extra]
			for task in owned:
				if not task.done():
					task.cancel()
			await asyncio.gather(*owned, return_exceptions=True)
		for task, kind in zip(tasks, kinds, strict=True):
			if task in done and not task.cancelled():
				return kind
		return _Wait.SHUTDOWN

	async def _watch(self) -> None:
		async for _changes in awatch(
			*self.watch_roots,
			watch_filter=self.filter,
			debounce=300,
			step=50,
		):
			self.desired += 1
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

	def _close_ready(self) -> None:
		if self._ready_read is not None:
			with contextlib.suppress(OSError):
				os.close(self._ready_read)
			self._ready_read = None


def _matches_ready(pattern: str, line: str) -> bool:
	return bool(re.search(pattern, ANSI_ESCAPE.sub("", line)))
