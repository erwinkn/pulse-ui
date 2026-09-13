"""The single thread-safe bridge from a worker thread onto Pulse's serving loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, final


@final
class LoopBinding:
	"""A reference to the loop Pulse schedules on, usable from any thread.

	This is the only place in Pulse that crosses a thread boundary. It exists so
	that reactive work scheduled from a synchronous FastAPI endpoint (which runs
	in Starlette's threadpool) can reach the serving loop. User scheduling is
	loop-affine and never goes through here.
	"""

	__slots__ = ("_loop",)

	def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
		self._loop = loop

	@property
	def loop(self) -> asyncio.AbstractEventLoop:
		return self._loop

	@property
	def current(self) -> bool:
		"""True when the caller is running on the bound loop."""
		try:
			return asyncio.get_running_loop() is self._loop
		except RuntimeError:
			return False

	def post(self, fn: Callable[[], Any]) -> bool:
		"""Run `fn` on the bound loop soon, from any thread.

		Returns True when the callback was dispatched. The callback runs with
		reactive tracking disabled, and an exception it raises is reported
		through the loop's exception handler.
		"""
		if self._loop.is_closed():
			return False
		try:
			self._loop.call_soon_threadsafe(self._run, fn)
		except RuntimeError:
			return False
		return True

	def _run(self, fn: Callable[[], Any]) -> None:
		from pulse.reactive import Untrack

		try:
			with Untrack():
				fn()
		except Exception as exc:
			name = getattr(fn, "__qualname__", repr(fn))
			self._loop.call_exception_handler(
				{
					"message": f"Unhandled exception in post({name})",
					"exception": exc,
					"context": {"callback": fn},
				}
			)
