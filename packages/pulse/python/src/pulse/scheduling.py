import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, override

from anyio import from_thread

T = TypeVar("T")
P = ParamSpec("P")


class TimerHandleLike(Protocol):
	def cancel(self) -> None: ...
	def cancelled(self) -> bool: ...
	def when(self) -> float: ...


def is_pytest() -> bool:
	"""Detect if running inside pytest using environment variables."""
	return bool(os.environ.get("PYTEST_CURRENT_TEST")) or (
		"PYTEST_XDIST_TESTRUNUID" in os.environ
	)


def schedule_on_loop(callback: Callable[[], None]) -> None:
	"""Schedule a callback to run ASAP on the main event loop from any thread."""
	try:
		loop = asyncio.get_running_loop()
		loop.call_soon_threadsafe(callback)
	except RuntimeError:

		async def _runner():
			loop = asyncio.get_running_loop()
			loop.call_soon(callback)

		try:
			from_thread.run(_runner)
		except RuntimeError:
			if not is_pytest():
				raise


def create_task(
	coroutine: Awaitable[T],
	*,
	name: str | None = None,
	on_done: Callable[[asyncio.Task[T]], None] | None = None,
) -> asyncio.Task[T]:
	"""Create and schedule a coroutine task on the main loop from any thread.

	- factory should create a fresh coroutine each call
	- optional on_done is attached on the created task within the loop
	"""

	try:
		asyncio.get_running_loop()
		# ensure_future accepts Awaitable and returns a Task when given a coroutine
		task = asyncio.ensure_future(coroutine)
		if name is not None:
			task.set_name(name)
		if on_done:
			task.add_done_callback(on_done)
		return task
	except RuntimeError:

		async def _runner():
			asyncio.get_running_loop()
			# ensure_future accepts Awaitable and returns a Task when given a coroutine
			task = asyncio.ensure_future(coroutine)
			if name is not None:
				task.set_name(name)
			if on_done:
				task.add_done_callback(on_done)
			return task

	try:
		return from_thread.run(_runner)
	except RuntimeError:
		raise


def create_future_on_loop() -> asyncio.Future[Any]:
	"""Create an asyncio Future on the main event loop from any thread."""
	try:
		return asyncio.get_running_loop().create_future()
	except RuntimeError:

		async def _create():
			loop = asyncio.get_running_loop()
			return loop.create_future()

		return from_thread.run(_create)


def _resolve_registries() -> tuple["TaskRegistry", "TimerRegistry"]:
	from pulse.context import PulseContext

	ctx = PulseContext.get()
	if ctx.render is not None:
		return ctx.render._tasks, ctx.render._timers  # pyright: ignore[reportPrivateUsage]
	return ctx.app._tasks, ctx.app._timers  # pyright: ignore[reportPrivateUsage]


def _schedule_later(
	delay: float,
	fn: Callable[P, Any],
	*args: P.args,
	**kwargs: P.kwargs,
) -> asyncio.TimerHandle:
	"""
	Schedule `fn(*args, **kwargs)` to run after `delay` seconds.
	Works with sync or async functions. Returns a TimerHandle; call .cancel() to cancel.

	The callback runs with no reactive scope to avoid accidentally capturing
	reactive dependencies from the calling context. Other context vars (like
	PulseContext) are preserved normally.
	"""

	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		try:
			loop = asyncio.get_event_loop()
		except RuntimeError as exc:
			raise RuntimeError("later() requires an event loop") from exc

	task_registry, _ = _resolve_registries()

	def _run():
		from pulse.reactive import Untrack

		try:
			with Untrack():
				res = fn(*args, **kwargs)
				if asyncio.iscoroutine(res):
					task = loop.create_task(res)
					task_registry.track(task)

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

	return loop.call_later(delay, _run)


