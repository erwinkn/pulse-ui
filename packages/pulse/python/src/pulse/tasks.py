"""Task scopes: an asyncio-hosted anyio task group with a lifetime."""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import Callable, Coroutine
from enum import Enum, auto
from typing import Any, ParamSpec, final

from anyio import Event, TaskHandle, create_task_group, sleep
from anyio.abc import TaskGroup
from anyio.lowlevel import checkpoint

from pulse.runtime import LoopBinding

P = ParamSpec("P")

CLOCK_RESOLUTION = time.get_clock_info("monotonic").resolution


def clamp_delay(delay: float) -> float:
	"""Clamp positive delays because asyncio treats timers within one clock resolution as due."""
	return max(delay, CLOCK_RESOLUTION) if delay > 0 else delay


def is_pytest() -> bool:
	"""Detect if running inside pytest using environment variables."""
	return bool(os.environ.get("PYTEST_CURRENT_TEST")) or (
		"PYTEST_XDIST_TESTRUNUID" in os.environ
	)


class TaskOutcome(Enum):
	"""How a task settled. Reported by ``Task.wait``."""

	COMPLETED = auto()
	CANCELLED = auto()
	FAILED = auto()


@final
class Task:
	"""A unit of work in a TaskScope. Not constructible outside one.

	Failures are reported through the loop's exception handler, not raised to a
	waiter, so ``wait`` never raises for the task's own outcome.
	"""

	__slots__ = ("_handle",)

	def __init__(self, handle: TaskHandle[None]) -> None:
		self._handle = handle

	@property
	def name(self) -> str:
		return self._handle.name

	def cancel(self) -> None:
		self._handle.cancel()

	def done(self) -> bool:
		return self._handle.status in (
			TaskHandle.Status.FINISHED,
			TaskHandle.Status.CANCELLED,
			TaskHandle.Status.FAILED,
		)

	def cancelled(self) -> bool:
		return self._handle.status is TaskHandle.Status.CANCELLED

	async def wait(self) -> TaskOutcome:
		"""Wait for the task to settle, then report how it ended."""
		await self._handle.wait()
		match self._handle.status:
			case TaskHandle.Status.FINISHED:
				return TaskOutcome.COMPLETED
			case TaskHandle.Status.CANCELLED:
				return TaskOutcome.CANCELLED
			case _:
				return TaskOutcome.FAILED


