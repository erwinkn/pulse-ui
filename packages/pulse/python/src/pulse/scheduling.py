import asyncio
import concurrent.futures
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, override

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


def run_on_loop(loop: asyncio.AbstractEventLoop, fn: Callable[[], T]) -> T:
	"""
	Run `fn` on `loop`'s thread and return its result.
	Blocks the calling thread; only called from a thread with no event loop,
	so it cannot deadlock on itself.
	"""
	future: concurrent.futures.Future[T] = concurrent.futures.Future()

	def _run() -> None:
		try:
			future.set_result(fn())
		except BaseException as exc:
			future.set_exception(exc)

	loop.call_soon_threadsafe(_run)
	return future.result()


def _loop_for_this_thread() -> asyncio.AbstractEventLoop | None:
	try:
		return asyncio.get_running_loop()
	except RuntimeError:
		try:
			return asyncio.get_event_loop()
		except RuntimeError:
			return None


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
		if self.task is not None and not self.task.done():
			if _loop_for_this_thread() is None and self.loop is not None:
				self.loop.call_soon_threadsafe(self.task.cancel)
			else:
				self.task.cancel()


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
	name: str | None
	_loop: asyncio.AbstractEventLoop | None

	def __init__(self, name: str | None = None) -> None:
		self._tasks = set()
		self.name = name
		try:
			self._loop = asyncio.get_running_loop()
		except RuntimeError:
			self._loop = None

	def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
		self._loop = loop

	def _require_loop(self) -> asyncio.AbstractEventLoop:
		if self._loop is None:
			name = self.name or "unnamed"
			raise RuntimeError(
				f"cannot schedule from a thread with no event loop: {name} registry has no bound loop"
			)
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

		def _make_task() -> asyncio.Task[T]:
			task = asyncio.ensure_future(coroutine)
			if name is not None:
				task.set_name(name)
			if on_done:
				task.add_done_callback(on_done)
			return self.track(task)

		loop = _loop_for_this_thread()
		if loop is None:
			return run_on_loop(self._require_loop(), _make_task)
		if loop.is_running():
			self._loop = loop
		return _make_task()

	def cancel_all(self) -> None:
		for task in list(self._tasks):
			if not task.done():
				task.cancel()
		self._tasks.clear()


