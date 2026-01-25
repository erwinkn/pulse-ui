from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Debounced:
	fn: Callable[..., Any]
	delay_ms: float


def debounced(fn: Callable[..., Any], delay_ms: int | float) -> Debounced:
	"""Return a debounced callback marker (delay in milliseconds)."""
	if not callable(fn):
		raise TypeError("debounced() requires a callable")
	if isinstance(delay_ms, bool) or not isinstance(delay_ms, (int, float)):
		raise TypeError("debounced() delay must be a number (ms)")
	if not math.isfinite(delay_ms) or delay_ms < 0:
		raise ValueError("debounced() delay must be finite and >= 0")
	return Debounced(fn=fn, delay_ms=float(delay_ms))


__all__ = ["Debounced", "debounced"]
