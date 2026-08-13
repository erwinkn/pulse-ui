from __future__ import annotations

import asyncio
import contextlib
import secrets
import signal
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, cast, final

from aiohttp import web as aiohttp_web
from watchfiles import Change, awatch

from pulse.cli.logging import TagMode
from pulse.cli.models import CommandSpec
from pulse.cli.processes import (
	PROCESS_KILL_TIMEOUT,
	PROCESS_STOP_TIMEOUT,
	ManagedProcess,
	write_tagged_line,
)
from pulse.cli.relay import PortReservation, TcpRelay
from pulse.env import (
	ENV_PULSE_BACKEND_INSTANCE,
	ENV_PULSE_BACKEND_LIFECYCLE_SECRET,
	ENV_PULSE_BACKEND_LIFECYCLE_URL,
	ENV_PULSE_VITE_INSTANCE,
	ENV_PULSE_VITE_LIFECYCLE_SECRET,
	ENV_PULSE_VITE_LIFECYCLE_URL,
)

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
STOP_TIMEOUT = PROCESS_STOP_TIMEOUT
KILL_TIMEOUT = PROCESS_KILL_TIMEOUT
VITE_START_TIMEOUT = 15.0
LIFECYCLE_MAX_BODY = 2 * 1024 * 1024


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
		# Ignored directory names only count below a watch root, so an app that
		# happens to live under an ancestor named "build" or "venv" still reloads.
		return any(
			path.is_relative_to(root)
			and not any(
				part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts
			)
			for root in self.application_roots
		)


class _StackResult(Enum):
	CHANGED = auto()
	SHUTDOWN = auto()
	BACKEND_FAILED = auto()
	WEB_FAILED = auto()


class _Marker(Enum):
	PREPARED = auto()
	READY = auto()


@dataclass(slots=True)
class _ProcessState:
	exited: asyncio.Future[_ExitEvent]
	token: object = field(default_factory=object)
	prepared: bool = False
	ready: bool = False
	vite_sequence: int = 0
	port: int | None = None
	sources: list[str] = field(default_factory=list)

	def saw(self, marker: _Marker) -> bool:
		if marker is _Marker.PREPARED:
			return self.prepared
		return self.ready


@dataclass(slots=True)
class _Stack:
	backend: ManagedProcess
	backend_state: _ProcessState
	backend_instance: str
	web: ManagedProcess | None = None
	web_state: _ProcessState | None = None
	web_instance: str | None = None


@dataclass(frozen=True, slots=True)
class _ExitEvent:
	token: object
	spec: CommandSpec
	code: int


@dataclass(frozen=True, slots=True)
class _ViteLifecycleEvent:
	instance: str
	event: str
	sequence: int
	port: int | None


@dataclass(frozen=True, slots=True)
class _BackendLifecycleEvent:
	instance: str
	event: str
	sources: list[str]
	port: int | None


type _SupervisorEvent = _ExitEvent | _ViteLifecycleEvent | _BackendLifecycleEvent


