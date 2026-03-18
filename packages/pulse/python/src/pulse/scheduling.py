import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, override

from anyio import from_thread

from pulse.errors import ErrorCode

T = TypeVar("T")
P = ParamSpec("P")

logger = logging.getLogger(__name__)


def _report_timer_error(
	exc: BaseException,
	*,
	code: ErrorCode,
	message: str,
	details: dict[str, Any],
) -> None:
	try:
		from pulse.context import PulseContext

		PulseContext.get().errors.report(
			exc,
			code=code,
			message=message,
			details=details,
		)
	except RuntimeError:
		logger.exception(message, exc_info=exc)


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
) -> TimerHandleLike | None:
	"""Schedule a callback to run ASAP on the main event loop from any thread."""
	_, timer_registry = _resolve_registries()
	return timer_registry.call_soon(fn, *args, **kwargs)


def create_task(
	coroutine: Awaitable[T],
	*,
	name: str | None = None,
	on_done: Callable[[asyncio.Task[T]], None] | None = None,
) -> asyncio.Task[T]:
	"""Create a tracked task on the active session/app registry."""
	task_registry, _ = _resolve_registries()
	return task_registry.create_task(coroutine, name=name, on_done=on_done)


def create_future() -> asyncio.Future[Any]:
	"""Create an asyncio Future on the main event loop from any thread."""
	task_registry, _ = _resolve_registries()
	return task_registry.create_future()


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

	_, timer_registry = _resolve_registries()
	return timer_registry.repeat(interval, fn, *args, **kwargs)


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

	def create_task(
		self,
		coroutine: Awaitable[T],
		*,
		name: str | None = None,
		on_done: Callable[[asyncio.Task[T]], None] | None = None,
	) -> asyncio.Task[T]:
		"""Create and schedule a coroutine task on the main loop from any thread."""
		try:
			asyncio.get_running_loop()
			task = asyncio.ensure_future(coroutine)
			if name is not None:
				task.set_name(name)
			if on_done:
				task.add_done_callback(on_done)
		except RuntimeError:

			async def _runner():
				asyncio.get_running_loop()
				task = asyncio.ensure_future(coroutine)
				if name is not None:
					task.set_name(name)
				if on_done:
					task.add_done_callback(on_done)
				return task

			task = from_thread.run(_runner)

		return self.track(task)

	def create_future(self) -> asyncio.Future[Any]:
		"""Create an asyncio Future on the main event loop from any thread."""
		try:
			return asyncio.get_running_loop().create_future()
		except RuntimeError:

			async def _create():
				return asyncio.get_running_loop().create_future()

			return from_thread.run(_create)

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
	) -> TimerHandleLike | None:
		def _schedule():
			return self._schedule_soon(fn, args, dict(kwargs))

		try:
			asyncio.get_running_loop()
			return _schedule()
		except RuntimeError:

			async def _runner():
				return _schedule()

			try:
				return from_thread.run(_runner)
			except RuntimeError:
				if not is_pytest():
					raise
				return None

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
						_report_timer_error(
							exc,
							code="timer.repeat",
							message="Unhandled exception in repeat() callback",
							details={"callback": repr(fn)},
						)
			except asyncio.CancelledError:
				# Swallow task cancellation to avoid noisy "exception was never retrieved"
				pass

		handle.task = self._tasks.create_task(_runner())
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
		Schedule `fn(*args, **kwargs)` to run after `delay` seconds.
		Works with sync or async functions. Returns a TimerHandle; call .cancel() to cancel.

		The callback can run without a reactive scope to avoid accidentally capturing
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

		tracked_box: list[TimerHandleLike] = []
		_run = self._prepare_run(tracked_box, fn, args, kwargs, untrack=untrack)

		handle = loop.call_later(delay, _run)
		tracked = _TrackedTimerHandle(handle, self)
		tracked_box.append(tracked)
		self._handles.add(tracked)
		return tracked

	def _schedule_soon(
		self,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
	) -> TimerHandleLike:
		try:
			loop = asyncio.get_running_loop()
		except RuntimeError:
			try:
				loop = asyncio.get_event_loop()
			except RuntimeError as exc:
				raise RuntimeError("call_soon() requires an event loop") from exc

		tracked_box: list[TimerHandleLike] = []
		_run = self._prepare_run(tracked_box, fn, args, kwargs, untrack=False)

		handle = loop.call_soon(_run)
		tracked = _TrackedHandle(handle, self, when=loop.time())
		tracked_box.append(tracked)
		self._handles.add(tracked)
		return tracked

	def _prepare_run(
		self,
		tracked_box: list[TimerHandleLike],
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		*,
		untrack: bool,
	) -> Callable[[], None]:
		def _run():
			from pulse.reactive import Untrack

			try:
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
							_report_timer_error(
								exc,
								code="timer.later",
								message="Unhandled exception in later() task",
								details={"callback": repr(fn)},
							)

					task.add_done_callback(_log_task_exception)
			except Exception as exc:
				_report_timer_error(
					exc,
					code="timer.later",
					message="Unhandled exception in later() callback",
					details={"callback": repr(fn)},
				)
			finally:
				self.discard(tracked_box[0] if tracked_box else None)

		return _run


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


class _TrackedHandle:
	__slots__: tuple[str, ...] = ("_handle", "_registry", "_when")
	_handle: asyncio.Handle
	_registry: "TimerRegistry"
	_when: float

	def __init__(
		self,
		handle: asyncio.Handle,
		registry: "TimerRegistry",
		*,
		when: float,
	) -> None:
		self._handle = handle
		self._registry = registry
		self._when = when

	def cancel(self) -> None:
		if not self._handle.cancelled():
			self._handle.cancel()
		self._registry.discard(self)

	def cancelled(self) -> bool:
		return self._handle.cancelled()

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