def later(
	delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> TimerHandleLike:
	"""
	Schedule `fn(*args, **kwargs)` to run after `delay` seconds.
	Works with sync or async functions. Returns a handle; call .cancel() to cancel.

	The callback runs with no reactive scope to avoid accidentally capturing
	reactive dependencies from the calling context. Other context vars (like
	PulseContext) are preserved normally.
	"""

	_, timer_registry = _resolve_registries()
	return timer_registry.later(delay, fn, *args, **kwargs)


class RepeatHandle:
	task: asyncio.Task[None] | None
	cancelled: bool

	def __init__(self) -> None:
		self.task = None
		self.cancelled = False

	def cancel(self):
		if self.cancelled:
			return
		self.cancelled = True
		if self.task is not None and not self.task.done():
			self.task.cancel()


def repeat(interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs):
	"""
	Repeatedly run `fn(*args, **kwargs)` every `interval` seconds.
	Works with sync or async functions.
	For async functions, waits for completion before starting the next delay.
	Returns a handle with .cancel() to stop future runs.

	The callback runs with no reactive scope to avoid accidentally capturing
	reactive dependencies from the calling context. Other context vars (like
	PulseContext) are preserved normally.

	Optional kwargs:
	- immediate: bool = False  # run once immediately before the first interval
	"""

	from pulse.reactive import Untrack

	task_registry, _ = _resolve_registries()
	loop = asyncio.get_running_loop()
	handle = RepeatHandle()

	async def _runner():
		nonlocal handle
		try:
			while not handle.cancelled:
				# Start counting the next interval AFTER the previous execution completes
				await asyncio.sleep(interval)
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
					loop.call_exception_handler(
						{
							"message": "Unhandled exception in repeat() callback",
							"exception": exc,
							"context": {"callback": fn},
						}
					)
		except asyncio.CancelledError:
			# Swallow task cancellation to avoid noisy "exception was never retrieved"
			pass

	handle.task = loop.create_task(_runner())
	task_registry.track(handle.task)

	return handle


class TaskRegistry:
	_tasks: set[asyncio.Task[Any]]
	name: str | None

	def __init__(self, name: str | None = None) -> None:
		self._tasks = set()
		self.name = name

	def track(self, task: asyncio.Task[T]) -> asyncio.Task[T]:
		self._tasks.add(task)
		task.add_done_callback(self._tasks.discard)
		return task

	def create(
		self,
		coroutine: Awaitable[T],
		*,
		name: str | None = None,
		on_done: Callable[[asyncio.Task[T]], None] | None = None,
	) -> asyncio.Task[T]:
		task = create_task(coroutine, name=name, on_done=on_done)
		return self.track(task)

	def cancel_all(self) -> None:
		for task in list(self._tasks):
			if not task.done():
				task.cancel()
		self._tasks.clear()


class TimerRegistry:
	_handles: set[TimerHandleLike]
	name: str | None

	def __init__(self, name: str | None = None) -> None:
		self._handles = set()
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
		tracked_box: list[_TrackedTimerHandle] = []

		def _wrapped():
			try:
				return fn(*args, **kwargs)
			finally:
				self.discard(tracked_box[0] if tracked_box else None)

		handle = _schedule_later(delay, _wrapped)
		tracked = _TrackedTimerHandle(handle, self)
		tracked_box.append(tracked)
		self._handles.add(tracked)
		return tracked

	def cancel_all(self) -> None:
		for handle in list(self._handles):
			handle.cancel()
		self._handles.clear()


class _TrackedTimerHandle:
	__slots__: tuple[str, ...] = ("_handle", "_registry")
	_handle: asyncio.TimerHandle
	_registry: "TimerRegistry"

	def __init__(self, handle: asyncio.TimerHandle, registry: "TimerRegistry") -> None:
		self._handle = handle
		self._registry = registry

	def cancel(self) -> None:
		if not self._handle.cancelled():
			self._handle.cancel()
		self._registry.discard(self)

	def cancelled(self) -> bool:
		return self._handle.cancelled()

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
