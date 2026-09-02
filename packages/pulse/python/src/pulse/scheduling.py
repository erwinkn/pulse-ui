"""Asyncio-specific lifecycle host for anyio task scopes."""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, Generic, ParamSpec, TypeVar, cast

from anyio import Event, TaskHandle, create_task_group, sleep
from anyio.abc import TaskGroup
from anyio.from_thread import run_sync
from anyio.lowlevel import EventLoopToken, checkpoint, current_token

T = TypeVar("T")
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


def _running_loop() -> asyncio.AbstractEventLoop | None:
	try:
		return asyncio.get_running_loop()
	except RuntimeError:
		return None


class Task(Generic[T]):
	"""A thread-safe handle for work owned by a Scheduler."""

	__slots__: tuple[str, ...] = (
		"_exception",
		"_handle",
		"_result",
		"_scheduler",
		"name",
	)

	_handle: TaskHandle[T, Any] | None
	_scheduler: Scheduler
	_result: T | None
	_exception: BaseException | None
	name: str | None

	def __init__(self, scheduler: Scheduler, name: str | None) -> None:
		self._scheduler = scheduler
		self._handle = None
		self._result = None
		self._exception = None
		self.name = name

	def _set_handle(self, handle: TaskHandle[T, Any]) -> None:
		self._handle = handle
		if self.name is None:
			self.name = handle.name

	def cancel(self) -> None:
		if self.done():
			return
		handle = self._handle
		assert handle is not None
		self._scheduler._run_on_loop(handle.cancel)  # pyright: ignore[reportPrivateUsage]

	def cancelled(self) -> bool:
		handle = self._handle
		assert handle is not None
		return handle.status is TaskHandle.Status.CANCELLED

	def done(self) -> bool:
		handle = self._handle
		assert handle is not None
		return handle.status in (
			TaskHandle.Status.FINISHED,
			TaskHandle.Status.CANCELLED,
			TaskHandle.Status.FAILED,
		)

	@property
	def exception(self) -> BaseException | None:
		return self._exception

	def __await__(self):
		return self._wait().__await__()

	async def _wait(self) -> T:
		handle = self._handle
		assert handle is not None
		try:
			await handle.wait()
		except asyncio.CancelledError:
			self.cancel()
			raise
		if self.cancelled():
			raise asyncio.CancelledError
		if self._exception is not None:
			raise self._exception
		return cast(T, self._result)


