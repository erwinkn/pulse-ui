from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast, overload

from pulse.hooks.core import MISSING, HookMetadata, HookState, hooks

T = TypeVar("T")
TCallable = TypeVar("TCallable", bound=Callable)


class StableEntry:
	__slots__ = ("value", "wrapper")

	def __init__(self, value: Any) -> None:
		self.value = value

		def wrapper(*args: Any, **kwargs: Any):
			current = self.value
			if callable(current):
				return current(*args, **kwargs)
			return current

		self.wrapper = wrapper


class StableRegistry(HookState):
	__slots__ = ("entries",)

	def __init__(self) -> None:
		super().__init__()
		self.entries: dict[str, StableEntry] = {}


def _stable_factory(*_: object) -> StableRegistry:
	return StableRegistry()


_stable_hook = hooks.create(
	"pulse:core.stable",
	_stable_factory,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal registry for pulse.stable values",
	),
)


@overload
def stable(key: str) -> Any: ...


@overload
def stable(key: str, value: TCallable) -> TCallable: ...


@overload
def stable(key: str, value: T) -> Callable[[], T]: ...


def stable(key: str, value: Any = MISSING):
	if not key:
		raise ValueError("stable() requires a non-empty string key")

	registry = cast(StableRegistry, _stable_hook())
	entry = registry.entries.get(key)

	if value is not MISSING:
		if entry is None:
			entry = StableEntry(value)
			registry.entries[key] = entry
		else:
			entry.value = value
		return entry.wrapper

	if entry is None:
		raise KeyError(f"stable(): no value registered for key '{key}'")
	return entry.wrapper


__all__ = ["stable", "StableRegistry", "StableEntry"]
