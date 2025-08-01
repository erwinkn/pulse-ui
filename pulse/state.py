"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

from collections import defaultdict
from typing import Any, Iterable, Callable, TypeVar
from abc import ABC, ABCMeta

from pulse.reactive import RENDER_CONTEXT, UPDATE_SCHEDULER


# Global context for tracking state access during rendering

T = TypeVar("T")


class StateProperty:
    """
    Descriptor that creates reactive properties on State classes.
    Tracks when properties are accessed and triggers updates when set.
    """

    def __init__(self, name: str, default_value: Any = None):
        self.name = name
        self.default_value = default_value
        self.private_name = f"_state_{name}"

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self

        # Track that this property was accessed during rendering
        ctx = RENDER_CONTEXT.get()
        if ctx is not None:
            ctx.track_state_access(obj, self.name)

        # Return the current value or default
        return getattr(obj, self.private_name, self.default_value)

    def __set__(self, obj: Any, value: Any) -> None:
        if not isinstance(obj, State):
            raise TypeError("StateProperty can only be defined on a State object")
        # Get the old value
        old_value = getattr(obj, self.private_name, self.default_value)
        if old_value != value:
            setattr(obj, self.private_name, value)
            obj.notify_listeners(self.name)


class StateMeta(ABCMeta):
    """
    Metaclass that automatically converts annotated attributes into reactive properties.
    """

    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        # Get type annotations
        annotations = namespace.get("__annotations__", {})

        # Convert annotated attributes to reactive properties
        for attr_name, attr_type in annotations.items():
            if not attr_name.startswith("_"):
                # Check if there's a default value
                default_value = namespace.get(attr_name, None)

                # Create a StateProperty descriptor
                namespace[attr_name] = StateProperty(attr_name, default_value)

        return super().__new__(mcs, name, bases, namespace)


class State(ABC, metaclass=StateMeta):
    """
    Base class for reactive state objects.

    Define state properties using type annotations:

    ```python
    class CounterState(ps.State):
        count: int = 0
        name: str = "Counter"
    ```

    Properties will automatically trigger re-renders when changed.
    """

    def __init__(self):
        # Track listeners for this state instance
        self._listeners: dict[str, set[Callable[[], None]]] = defaultdict(set)

    def __repr__(self) -> str:
        """Return a developer-friendly representation of the state."""
        props = []
        for name in self.__class__.__annotations__:
            if not name.startswith("_"):
                prop_value = getattr(self, name)
                props.append(f"{name}={prop_value!r}")
        return f"<{self.__class__.__name__} {' '.join(props)}>"

    def __str__(self) -> str:
        """Return a user-friendly representation of the state."""
        return self.__repr__()

    def add_listener(self, fields: Iterable[str], fn: Callable[[], Any]):
        for field in fields:
            self._listeners[field].add(fn)

    def remove_listener(self, fields: Iterable[str], fn: Callable[[], Any]):
        for field in fields:
            self._listeners[field].remove(fn)

    def notify_listeners(self, field: str):
        """Notify all listeners that a property has changed."""

        # Notify property-specific listeners
        scheduler = UPDATE_SCHEDULER.get()
        if field in self._listeners:
            for listener in self._listeners[field].copy():
                if scheduler:
                    scheduler.schedule(listener)
                else:
                    try:
                        listener()
                    except Exception as e:
                        print(f"Error in state listener: {e}")