@final
class _LifecycleServer:
	def __init__(
		self,
		on_vite_event: Callable[[_ViteLifecycleEvent], None],
		on_backend_event: Callable[[_BackendLifecycleEvent], None],
	) -> None:
		self._on_vite_event = on_vite_event
		self._on_backend_event = on_backend_event
		self._secret = secrets.token_urlsafe(32)
		self._runner: aiohttp_web.AppRunner | None = None
		self.url: str | None = None

	async def start(self) -> None:
		app = aiohttp_web.Application(client_max_size=LIFECYCLE_MAX_BODY)
		app.router.add_post("/vite", self._handle_vite)
		app.router.add_post("/backend", self._handle_backend)
		self._runner = aiohttp_web.AppRunner(app, access_log=None)
		await self._runner.setup()
		site = aiohttp_web.TCPSite(self._runner, "127.0.0.1", 0)
		await site.start()
		addresses = self._runner.addresses
		if len(addresses) != 1:
			raise RuntimeError("Expected one lifecycle listener")
		self.url = f"http://127.0.0.1:{addresses[0][1]}/vite"

	async def close(self) -> None:
		if self._runner is not None:
			await self._runner.cleanup()
			self._runner = None
		self.url = None

	def configure_vite(self, environment: dict[str, str]) -> str:
		if self.url is None:
			raise RuntimeError("Lifecycle listener is not running")
		instance = secrets.token_urlsafe(18)
		environment.update(
			{
				ENV_PULSE_VITE_LIFECYCLE_URL: self.url,
				ENV_PULSE_VITE_LIFECYCLE_SECRET: self._secret,
				ENV_PULSE_VITE_INSTANCE: instance,
			}
		)
		return instance

	def configure_backend(self, environment: dict[str, str]) -> str:
		if self.url is None:
			raise RuntimeError("Lifecycle listener is not running")
		instance = secrets.token_urlsafe(18)
		environment.update(
			{
				ENV_PULSE_BACKEND_LIFECYCLE_URL: self.url.replace("/vite", "/backend"),
				ENV_PULSE_BACKEND_LIFECYCLE_SECRET: self._secret,
				ENV_PULSE_BACKEND_INSTANCE: instance,
			}
		)
		return instance

	async def _payload(self, request: aiohttp_web.Request) -> dict[str, object]:
		authorization = request.headers.get("Authorization", "")
		if not secrets.compare_digest(authorization, f"Bearer {self._secret}"):
			raise aiohttp_web.HTTPUnauthorized()
		try:
			payload = await request.json()
		except (ValueError, TypeError):
			raise aiohttp_web.HTTPBadRequest() from None
		if not isinstance(payload, dict):
			raise aiohttp_web.HTTPBadRequest()
		return cast(dict[str, object], payload)

	async def _handle_vite(self, request: aiohttp_web.Request) -> aiohttp_web.Response:
		payload = await self._payload(request)
		event = payload.get("event")
		instance = payload.get("instance")
		sequence = payload.get("sequence")
		port = payload.get("port")
		if event not in ("configured", "listening", "closed"):
			raise aiohttp_web.HTTPBadRequest()
		if not isinstance(instance, str):
			raise aiohttp_web.HTTPBadRequest()
		if type(sequence) is not int or sequence <= 0:
			raise aiohttp_web.HTTPBadRequest()
		if port is not None and (type(port) is not int or port <= 0):
			raise aiohttp_web.HTTPBadRequest()
		if event == "listening" and port is None:
			raise aiohttp_web.HTTPBadRequest()
		if event == "configured" and port is not None:
			raise aiohttp_web.HTTPBadRequest()
		self._on_vite_event(_ViteLifecycleEvent(instance, event, sequence, port))
		return aiohttp_web.Response(status=204)

	async def _handle_backend(
		self, request: aiohttp_web.Request
	) -> aiohttp_web.Response:
		payload = await self._payload(request)
		event = payload.get("event")
		instance = payload.get("instance")
		sources = payload.get("sources", [])
		port = payload.get("port")
		if event not in ("prepared", "ready") or not isinstance(instance, str):
			raise aiohttp_web.HTTPBadRequest()
		if event == "prepared":
			if not isinstance(sources, list) or not all(
				isinstance(source, str) for source in sources
			):
				raise aiohttp_web.HTTPBadRequest()
			if port is not None:
				raise aiohttp_web.HTTPBadRequest()
		elif sources != [] or type(port) is not int or port <= 0:
			raise aiohttp_web.HTTPBadRequest()
		self._on_backend_event(
			_BackendLifecycleEvent(instance, event, cast(list[str], sources), port)
		)
		return aiohttp_web.Response(status=204)


