from collections.abc import Iterable
from typing import Any, TypeVar

from pulse.reactive import Computed, Signal
from pulse.transpiler_v2.nodes import Element

T1 = TypeVar("T1", bound=Element | Iterable[Element])
T2 = TypeVar("T2", bound=Element | Iterable[Element] | None)


def _is_truthy(value: Any) -> bool:
	if isinstance(value, bool):
		return value
	if value is None:
		return False
	try:
		return bool(value)
	except Exception:
		pass
	# Fallbacks for array/dataframe-like values that have ambiguous truthiness
	try:
		return len(value) > 0  # type: ignore[arg-type]
	except Exception:
		pass
	size = getattr(value, "size", None)
	if isinstance(size, int):
		return size > 0
	empty = getattr(value, "empty", None)
	if isinstance(empty, bool):
		return not empty
	# Conservative fallback
	return False


def If(
	condition: bool | Signal[bool] | Computed[bool],
	then: T1,
	else_: T2 = None,
) -> T1 | T2:
	"""Conditional rendering helper that returns either then or else_ based on condition.

	Args:
	    condition: Value to test truthiness
	    then: Element to render if condition is truthy
	    else_: Optional element to render if condition is falsy

	Returns:
	    The then value if condition is truthy, else_ if provided and condition is falsy, None otherwise
	"""
	# Unwrap reactive condition if needed and coerce to bool explicitly with guards
	if isinstance(condition, (Signal, Computed)):
		try:
			raw = condition.unwrap()  # type: ignore[attr-defined]
		except Exception:
			try:
				raw = condition()
			except Exception:
				raw = condition
	else:
		raw = condition
	if _is_truthy(raw):
		return then
	return else_