class TimerRegistry:
	_handles: set[TimerHandleLike]
	_tasks: TaskRegistry
	name: str | None

	def __init__(self, *, tasks: TaskRegistry, name: str | None = None) -> None:
		self._handles = set()
		self._tasks = tasks
		self.name = name

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
		return self._schedule(delay, fn, args, dict(kwargs), untrack=True)

	def call_soon(
		self, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> TimerHandleLike:
		loop = _loop_for_this_thread()
		if loop is None:
			loop = self._tasks._require_loop()  # pyright: ignore[reportPrivateUsage]
			return run_on_loop(
				loop, lambda: self._schedule_soon(loop, fn, args, dict(kwargs))
			)
		return self._schedule_soon(loop, fn, args, dict(kwargs))

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

	def _schedule(
		self,
		delay: float,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		*,
		untrack: bool,
	) -> TimerHandleLike:
		"""
		Schedule a callback after `delay`; supports calls from any thread.
		Works with sync or async functions. Returns a TimerHandle; call .cancel() to cancel.

		The callback can run without a reactive scope to avoid accidentally capturing
		reactive dependencies from the calling context. Other context vars (like
		PulseContext) are preserved normally.
		"""

		def _schedule_on_loop(loop: asyncio.AbstractEventLoop) -> TimerHandleLike:
			tracked_box: list[TimerHandleLike] = []
			run = self._prepare_run(
				loop,
				tracked_box,
				fn,
				args,
				kwargs,
				untrack=untrack,
			)
			handle = loop.call_later(clamp_delay(delay), run)
			tracked = _TrackedTimerHandle(handle, self, loop=loop)
			tracked_box.append(tracked)
			self._handles.add(tracked)
			if loop.is_running():
				self._tasks.bind_loop(loop)
			return tracked

		loop = _loop_for_this_thread()
		if loop is None:
			loop = self._tasks._require_loop()  # pyright: ignore[reportPrivateUsage]
			return run_on_loop(loop, lambda: _schedule_on_loop(loop))
		return _schedule_on_loop(loop)

	def _schedule_soon(
		self,
		loop: asyncio.AbstractEventLoop,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
	) -> TimerHandleLike:
		tracked_box: list[TimerHandleLike] = []
		_run = self._prepare_run(loop, tracked_box, fn, args, kwargs, untrack=False)

		handle = loop.call_soon(_run)
		tracked = _TrackedHandle(handle, self, loop=loop, when=loop.time())
		tracked_box.append(tracked)
		self._handles.add(tracked)
		if loop.is_running():
			self._tasks.bind_loop(loop)
		return tracked

	def _prepare_run(
		self,
		loop: asyncio.AbstractEventLoop,
		tracked_box: list[TimerHandleLike],
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		*,
		untrack: bool,
	) -> Callable[[], None]:
		def _run():
			from pulse.reactive import Untrack

			tracked = tracked_box[0] if tracked_box else None
			try:
				if tracked is not None and tracked.cancelled():
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


class _TrackedTimerHandle:
	__slots__: tuple[str, ...] = ("_handle", "_registry", "_loop", "_cancelled")
	_handle: asyncio.TimerHandle
	_registry: "TimerRegistry"
	_loop: asyncio.AbstractEventLoop
	_cancelled: bool

	def __init__(
		self,
		handle: asyncio.TimerHandle,
		registry: "TimerRegistry",
		*,
		loop: asyncio.AbstractEventLoop,
	) -> None:
		self._handle = handle
		self._registry = registry
		self._loop = loop
		self._cancelled = False

	def cancel(self) -> None:
		if self._cancelled:
			return
		self._cancelled = True
		if _loop_for_this_thread() is None:
			self._loop.call_soon_threadsafe(self._finish_cancel)
		else:
			self._finish_cancel()

	def _finish_cancel(self) -> None:
		if not self._handle.cancelled():
			self._handle.cancel()
		self._registry.discard(self)

	def cancelled(self) -> bool:
		return self._cancelled or self._handle.cancelled()

	def when(self) -> float:
		return self._handle.when()

	def __getattr__(self, name: str):
		return getattr(self._handle, name)

	@override
	def __hash__(self) -> int:
		return hash(self._handle)

	@override
	def __eq__(self, other: object) -> bool:
		if isinstance(other, _TrackedTimerHandle):
			return self._handle is other._handle
		return self._handle is other


class _TrackedHandle:
	__slots__: tuple[str, ...] = (
		"_handle",
		"_registry",
		"_loop",
		"_when",
		"_cancelled",
	)
	_handle: asyncio.Handle
	_registry: "TimerRegistry"
	_loop: asyncio.AbstractEventLoop
	_when: float
	_cancelled: bool

	def __init__(
		self,
		handle: asyncio.Handle,
		registry: "TimerRegistry",
		*,
		loop: asyncio.AbstractEventLoop,
		when: float,
	) -> None:
		self._handle = handle
		self._registry = registry
		self._loop = loop
		self._when = when
		self._cancelled = False

	def cancel(self) -> None:
		if self._cancelled:
			return
		self._cancelled = True
		if _loop_for_this_thread() is None:
			self._loop.call_soon_threadsafe(self._finish_cancel)
		else:
			self._finish_cancel()

	def _finish_cancel(self) -> None:
		if not self._handle.cancelled():
			self._handle.cancel()
		self._registry.discard(self)

	def cancelled(self) -> bool:
		return self._cancelled or self._handle.cancelled()

	def when(self) -> float:
		return self._when

	def __getattr__(self, name: str):
		return getattr(self._handle, name)

	@override
	def __hash__(self) -> int:
		return hash(self._handle)

	@override
	def __eq__(self, other: object) -> bool:
		if isinstance(other, _TrackedHandle):
			return self._handle is other._handle
		return self._handle is other
