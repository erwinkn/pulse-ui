import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from anyio import from_thread

T = TypeVar("T")
P = ParamSpec("P")


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


def later(
	delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
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

	def _run():
		from pulse.reactive import Untrack

		try:
			with Untrack():
				res = fn(*args, **kwargs)
				if asyncio.iscoroutine(res):
					task = loop.create_task(res)

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
	_handles: set[asyncio.Handle]
	name: str | None

	def __init__(self, name: str | None = None) -> None:
		self._handles = set()
		self.name = name

	def track(self, handle: asyncio.Handle) -> asyncio.Handle:
		self._handles.add(handle)
		return handle

	def discard(self, handle: asyncio.Handle | None) -> None:
		if handle is None:
			return
		self._handles.discard(handle)

	def later(
		self, delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> asyncio.TimerHandle:
		handle: asyncio.TimerHandle | None = None

		def _wrapped():
			try:
				return fn(*args, **kwargs)
			finally:
				self.discard(handle)

		handle = later(delay, _wrapped)
		self._handles.add(handle)
		return handle

	def cancel_all(self) -> None:
		for handle in list(self._handles):
			handle.cancel()
		self._handles.clear()
