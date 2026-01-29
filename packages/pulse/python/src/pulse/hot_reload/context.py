from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_HOT_RELOAD_ACTIVE: ContextVar[bool] = ContextVar(
	"pulse_hot_reload_active",
	default=False,
)


def is_hot_reload_active() -> bool:
	return _HOT_RELOAD_ACTIVE.get()


@contextmanager
def hot_reload_context(active: bool = True):
	token = _HOT_RELOAD_ACTIVE.set(active)
	try:
		yield
	finally:
		_HOT_RELOAD_ACTIVE.reset(token)
