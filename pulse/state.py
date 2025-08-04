"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

from abc import ABC, ABCMeta
from typing import Any, TypeVar

from pulse.reactive import Signal


T = TypeVar("T")


class StateProperty:
    """
    Descriptor that creates reactive properties on State classes.
    Tracks when properties are accessed and triggers updates when set.
    """

    def __init__(self, name: str, default_value: Any = None):
        self.name = name
        self.default_value = default_value
        self.private_name = f"__signal_{name}"

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self

        if not hasattr(obj, self.private_name):
            # Create the signal on first access
            signal = Signal(
                self.default_value, name=f"{obj.__class__.__name__}.{self.name}"
            )
            setattr(obj, self.private_name, signal)
            return signal()

        signal: Signal = getattr(obj, self.private_name)
        return signal()

    def __set__(self, obj: Any, value: Any) -> None:
        if not hasattr(obj, self.private_name):
            # Create the signal on first set if not already accessed
            signal = Signal(
                self.default_value, name=f"{obj.__class__.__name__}.{self.name}"
            )
            setattr(obj, self.private_name, signal)

        signal: Signal = getattr(obj, self.private_name)
        signal.write(value)


class StateMeta(ABCMeta):
    """
    Metaclass that automatically converts annotated attributes into reactive properties.
    """

    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        annotations = namespace.get("__annotations__", {})

        for attr_name in annotations:
            if not attr_name.startswith("_"):
                default_value = namespace.get(attr_name)
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
