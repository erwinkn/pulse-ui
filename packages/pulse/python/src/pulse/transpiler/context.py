"""Context for JSExpr emit mode."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# When True, JSExpr.emit() returns code suitable for client-side interpretation
# (e.g., "get_object('Button_1')" instead of "Button_1")
_interpreted_mode: ContextVar[bool] = ContextVar(
	"jsexpr_interpreted_mode", default=False
)


def is_interpreted_mode() -> bool:
	"""Check if we're in interpreted mode."""
	return _interpreted_mode.get()


@contextmanager
def interpreted_mode() -> Iterator[None]:
	"""Context manager to enable interpreted mode for JSExpr.emit()."""
	token = _interpreted_mode.set(True)
	try:
		yield
	finally:
		_interpreted_mode.reset(token)
