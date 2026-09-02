import asyncio
import concurrent.futures
import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

# Cross-thread calls block on the loop. A loop that stops between the
# is_running() check and running our callback would hang the caller forever.
MARSHAL_TIMEOUT = 30.0

_idle_loop: asyncio.AbstractEventLoop | None = None


def running_loop() -> asyncio.AbstractEventLoop | None:
	try:
		return asyncio.get_running_loop()
	except RuntimeError:
		return None


def _main_thread_idle_loop() -> asyncio.AbstractEventLoop | None:
	"""
	The main thread's idle loop, for scheduling from sync code with nothing
	running (e.g. an Effect created at import time). Work queued on it runs only
	if something later runs that loop.
	"""
	global _idle_loop
	if threading.current_thread() is not threading.main_thread():
		return None
	if _idle_loop is None or _idle_loop.is_closed():
		_idle_loop = asyncio.new_event_loop()
	return _idle_loop


def post(loop: asyncio.AbstractEventLoop, fn: Callable[[], Any]) -> None:
	"""Run `fn` on `loop`'s thread without waiting. No-op if the loop is closed."""
	if running_loop() is loop:
		fn()
		return
	try:
		loop.call_soon_threadsafe(fn)
	except RuntimeError:
		# Loop is closed: nothing it holds can fire any more.
		pass


class LoopRef:
	"""The event loop Pulse schedules on, and the only place that knows about threads."""

	__slots__: tuple[str, ...] = ("name", "_loop")
	name: str | None
	_loop: asyncio.AbstractEventLoop | None

	def __init__(
		self,
		name: str | None = None,
		*,
		loop: asyncio.AbstractEventLoop | None = None,
	) -> None:
		self.name = name
		self._loop = loop

	@property
	def loop(self) -> asyncio.AbstractEventLoop | None:
		return self._loop

	def bind(self, loop: asyncio.AbstractEventLoop) -> None:
		self._loop = loop

	def run(self, fn: Callable[[asyncio.AbstractEventLoop], T]) -> T:
		"""
		Run `fn(loop)` on the loop's thread and return its result.
		Inline when already on the loop, otherwise blocks the calling thread.
		"""
		label = self.name or "unnamed"
		running = running_loop()
		target = self._loop

		if target is None:
			if running is not None:
				# An unbound ref adopts and binds the first running loop that uses it.
				self._loop = running
				return fn(running)
			idle = _main_thread_idle_loop()
			if idle is None:
				raise RuntimeError(f"cannot schedule: {label} has no bound event loop")
			return fn(idle)
		if running is target:
			return fn(target)
		if running is not None:
			raise RuntimeError(
				f"cannot schedule on {label} from a thread running a different event loop"
			)
		if not target.is_running():
			raise RuntimeError(f"cannot schedule on {label}: event loop is not running")

		future: concurrent.futures.Future[T] = concurrent.futures.Future()

		def _call() -> None:
			try:
				future.set_result(fn(target))
			except BaseException as exc:
				future.set_exception(exc)

		target.call_soon_threadsafe(_call)
		return future.result(timeout=MARSHAL_TIMEOUT)
