from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, ParamSpec, TypeVar

from pulse.context import PULSE_CONTEXT
from pulse.scheduling import TimerHandleLike, later

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class Debounced(Generic[P, R]):
	fn: Callable[P, R]
	delay_ms: float
	_handle: TimerHandleLike | asyncio.Handle | None = field(
		default=None, init=False, repr=False, compare=False
	)

	def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Any:
		if self._handle is not None:
			self._handle.cancel()

		delay = self.delay_ms / 1000.0

		def _run() -> None:
			object.__setattr__(self, "_handle", None)
			result = self.fn(*args, **kwargs)
			if asyncio.iscoroutine(result):
				loop = asyncio.get_running_loop()
				task = loop.create_task(result)

				def _log_task_exception(t: asyncio.Task[Any]) -> None:
					try:
						t.result()
					except asyncio.CancelledError:
						pass
					except Exception as exc:
						loop.call_exception_handler(
							{
								"message": "Unhandled exception in debounced() task",
								"exception": exc,
								"context": {"callback": self.fn},
							}
						)

				task.add_done_callback(_log_task_exception)

		if PULSE_CONTEXT.get() is not None:
			handle = later(delay, _run)
		else:
			try:
				loop = asyncio.get_running_loop()
			except RuntimeError:
				try:
					loop = asyncio.get_event_loop()
				except RuntimeError as exc:
					raise RuntimeError("debounced() requires an event loop") from exc
			handle = loop.call_later(delay, _run)

		object.__setattr__(self, "_handle", handle)


def debounced(fn: Callable[P, R], delay_ms: int | float) -> Debounced[P, R]:
	"""Return a debounced callback marker (delay in milliseconds)."""
	if not callable(fn):
		raise TypeError("debounced() requires a callable")
	if isinstance(delay_ms, bool) or not isinstance(delay_ms, (int, float)):
		raise TypeError("debounced() delay must be a number (ms)")
	if not math.isfinite(delay_ms) or delay_ms < 0:
		raise ValueError("debounced() delay must be finite and >= 0")
	return Debounced(fn=fn, delay_ms=float(delay_ms))


__all__ = ["Debounced", "debounced"]
