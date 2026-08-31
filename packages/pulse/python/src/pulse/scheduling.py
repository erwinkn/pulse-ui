import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar

from pulse.loop import LoopRef, post

T = TypeVar("T")
P = ParamSpec("P")

CLOCK_RESOLUTION = time.get_clock_info("monotonic").resolution


def clamp_delay(delay: float) -> float:
	"""Clamp positive delays because asyncio treats timers within one clock resolution as due."""
	return max(delay, CLOCK_RESOLUTION) if delay > 0 else delay


class TimerHandleLike(Protocol):
	def cancel(self) -> None: ...
	def cancelled(self) -> bool: ...
	def when(self) -> float: ...


def is_pytest() -> bool:
	"""Detect if running inside pytest using environment variables."""
	return bool(os.environ.get("PYTEST_CURRENT_TEST")) or (
		"PYTEST_XDIST_TESTRUNUID" in os.environ
	)


def _resolve_registries() -> tuple["TaskRegistry", "TimerRegistry"]:
	from pulse.context import PulseContext

	ctx = PulseContext.get()
	if ctx.render is not None:
		return ctx.render._tasks, ctx.render._timers  # pyright: ignore[reportPrivateUsage]
	return ctx.app._tasks, ctx.app._timers  # pyright: ignore[reportPrivateUsage]


