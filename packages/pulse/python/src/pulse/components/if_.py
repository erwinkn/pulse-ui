"""Conditional rendering component.

Provides a declarative way to conditionally render elements based on a condition.
"""

from collections.abc import Iterable
from typing import Any, TypeVar

from pulse.reactive import Computed, Signal
from pulse.transpiler.nodes import Element

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
	"""Conditional rendering helper.

	Returns `then` if the condition is truthy, otherwise returns `else_`.
	Automatically unwraps reactive values (Signal, Computed) before evaluation.

	Args:
		condition: A boolean or reactive value to evaluate. Supports `Signal[bool]`
			and `Computed[bool]` which are automatically unwrapped.
		then: Element to render when condition is truthy.
		else_: Element to render when condition is falsy. Defaults to None.

	Returns:
		The `then` value if condition is truthy, otherwise `else_`.

	Example:
		Basic conditional::

			ps.If(
				user.is_admin,
				then=AdminPanel(),
				else_=ps.p("Access denied"),
			)

		With reactive condition::

			is_visible = ps.Signal(True)
			ps.If(is_visible, then=ps.div("Content"))
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
