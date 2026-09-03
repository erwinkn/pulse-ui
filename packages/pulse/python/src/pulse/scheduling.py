"""Task scopes: an asyncio-hosted anyio task group with a lifetime."""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec

from anyio import Event, TaskHandle, create_task_group, sleep
from anyio.abc import TaskGroup
from anyio.lowlevel import checkpoint

P = ParamSpec("P")

CLOCK_RESOLUTION = time.get_clock_info("monotonic").resolution

_FINISHED = (
	TaskHandle.Status.FINISHED,
	TaskHandle.Status.CANCELLED,
	TaskHandle.Status.FAILED,
)


def clamp_delay(delay: float) -> float:
	"""Clamp positive delays because asyncio treats timers within one clock resolution as due."""
	return max(delay, CLOCK_RESOLUTION) if delay > 0 else delay


def is_pytest() -> bool:
	"""Detect if running inside pytest using environment variables."""
	return bool(os.environ.get("PYTEST_CURRENT_TEST")) or (
		"PYTEST_XDIST_TESTRUNUID" in os.environ
	)


def is_pending(handle: TaskHandle[Any]) -> bool:
	"""True until the task has finished, including while it is being cancelled."""
	return handle.status not in _FINISHED


async def _invoke(
	fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
	from pulse.reactive import Untrack

	with Untrack():
		result = fn(*args, **kwargs)
	if inspect.isawaitable(result):
		await result


class Scheduler:
	"""A task lifetime: everything spawned here is cancelled and drained on close."""

	_name: str
	_loop: asyncio.AbstractEventLoop | None
	_tg: TaskGroup | None
	_host: asyncio.Task[None] | None
	_close_requested: Event | None

	def __init__(self, name: str) -> None:
		self._name = name
		self._loop = None
		self._tg = None
		self._host = None
		self._close_requested = None

	@property
	def name(self) -> str:
		return self._name

	@property
	def running(self) -> bool:
		return self._tg is not None

	@property
	def owns_current_thread(self) -> bool:
		"""True when the caller runs on this scope's loop, so handles are usable."""
		return self._loop is not None and _running_loop() is self._loop

	async def start(self) -> None:
		if self.running:
			raise RuntimeError(f"scheduler {self._name} is already running")

		loop = asyncio.get_running_loop()
		self._loop = loop
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

	async def __aenter__(self) -> Scheduler:
		await self.start()
		return self

	async def __aexit__(self, *exc: object) -> None:
		await self.close()

	def spawn(
		self, coroutine: Coroutine[Any, Any, Any], *, name: str | None = None
	) -> TaskHandle[None]:
		"""Run a coroutine in this scope. Its exceptions are reported, not propagated."""
		tg = self._task_group()
		name = name or coroutine.__qualname__
		return tg.create_task(self._guard(coroutine, name), name=name)

	def later(
		self, delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
	) -> TaskHandle[None]:
		"""Call `fn` once after `delay` seconds."""
		return self.spawn(
			self._delayed(delay, fn, args, dict(kwargs)),
			name=f"later:{_callable_name(fn)}",
		)

	def repeat(
		self,
		interval: float,
		fn: Callable[P, Any],
		*args: P.args,
		immediate: bool = False,  # pyright: ignore[reportGeneralTypeIssues]
		**kwargs: P.kwargs,
	) -> TaskHandle[None]:
		"""Call `fn` every `interval` seconds, surviving its exceptions."""
		return self.spawn(
			self._repeated(interval, fn, args, dict(kwargs), immediate=immediate),
			name=f"repeat:{_callable_name(fn)}",
		)

	def post(self, fn: Callable[[], Any]) -> None:
		"""Call `fn` on this scope's loop soon, from any thread.

		Returns no handle: one is only usable from the loop that owns it. `fn` must be
		synchronous; use `spawn` for coroutines.
		"""
		loop = self._loop
		if loop is None:
			raise RuntimeError(f"cannot schedule on {self._name}: it has never run")
		loop.call_soon_threadsafe(self._post, fn)

	def _post(self, fn: Callable[[], Any]) -> None:
		from pulse.reactive import Untrack

		# The scope may have closed between post() and this callback.
		if self._tg is None:
			return
		try:
			with Untrack():
				fn()
		except Exception as exc:
			self._report(f"Unhandled exception in post({_callable_name(fn)})", exc, fn)

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


def current_scheduler() -> Scheduler:
	from pulse.context import PulseContext

	ctx = PulseContext.get()
	if ctx.render is not None:
		return ctx.render.scheduler
	return ctx.app.scheduler


def spawn(
	coroutine: Coroutine[Any, Any, Any], *, name: str | None = None
) -> TaskHandle[None]:
	"""Run a coroutine in the active scheduler."""
	return current_scheduler().spawn(coroutine, name=name)


def post(fn: Callable[[], Any]) -> None:
	"""Run a callback in the active scheduler from any thread."""
	current_scheduler().post(fn)


def later(
	delay: float, fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
) -> TaskHandle[None]:
	"""Schedule a callback after a delay on the active scheduler."""
	return current_scheduler().later(delay, fn, *args, **kwargs)


def repeat(
	interval: float,
	fn: Callable[P, Any],
	*args: P.args,
	immediate: bool = False,  # pyright: ignore[reportGeneralTypeIssues]
	**kwargs: P.kwargs,
) -> TaskHandle[None]:
	"""Repeat a callback on the active scheduler."""
	return current_scheduler().repeat(
		interval, fn, *args, immediate=immediate, **kwargs
	)