class Scheduler:
	"""An anyio task scope with asyncio thread dispatch."""

	_name: str
	_loop: asyncio.AbstractEventLoop | None
	_token: EventLoopToken | None
	_tg: TaskGroup | None
	_host: asyncio.Task[None] | None
	_close_requested: Event | None

	def __init__(self, name: str) -> None:
		self._name = name
		self._loop = None
		self._token = None
		self._tg = None
		self._host = None
		self._close_requested = None

	@property
	def name(self) -> str:
		return self._name

	@property
	def running(self) -> bool:
		return self._tg is not None

	async def start(self) -> None:
		if self.running:
			raise RuntimeError(f"scheduler {self._name} is already running")

		loop = asyncio.get_running_loop()
		self._loop = loop
		self._token = current_token()
		self._close_requested = Event()
		ready = asyncio.Event()
		self._host = loop.create_task(self._run(ready), name=f"scheduler:{self._name}")
		await ready.wait()

	async def _run(self, ready: asyncio.Event) -> None:
		async with create_task_group() as tg:
			self._tg = tg
			ready.set()
			assert self._close_requested is not None
			await self._close_requested.wait()
			tg.cancel_scope.cancel()

	async def close(self) -> None:
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
			self._loop = None
			self._token = None

	async def __aenter__(self) -> Scheduler:
		await self.start()
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.close()

	def _run_on_loop(self, fn: Callable[[], T]) -> T:
		if not self.running:
			raise RuntimeError(
				f"cannot schedule on {self._name}: scheduler is not running"
			)
		loop = self._loop
		token = self._token
		assert loop is not None
		assert token is not None

		current = _running_loop()
		if current is loop:
			return fn()
		if current is not None:
			raise RuntimeError(
				f"cannot schedule on {self._name} from a thread running a different event loop"
			)
		return run_sync(fn, token=token)

	def _report(self, message: str, exception: Exception, callback: Any) -> None:
		assert self._loop is not None
		self._loop.call_exception_handler(
			{
				"message": message,
				"exception": exception,
				"context": {"callback": callback},
			}
		)

	def _spawn(
		self,
		coroutine: Awaitable[T],
		*,
		name: str | None = None,
		on_done: Callable[[Task[T]], None] | None = None,
		error_message: str | None = None,
		callback: Callable[..., Any] | None = None,
	) -> Task[T]:
		assert self._tg is not None
		task = Task[T](self, name)

		async def _runner() -> None:
			started = False
			try:
				handle = task._handle  # pyright: ignore[reportPrivateUsage]
				assert handle is not None
				if handle.status is TaskHandle.Status.CANCELLING:
					await checkpoint()
				started = True
				task._result = await coroutine  # pyright: ignore[reportPrivateUsage]
			except asyncio.CancelledError:
				raise
			except Exception as exc:
				task._exception = exc  # pyright: ignore[reportPrivateUsage]
				if on_done is None:
					self._report(
						error_message or "Unhandled exception in create_task()",
						exc,
						callback if callback is not None else coroutine,
					)
			finally:
				if not started and inspect.iscoroutine(coroutine):
					coroutine.close()
				if on_done is not None:
					try:
						on_done(task)
					except Exception as exc:
						self._report(
							"Unhandled exception in scheduled task done callback",
							exc,
							on_done,
						)

		handle = cast(TaskHandle[T, Any], self._tg.start_soon(_runner, name=name))
		task._set_handle(handle)  # pyright: ignore[reportPrivateUsage]
		return task

	def create_task(
		self,
		coroutine: Awaitable[T],
		*,
		name: str | None = None,
		on_done: Callable[[Task[T]], None] | None = None,
	) -> Task[T]:
		"""Create a task in this scheduler."""
		return self._run_on_loop(
			lambda: self._spawn(coroutine, name=name, on_done=on_done)
		)

	def _callback(
		self,
		delay: float | None,
		fn: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		*,
		repeat: bool = False,
		immediate: bool = False,
	) -> Awaitable[None]:
		async def _run() -> None:
			from pulse.reactive import Untrack

			if delay is not None and not immediate:
				await sleep(clamp_delay(delay))
			while True:
				try:
					with Untrack():
						result = fn(*args, **kwargs)
					if inspect.isawaitable(result):
						await result
				except asyncio.CancelledError:
					raise
				except Exception as exc:
					if not repeat:
						raise
					self._report("Unhandled exception in repeat() callback", exc, fn)
				if not repeat:
					return
				await sleep(clamp_delay(delay or 0))

		return _run()

	def call_soon(
		self, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> Task[None]:
		return self._run_on_loop(
			lambda: self._spawn(
				self._callback(0, fn, args, dict(kwargs)),
				error_message="Unhandled exception in later() callback",
				callback=fn,
			)
		)

	def later(
		self, delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> Task[None]:
		return self._run_on_loop(
			lambda: self._spawn(
				self._callback(delay, fn, args, dict(kwargs)),
				error_message="Unhandled exception in later() callback",
				callback=fn,
			)
		)

	def repeat(
		self, interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> Task[None]:
		immediate = bool(kwargs.pop("immediate", False))
		return self._run_on_loop(
			lambda: self._spawn(
				self._callback(
					interval,
					fn,
					args,
					dict(kwargs),
					repeat=True,
					immediate=immediate,
				)
			)
		)

	def _create_future(self) -> asyncio.Future[Any]:
		return self._run_on_loop(asyncio.get_running_loop().create_future)  # pyright: ignore[reportPrivateUsage]


def _current_scheduler() -> Scheduler:
	from pulse.context import PulseContext

	ctx = PulseContext.get()
	if ctx.render is not None:
		return ctx.render.scheduler
	return ctx.app.scheduler


def call_soon(fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> Task[None]:
	"""Schedule a callback to run ASAP on the active scheduler."""
	return _current_scheduler().call_soon(fn, *args, **kwargs)


def create_task(
	coroutine: Awaitable[T],
	*,
	name: str | None = None,
	on_done: Callable[[Task[T]], None] | None = None,
) -> Task[T]:
	"""Create a task in the active scheduler."""
	return _current_scheduler().create_task(coroutine, name=name, on_done=on_done)


def create_future() -> asyncio.Future[Any]:
	"""Create a future on the active scheduler's event loop."""
	return _current_scheduler()._create_future()  # pyright: ignore[reportPrivateUsage]


def later(
	delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> Task[None]:
	"""Schedule a callback after a delay on the active scheduler."""
	return _current_scheduler().later(delay, fn, *args, **kwargs)


def repeat(
	interval: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> Task[None]:
	"""Repeat a callback on the active scheduler."""
	return _current_scheduler().repeat(interval, fn, *args, **kwargs)
