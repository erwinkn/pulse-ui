from collections.abc import Callable
from typing import Any, TypeVar, overload

from pulse.hooks.core import MISSING, HookMetadata, HookState, hooks

T = TypeVar("T")
TCallable = TypeVar("TCallable", bound=Callable[..., Any])


class StableEntry:
	"""Container for a stable value and its wrapper function.

	Holds a value and a wrapper function that always delegates to the
	current value, allowing the wrapper reference to remain stable while
	the underlying value can change.

	Attributes:
		value: The current wrapped value.
		wrapper: Stable function that delegates to the current value.
	"""

	__slots__ = ("value", "wrapper")  # pyright: ignore[reportUnannotatedClassAttribute]
	value: Any
	wrapper: Callable[..., Any]

	def __init__(self, value: Any) -> None:
		self.value = value

		def wrapper(*args: Any, **kwargs: Any):
			current = self.value
			if callable(current):
				return current(*args, **kwargs)
			return current

		self.wrapper = wrapper


class StableRegistry(HookState):
	"""Internal hook state that stores stable entries by key.

	Maintains a dictionary of StableEntry objects, allowing stable
	wrappers to persist across renders while their underlying values
	can be updated.
	"""

	__slots__ = ("entries",)  # pyright: ignore[reportUnannotatedClassAttribute]

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


def stable(key: str, value: Any = MISSING) -> Any:
	"""Return a stable wrapper that always calls the latest value.

		Creates a wrapper function that maintains a stable reference across renders
		while delegating to the current value. Useful for event handlers and callbacks
		that need to stay referentially stable.

		Args:
			key: Unique identifier for this stable value within the component.
			value: Optional value or callable to wrap. If provided, updates the
				stored value and returns the wrapper. If omitted, returns the
				existing wrapper for the key.

		Returns:
			A stable wrapper function that delegates to the current value. If the
			value is callable, the wrapper calls it with any provided arguments.
			If not callable, the wrapper returns the value directly.

		Raises:
			ValueError: If key is empty.
			KeyError: If value is not provided and no entry exists for the key.

		Example:

		```python
		def my_component():
		    s = ps.state("data", lambda: DataState())

		    # Without stable, this would create a new function each render
		    handle_click = ps.stable("click", lambda: s.increment())

		    return m.Button("Click", on_click=handle_click)
		```

		Use Cases:
			- Event handlers passed to child components to prevent unnecessary re-renders
			- Callbacks registered with external systems
			- Any function reference that needs to stay stable across renders
	) -> Any:
	"""
	if not key:
		raise ValueError("stable() requires a non-empty string key")

	registry = _stable_hook()
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