async def _invoke(
	fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
	from pulse.reactive import Untrack

	with Untrack():
		result = fn(*args, **kwargs)
		if inspect.isawaitable(result):
			await result


class TaskScope:
	"""A task lifetime: everything spawned here is cancelled and drained on close."""

	_name: str
	_loop: asyncio.AbstractEventLoop | None
	_tg: TaskGroup | None
	_host: asyncio.Task[None] | None
	_close_requested: Event | None
	_binding: LoopBinding | None

	def __init__(self, name: str) -> None:
		self._name = name
		self._loop = None
		self._tg = None
		self._host = None
		self._close_requested = None
		self._binding = None

	@property
	def name(self) -> str:
		return self._name

	@property
	def running(self) -> bool:
		return self._tg is not None

	@property
	def loop(self) -> asyncio.AbstractEventLoop | None:
		return self._loop

	@property
	def binding(self) -> LoopBinding | None:
		"""The thread-safe bridge onto this scope's loop, once it has started."""
		return self._binding

	async def start(self) -> None:
		if self.running:
			raise RuntimeError(f"task scope {self._name} is already running")

		loop = asyncio.get_running_loop()
		self._loop = loop
		self._binding = LoopBinding(loop)
		self._close_requested = Event()
		ready = asyncio.Event()
		self._host = loop.create_task(self._run(ready), name=f"task-scope:{self._name}")
		await ready.wait()

	async def _run(self, ready: asyncio.Event) -> None:
		async with create_task_group() as tg:
			self._tg = tg
			ready.set()
			assert self._close_requested is not None
			await self._close_requested.wait()
			tg.cancel_scope.cancel()

	async def close(self) -> None:
		"""Cancel every task in this scope and wait for them to finish."""
		if not self.running:
			return
		assert self._close_requested is not None
		assert self._host is not None
		self._close_requested.set()
		try:
			await self._host
		finally:
			self._tg = None
			self._host = None
			self._close_requested = None

	async def __aenter__(self) -> TaskScope:
		await self.start()
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.close()

	def spawn(
		self, coroutine: Coroutine[Any, Any, Any], *, name: str | None = None
	) -> Task:
		"""Run a coroutine in this scope. Its exceptions are reported, not propagated."""
		tg = self._task_group()
		name = name or coroutine.__qualname__
		return Task(tg.create_task(self._guard(coroutine, name), name=name))

	def later(
		self, delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> Task:
		"""Call `fn` once after `delay` seconds."""
		return self.spawn(
			self._delayed(delay, fn, args, dict(kwargs)),
			name=f"later:{_callable_name(fn)}",
		)

	def repeat(
		self, interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> Task:
		"""Call `fn` every `interval` seconds, waiting one interval before the first run."""
		return self.spawn(
			self._repeated(interval, fn, args, dict(kwargs), immediate=False),
			name=f"repeat:{_callable_name(fn)}",
		)

	def every(
		self, interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> Task:
		"""Call `fn` immediately, then every `interval` seconds."""
		return self.spawn(
			self._repeated(interval, fn, args, dict(kwargs), immediate=True),
			name=f"every:{_callable_name(fn)}",
		)

	def _task_group(self) -> TaskGroup:
		tg = self._tg
		if tg is None:
			raise RuntimeError(f"cannot schedule on {self._name}: it is not running")
		if _running_loop() is not self._loop:
			raise RuntimeError(
				f"cannot schedule on {self._name} from outside its event loop"
			)
		return tg

	async def _guard(self, coroutine: Coroutine[Any, Any, Any], name: str) -> None:
		# Honour a cancel() issued before this task first ran.
		try:
			await checkpoint()
		except BaseException:
			coroutine.close()
			raise
		try:
			await coroutine
		except Exception as exc:
			self._report(f"Unhandled exception in task {name}", exc, name)

	async def _delayed(
		self,
		delay: float,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
	) -> None:
		await sleep(clamp_delay(delay))
		await _invoke(fn, args, kwargs)

	async def _repeated(
		self,
		interval: float,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		*,
		immediate: bool,
	) -> None:
		if not immediate:
			await sleep(clamp_delay(interval))
		while True:
			try:
				await _invoke(fn, args, kwargs)
			except Exception as exc:
				self._report(
					f"Unhandled exception in repeat({_callable_name(fn)})", exc, fn
				)
			await sleep(clamp_delay(interval))

	def _report(self, message: str, exception: Exception, callback: Any) -> None:
		assert self._loop is not None
		self._loop.call_exception_handler(
			{
				"message": message,
				"exception": exception,
				"context": {"callback": callback},
			}
		)


def _callable_name(fn: Callable[..., Any]) -> str:
	return getattr(fn, "__qualname__", repr(fn))


def _running_loop() -> asyncio.AbstractEventLoop | None:
	try:
		return asyncio.get_running_loop()
	except RuntimeError:
		return None


def _active_scope() -> TaskScope:
	from pulse.context import PulseContext

	ctx = PulseContext.get()
	if ctx.render is not None:
		return ctx.render.task_scope
	return ctx.app.task_scope


def spawn(coroutine: Coroutine[Any, Any, Any], *, name: str | None = None) -> Task:
	"""Run a coroutine in the active task scope."""
	return _active_scope().spawn(coroutine, name=name)


def later(
	delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> Task:
	"""Schedule a callback after a delay on the active task scope."""
	return _active_scope().later(delay, fn, *args, **kwargs)


def repeat(
	interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> Task:
	"""Repeat a callback on the active task scope, first run after `interval`."""
	return _active_scope().repeat(interval, fn, *args, **kwargs)


def every(
	interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> Task:
	"""Repeat a callback on the active task scope, first run immediately."""
	return _active_scope().every(interval, fn, *args, **kwargs)