@final
class DevSupervisor:
	"""Restart Uvicorn and Vite as one development stack."""

	def __init__(
		self,
		*,
		backend: CommandSpec,
		web: CommandSpec | None,
		watch_roots: tuple[Path, ...],
		ignored_roots: tuple[Path, ...],
		registered_sources: set[Path],
		tag_mode: TagMode,
		public_port: PortReservation | None = None,
		vite_port: PortReservation | None = None,
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
		self.public_relay = TcpRelay(public_port) if public_port is not None else None
		self.vite_relay = TcpRelay(vite_port) if vite_port is not None else None
		self.web_first = web_first
		self.desired = 0
		self.changed = asyncio.Event()
		self.shutdown = asyncio.Event()
		self._kill_now = asyncio.Event()
		self._interrupt_count = 0
		self._current: _Stack | None = None
		self._starting: _Stack | None = None
		self._events: asyncio.Queue[_SupervisorEvent] = asyncio.Queue()
		self._states: dict[str, _ProcessState] = {}
		self._backend_instance: str | None = None
		self._vite_instance: str | None = None
		self._lifecycle = _LifecycleServer(
			self._notify_vite_lifecycle,
			self._notify_backend_lifecycle,
		)
		self._add_watch_sources([str(source) for source in registered_sources])

	@property
	def backend(self) -> ManagedProcess | None:
		stack = self._starting or self._current
		return None if stack is None else stack.backend

	@property
	def web(self) -> ManagedProcess | None:
		stack = self._starting or self._current
		return None if stack is None else stack.web

	async def run(self) -> int:
		loop = asyncio.get_running_loop()
		previous_handlers: dict[int, object] = {}

		def request_shutdown(_signum: int, _frame: object) -> None:
			self._interrupt_count += 1
			loop.call_soon_threadsafe(self._handle_interrupt)

		for signum in (signal.SIGINT, signal.SIGTERM):
			previous_handlers[signum] = signal.signal(signum, request_shutdown)

		watch_task: asyncio.Task[None] | None = None
		try:
			await self._lifecycle.start()
			if self.public_relay is not None:
				await self.public_relay.start()
			if self.vite_relay is not None:
				await self.vite_relay.start()
			watch_task = asyncio.create_task(self._watch())
			self.desired = 1
			self.changed.set()
			while not self.shutdown.is_set():
				await self._wait_for_restart()
				if self.shutdown.is_set():
					break
				revision = self.desired
				self.changed.clear()
				if self.desired != revision:
					self.changed.set()
					continue

				result, watch_task = await self._start_stack(revision, watch_task)
				if result is _StackResult.CHANGED:
					await self._stop_stack(self._starting)
					self._starting = None
					self.changed.set()
					continue
				if result is _StackResult.SHUTDOWN:
					break
				if result is _StackResult.WEB_FAILED:
					code = self._failed_code(self._starting, web=True)
					await self._stop_stack(self._starting)
					self._starting = None
					if self._current is not None:
						print(
							"Reload error: web dev server failed to start. "
							+ "Keeping the previous stack. Waiting for changes...",
							flush=True,
						)
						continue
					if code is None:
						print("Web dev server stopped listening.", flush=True)
					else:
						print(f"Web dev server exited with code {code}.", flush=True)
					return code or 1

				if result is _StackResult.BACKEND_FAILED:
					code = self._failed_code(self._starting, web=False)
					await self._stop_stack(self._starting)
					self._starting = None
					print(
						f"Reload error: backend exited with code {code}. "
						+ "Waiting for changes to restart...",
						flush=True,
					)
					continue

				old = self._current
				self._current = self._starting
				self._starting = None
				await self._stop_stack(old)

				result = await self._wait_while_running(revision)
				if result is _StackResult.CHANGED:
					self.changed.set()
					continue
				if result is _StackResult.SHUTDOWN:
					break
				if result is _StackResult.WEB_FAILED:
					assert self._current is not None
					code = self._current.web.returncode if self._current.web else None
					if code is None:
						print("Web dev server stopped listening.", flush=True)
					else:
						print(f"Web dev server exited with code {code}.", flush=True)
					return code or 1

				assert result is _StackResult.BACKEND_FAILED
				code = self._current.backend.returncode if self._current else None
				print(
					f"Reload error: backend exited with code {code}. "
					+ "Waiting for changes to restart...",
					flush=True,
				)
				if self.public_relay is not None:
					self.public_relay.clear_target()
				if self.vite_relay is not None:
					self.vite_relay.clear_target()
				await self._stop_stack(self._current)
				self._current = None
			return 130 if self.shutdown.is_set() else 0
		finally:
			if watch_task is not None:
				watch_task.cancel()
				with contextlib.suppress(asyncio.CancelledError):
					await watch_task
			if self.public_relay is not None:
				self.public_relay.clear_target()
			if self.vite_relay is not None:
				self.vite_relay.clear_target()
			await self._stop_stack(self._starting)
			self._starting = None
			await self._stop_stack(self._current)
			self._current = None
			if self.vite_relay is not None:
				await self.vite_relay.close()
			if self.public_relay is not None:
				await self.public_relay.close()
			await self._lifecycle.close()
			for signum, handler in previous_handlers.items():
				signal.signal(signum, cast(Any, handler))

	def _handle_interrupt(self) -> None:
		self.shutdown.set()
		if self._interrupt_count >= 2:
			self._kill_now.set()
			self._kill_all_trees()

	def _kill_all_trees(self) -> None:
		for stack in (self._starting, self._current):
			if stack is None:
				continue
			for process in (stack.web, stack.backend):
				if process is not None:
					process.kill_tree()

	@staticmethod
	def _failed_code(stack: _Stack | None, *, web: bool) -> int | None:
		if stack is None:
			return None
		process = stack.web if web else stack.backend
		return None if process is None else process.returncode

	async def _start_stack(
		self,
		revision: int,
		watch_task: asyncio.Task[None],
	) -> tuple[_StackResult | None, asyncio.Task[None]]:
		backend_instance = self._lifecycle.configure_backend(self.backend_spec.env)
		backend, backend_state = self._start(self.backend_spec)
		self._backend_instance = backend_instance
		self._starting = _Stack(
			backend=backend,
			backend_state=backend_state,
			backend_instance=backend_instance,
		)
		result = await self._wait_until(
			backend_state,
			revision,
			_Marker.PREPARED,
			self._live_processes(self._starting),
		)
		if result is not None:
			return result, watch_task

		if self._add_watch_sources(backend_state.sources):
			watch_task = await self._restart_watch(watch_task)

		if self.web_first and self.web_spec is not None:
			result = await self._start_web(revision)
			if result is not None:
				return result, watch_task

		try:
			backend.send_line("serve")
		except OSError:
			# The worker died between "prepared" and this write; its exit event
			# may still be in flight.
			return _StackResult.BACKEND_FAILED, watch_task
		result = await self._wait_until(
			backend_state,
			revision,
			_Marker.READY,
			self._live_processes(self._starting),
		)
		if result is not None:
			return result, watch_task
		if self.backend_spec.on_ready is not None:
			self.backend_spec.on_ready()

		if not self.web_first and self.web_spec is not None:
			result = await self._start_web(revision)
			if result is not None:
				return result, watch_task

		assert self._starting is not None
		self._publish_targets(self._starting)
		return None, watch_task

	async def _start_web(self, revision: int) -> _StackResult | None:
		assert self.web_spec is not None
		assert self._starting is not None
		vite_instance = self._lifecycle.configure_vite(self.web_spec.env)
		process, state = self._start(self.web_spec)
		self._vite_instance = vite_instance
		self._starting.web = process
		self._starting.web_state = state
		self._starting.web_instance = vite_instance
		# The plugin reports "configured" as soon as Vite resolves its config, so
		# only its absence is bounded by a timeout. A configured server may take
		# arbitrarily long to listen (cold caches, slow machines); that wait is
		# unbounded but stays interruptible through edits and shutdown.
		try:
			result = await asyncio.wait_for(
				self._wait_until(
					state,
					revision,
					_Marker.PREPARED,
					self._live_processes(self._starting),
				),
				timeout=VITE_START_TIMEOUT,
			)
		except TimeoutError:
			write_tagged_line(
				self.web_spec.name,
				"The Pulse Vite plugin did not respond. Add "
				+ 'pulseVitePlugin() from "pulse-ui-client/vite" to vite.config.ts.',
				self.tag_mode,
			)
			return _StackResult.WEB_FAILED
		if result is not None:
			return result
		result = await self._wait_until(
			state,
			revision,
			_Marker.READY,
			self._live_processes(self._starting),
		)
		if result is None and self.web_spec.on_ready is not None:
			self.web_spec.on_ready()
		return result

	async def _wait_until(
		self,
		state: _ProcessState,
		revision: int,
		marker: _Marker,
		processes: tuple[tuple[ManagedProcess, _ProcessState, _StackResult], ...],
	) -> _StackResult | None:
		while True:
			if result := await self._terminal_result(revision, processes):
				return result
			if state.saw(marker):
				return None
			await self._wait_for_event()

	async def _wait_while_running(self, revision: int) -> _StackResult:
		while True:
			if result := await self._terminal_result(
				revision, self._live_processes(self._current)
			):
				return result
			await self._wait_for_event()

	def _live_processes(
		self,
		stack: _Stack | None,
	) -> tuple[tuple[ManagedProcess, _ProcessState, _StackResult], ...]:
		if stack is None:
			return ()
		processes: list[tuple[ManagedProcess, _ProcessState, _StackResult]] = [
			(stack.backend, stack.backend_state, _StackResult.BACKEND_FAILED)
		]
		if stack.web is not None and stack.web_state is not None:
			processes.append((stack.web, stack.web_state, _StackResult.WEB_FAILED))
		return tuple(processes)

	async def _terminal_result(
		self,
		revision: int,
		processes: tuple[tuple[ManagedProcess, _ProcessState, _StackResult], ...],
	) -> _StackResult | None:
		if self.shutdown.is_set():
			return _StackResult.SHUTDOWN
		if self.desired != revision:
			return _StackResult.CHANGED
		for process, state, result in processes:
			if state.exited.done() or not process.is_alive():
				await self._drain_events()
				return result
		return None

	async def _wait_for_restart(self) -> None:
		while not self.changed.is_set() and not self.shutdown.is_set():
			await self._wait_for_event()

	async def _wait_for_event(self) -> None:
		event = asyncio.create_task(self._events.get())
		changed = asyncio.create_task(self.changed.wait())
		shutdown = asyncio.create_task(self.shutdown.wait())
		kill_now = asyncio.create_task(self._kill_now.wait())
		tasks = (event, changed, shutdown, kill_now)
		try:
			await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
		finally:
			for task in tasks:
				if not task.done():
					task.cancel()
			await asyncio.gather(*tasks, return_exceptions=True)
		if event.done() and not event.cancelled():
			self._handle_event(event.result())
			await self._drain_events()

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

	async def _restart_watch(
		self, watch_task: asyncio.Task[None]
	) -> asyncio.Task[None]:
		watch_task.cancel()
		with contextlib.suppress(asyncio.CancelledError):
			await watch_task
		return asyncio.create_task(self._watch())

	def _add_watch_sources(self, sources: list[str]) -> bool:
		self.filter.add_sources(sources)
		roots = list(self.watch_roots)
		changed = False
		for source in sources:
			parent = Path(source).resolve().parent
			if any(parent == root or parent.is_relative_to(root) for root in roots):
				continue
			roots.append(parent)
			changed = True
		if changed:
			self.watch_roots = tuple(roots)
		return changed

	def _start(self, spec: CommandSpec) -> tuple[ManagedProcess, _ProcessState]:
		loop = asyncio.get_running_loop()
		state = _ProcessState(loop.create_future())
		self._states[spec.name] = state

		def on_output(line: str) -> None:
			write_tagged_line(spec.name, line, self.tag_mode)

		def on_exit(code: int) -> None:
			if not loop.is_closed():
				event = _ExitEvent(state.token, spec, code)

				def publish() -> None:
					if not state.exited.done():
						state.exited.set_result(event)
					self._events.put_nowait(event)

				loop.call_soon_threadsafe(publish)

		return ManagedProcess.start(spec, on_output, on_exit), state

	def _notify_vite_lifecycle(self, event: _ViteLifecycleEvent) -> None:
		self._events.put_nowait(event)

	def _notify_backend_lifecycle(self, event: _BackendLifecycleEvent) -> None:
		self._events.put_nowait(event)

	async def _drain_events(self) -> None:
		while not self._events.empty():
			self._handle_event(self._events.get_nowait())

	def _vite_state(self, instance: str) -> _ProcessState | None:
		for stack in (self._starting, self._current):
			if stack is not None and stack.web_instance == instance:
				return stack.web_state
		if instance == self._vite_instance and self.web_spec is not None:
			return self._states.get(self.web_spec.name)
		return None

	def _backend_state(self, instance: str) -> _ProcessState | None:
		for stack in (self._starting, self._current):
			if stack is not None and stack.backend_instance == instance:
				return stack.backend_state
		if instance == self._backend_instance:
			return self._states.get(self.backend_spec.name)
		return None

	def _handle_event(self, event: _SupervisorEvent) -> None:
		if isinstance(event, _ViteLifecycleEvent):
			state = self._vite_state(event.instance)
			if state is None or event.sequence <= state.vite_sequence:
				return
			state.vite_sequence = event.sequence
			if event.event == "configured":
				state.prepared = True
				return
			if event.event == "closed":
				state.ready = False
				if (
					self.vite_relay is not None
					and state.port is not None
					and self.vite_relay.target == ("127.0.0.1", state.port)
				):
					self.vite_relay.clear_target()
				return
			assert event.port is not None
			state.port = event.port
			state.prepared = True
			state.ready = True
			if not self._defer_retarget(event.instance, web=True):
				self._publish_vite(state.port)
			return
		if isinstance(event, _BackendLifecycleEvent):
			state = self._backend_state(event.instance)
			if state is None:
				return
			if event.event == "prepared":
				state.sources = event.sources
				state.prepared = True
			else:
				assert event.port is not None
				state.port = event.port
				state.ready = True
				if not self._defer_retarget(event.instance, web=False):
					self._publish_backend(state.port)
			return

	def _defer_retarget(self, instance: str, *, web: bool) -> bool:
		# Keep the live stack on the relays until the replacement is fully ready.
		if self._current is None or self._starting is None:
			return False
		if web:
			return self._starting.web_instance == instance
		return self._starting.backend_instance == instance

	def _publish_backend(self, port: int) -> None:
		if self.public_relay is not None:
			self.public_relay.set_target("127.0.0.1", port)

	def _publish_vite(self, port: int) -> None:
		if self.vite_relay is not None:
			self.vite_relay.set_target("127.0.0.1", port)

	def _publish_targets(self, stack: _Stack) -> None:
		if stack.backend_state.port is not None:
			self._publish_backend(stack.backend_state.port)
		if stack.web_state is not None and stack.web_state.port is not None:
			self._publish_vite(stack.web_state.port)

	async def _stop_stack(self, stack: _Stack | None) -> None:
		if stack is None:
			return
		owned = [process for process in (stack.web, stack.backend) if process]
		stop_order = (
			(stack.backend, stack.web) if self.web_first else (stack.web, stack.backend)
		)
		for process in stop_order:
			if process is not None:
				process.request_stop()
		await asyncio.gather(
			*(self._wait_until_stopped(process, STOP_TIMEOUT) for process in owned)
		)
		for process in owned:
			process.kill_tree()
		await asyncio.gather(
			*(self._wait_until_stopped(process, KILL_TIMEOUT) for process in owned)
		)
		for process in owned:
			process.close()
		await self._drain_events()

	async def _wait_until_stopped(
		self, process: ManagedProcess, timeout: float
	) -> None:
		loop = asyncio.get_running_loop()
		deadline = loop.time() + timeout
		while process.is_alive():
			if self._kill_now.is_set():
				return
			remaining = deadline - loop.time()
			if remaining <= 0:
				return
			try:
				await asyncio.wait_for(
					self._kill_now.wait(), timeout=min(0.01, remaining)
				)
				return
			except TimeoutError:
				pass
		await self._drain_events()
