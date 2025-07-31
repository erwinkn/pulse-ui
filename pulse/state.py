"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

from collections import defaultdict
from typing import Any, Set, Optional, Callable, TypeVar
from dataclasses import field
from abc import ABC, ABCMeta


# Global context for tracking state access during rendering
RENDER_CONTEXT: Optional["ReactiveContext"] = None

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
        if RENDER_CONTEXT is not None:
            RENDER_CONTEXT.track_state_access(obj, self.name)

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

    def add_listener(self, field: str, fn: Callable[[], Any]):
        self._listeners[field].add(fn)

    def remove_listener(self, field: str, fn: Callable[[], Any]):
        self._listeners[field].remove(fn)

    def notify_listeners(self, field: str):
        """Notify all listeners that a property has changed."""

        # Notify property-specific listeners
        if field in self._listeners:
            for listener in self._listeners[field].copy():
                try:
                    listener()
                except Exception as e:
                    print(f"Error in state listener: {e}")


class ReactiveContext:
    """
    Context object that tracks state access during rendering.
    """

    # Map of state instances to the properties accessed
    accessed_states: dict[State, Set[str]] = field(default_factory=dict)

    def __init__(self) -> None:
        self.accessed_states = {}

    def track_state_access(self, state: State, property_name: str):
        """Track that a state property was accessed during rendering."""
        if state not in self.accessed_states:
            self.accessed_states[state] = set()

        self.accessed_states[state].add(property_name)

    def __enter__(self):
        """Enter the context manager - set this as the global render context."""
        global RENDER_CONTEXT
        self._previous_context = RENDER_CONTEXT
        RENDER_CONTEXT = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager - restore the previous render context."""
        global RENDER_CONTEXT
        RENDER_CONTEXT = self._previous_context
        return False


def set_render_context(context: Optional[ReactiveContext]):
    """Set the global render context for tracking state access."""
    global RENDER_CONTEXT
    RENDER_CONTEXT = context


def get_render_context() -> Optional[ReactiveContext]:
    """Get the current render context."""
    return RENDER_CONTEXT