def call_soon(
	fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> TimerHandleLike:
	"""Schedule a callback ASAP; supports calls from any thread."""
	_, timer_registry = _resolve_registries()
	return timer_registry.call_soon(fn, *args, **kwargs)


def create_task(
	coroutine: Awaitable[T],
	*,
	name: str | None = None,
	on_done: Callable[[asyncio.Task[T]], None] | None = None,
) -> asyncio.Task[T]:
	"""Create a tracked task; supports calls from any thread."""
	task_registry, _ = _resolve_registries()
	return task_registry.create_task(coroutine, name=name, on_done=on_done)


def later(
	delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> TimerHandleLike:
	"""
	Schedule a callback after `delay`; supports calls from any thread.
	Works with sync or async functions. Returns a handle; call .cancel() to cancel.

	The callback runs with no reactive scope to avoid accidentally capturing
	reactive dependencies from the calling context. Other context vars (like
	PulseContext) are preserved normally.
	"""

	_, timer_registry = _resolve_registries()
	return timer_registry.later(delay, fn, *args, **kwargs)


class RepeatHandle:
	task: asyncio.Task[None] | None
	loop: asyncio.AbstractEventLoop | None
	cancelled: bool

	def __init__(self) -> None:
		self.task = None
		self.loop = None
		self.cancelled = False

	def cancel(self):
		if self.cancelled:
			return
		self.cancelled = True
		task = self.task
		if task is not None and self.loop is not None and not task.done():
			post(self.loop, task.cancel)


def repeat(interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs):
	"""
	Repeat a callback every `interval`; supports calls from any thread.
	Works with sync or async functions.
	For async functions, waits for completion before starting the next delay.
	Returns a handle with .cancel() to stop future runs.

	The callback runs with no reactive scope to avoid accidentally capturing
	reactive dependencies from the calling context. Other context vars (like
	PulseContext) are preserved normally.

	Optional kwargs:
	- immediate: bool = False  # run once immediately before the first interval
	"""

	_, timer_registry = _resolve_registries()
	return timer_registry.repeat(interval, fn, *args, **kwargs)


class TaskRegistry:
	_tasks: set[asyncio.Task[Any]]
	_loop: LoopRef

	def __init__(
		self,
		name: str | None = None,
		*,
		loop: LoopRef | None = None,
	) -> None:
		self._tasks = set()
		self._loop = loop if loop is not None else LoopRef(name)

	@property
	def loop(self) -> LoopRef:
		return self._loop

	def track(self, task: asyncio.Task[T]) -> asyncio.Task[T]:
		self._tasks.add(task)
		task.add_done_callback(self._tasks.discard)
		return task

	def create_task(
		self,
		coroutine: Awaitable[T],
		*,
		name: str | None = None,
		on_done: Callable[[asyncio.Task[T]], None] | None = None,
	) -> asyncio.Task[T]:
		"""Create and schedule a task; supports calls from any thread."""

		def _make(loop: asyncio.AbstractEventLoop) -> asyncio.Task[T]:
			task = asyncio.ensure_future(coroutine, loop=loop)
			if name is not None:
				task.set_name(name)
			if on_done:
				task.add_done_callback(on_done)
			return self.track(task)

		return self._loop.run(_make)

	def cancel_all(self) -> None:
		for task in list(self._tasks):
			if not task.done():
				task.cancel()
		self._tasks.clear()


class TimerRegistry:
	_handles: set[TimerHandleLike]
	_tasks: TaskRegistry

	def __init__(self, *, tasks: TaskRegistry) -> None:
		self._handles = set()
		self._tasks = tasks

	def track(self, handle: TimerHandleLike) -> TimerHandleLike:
		self._handles.add(handle)
		return handle

	def discard(self, handle: TimerHandleLike | None) -> None:
		if handle is None:
			return
		self._handles.discard(handle)

	def later(
		self,
		delay: float,
		fn: Callable[P, Any],
		*args: P.args,
		**kwargs: P.kwargs,
	) -> TimerHandleLike:
		return self._tasks.loop.run(
			lambda loop: self._start(loop, delay, fn, args, dict(kwargs), untrack=True)
		)

	def call_soon(
		self, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> TimerHandleLike:
		return self._tasks.loop.run(
			lambda loop: self._start(loop, None, fn, args, dict(kwargs), untrack=False)
		)

	def repeat(
		self, interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> RepeatHandle:
		from pulse.reactive import Untrack

		handle = RepeatHandle()

		async def _runner():
			nonlocal handle
			try:
				while not handle.cancelled:
					# Start counting the next interval AFTER the previous execution completes
					await asyncio.sleep(clamp_delay(interval))
					if handle.cancelled:
						break
					try:
						with Untrack():
							result = fn(*args, **kwargs)
							if asyncio.iscoroutine(result):
								await result
					except asyncio.CancelledError:
						# Propagate to outer handler to finish cleanly
						raise
					except Exception as exc:
						# Surface exceptions via the loop's exception handler and continue
						asyncio.get_running_loop().call_exception_handler(
							{
								"message": "Unhandled exception in repeat() callback",
								"exception": exc,
								"context": {"callback": fn},
							}
						)
			except asyncio.CancelledError:
				# Swallow task cancellation to avoid noisy "exception was never retrieved"
				pass

		coroutine = _runner()
		try:
			handle.task = self._tasks.create_task(coroutine)
		except BaseException:
			coroutine.close()
			raise
		handle.loop = handle.task.get_loop()
		return handle

	def cancel_all(self) -> None:
		for handle in list(self._handles):
			handle.cancel()
		self._handles.clear()

	def _start(
		self,
		loop: asyncio.AbstractEventLoop,
		delay: float | None,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		*,
		untrack: bool,
	) -> TimerHandleLike:
		"""
		Run the loop-side half of `later` or `call_soon`; `delay=None` uses
		`call_soon`.
		Works with sync or async functions. Returns a TimerHandle; call .cancel() to cancel.

		The callback can run without a reactive scope to avoid accidentally capturing
		reactive dependencies from the calling context. Other context vars (like
		PulseContext) are preserved normally.
		"""

		tracked = _TrackedHandle(self, loop=loop)
		run = self._prepare_run(loop, tracked, fn, args, kwargs, untrack=untrack)
		if delay is None:
			tracked.attach(loop.call_soon(run), loop.time())
		else:
			timer = loop.call_later(clamp_delay(delay), run)
			tracked.attach(timer, timer.when())
		self._handles.add(tracked)
		return tracked

	def _prepare_run(
		self,
		loop: asyncio.AbstractEventLoop,
		tracked: TimerHandleLike,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		*,
		untrack: bool,
	) -> Callable[[], None]:
		def _run():
			from pulse.reactive import Untrack

			try:
				if tracked.cancelled():
					return
				if untrack:
					with Untrack():
						res = fn(*args, **kwargs)
				else:
					res = fn(*args, **kwargs)
				if asyncio.iscoroutine(res):
					task = self._tasks.create_task(res)

					def _log_task_exception(t: asyncio.Task[Any]):
						try:
							t.result()
						except asyncio.CancelledError:
							# Normal cancellation path
							pass
						except Exception as exc:
							loop.call_exception_handler(
								{
									"message": "Unhandled exception in later() task",
									"exception": exc,
									"context": {"callback": fn},
								}
							)

					task.add_done_callback(_log_task_exception)
			except Exception as exc:
				# Surface exceptions via the loop's exception handler and continue
				loop.call_exception_handler(
					{
						"message": "Unhandled exception in later() callback",
						"exception": exc,
						"context": {"callback": fn},
					}
				)
			finally:
				self.discard(tracked)

		return _run


class _TrackedHandle:
	__slots__: tuple[str, ...] = (
		"_handle",
		"_registry",
		"_loop",
		"_when",
		"_cancelled",
	)
	_handle: asyncio.Handle | asyncio.TimerHandle | None
	_registry: "TimerRegistry"
	_loop: asyncio.AbstractEventLoop
	_when: float
	_cancelled: bool

	def __init__(
		self,
		registry: "TimerRegistry",
		*,
		loop: asyncio.AbstractEventLoop,
	) -> None:
		self._handle = None
		self._registry = registry
		self._loop = loop
		self._when = 0.0
		self._cancelled = False

	def attach(self, handle: asyncio.Handle | asyncio.TimerHandle, when: float) -> None:
		self._handle = handle
		self._when = when

	def cancel(self) -> None:
		if self._cancelled:
			return
		self._cancelled = True
		post(self._loop, self._finish_cancel)

	def _finish_cancel(self) -> None:
		if self._handle is not None and not self._handle.cancelled():
			self._handle.cancel()
		self._registry.discard(self)

	def cancelled(self) -> bool:
		return self._cancelled or (
			self._handle is not None and self._handle.cancelled()
		)

	def when(self) -> float:
		return self._when
