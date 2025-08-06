"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

from abc import ABC, ABCMeta
from typing import Any, Callable, Never, TypeVar, cast
import functools

from pulse.reactive import Signal, Computed, Effect


T = TypeVar("T")
TState = TypeVar("TState", bound="State")


class StateProperty:
    """
    Descriptor that creates reactive properties on State classes.
    Tracks when properties are accessed and triggers updates when set.
    """

    def __init__(self, name: str, default_value: Any = None):
        self.name = name
        self.default_value = default_value
        self.private_name = f"__signal_{name}"

    def get_signal(self, obj) -> Signal:
        if not hasattr(obj, self.private_name):
            # Create the signal on first access
            signal = Signal(
                self.default_value, name=f"{obj.__class__.__name__}.{self.name}_{id}"
            )
            setattr(obj, self.private_name, signal)
            return signal

        return getattr(obj, self.private_name)

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self

        return self.get_signal(obj).read()

    def __set__(self, obj: Any, value: Any) -> None:
        signal = self.get_signal(obj)
        signal.write(value)


class ComputedProperty:
    """
    Descriptor for computed properties on State classes.
    """

    def __init__(self, name: str, computed: Computed):
        self.name = name
        self.computed = computed
        self.curried_obj = None

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self

        if self.curried_obj is None:
            self.curried_obj = obj
            # Since the computed has been defined as a method, it expects the
            # first argument to be the state object. We turn this into a regular
            # pulse.Computed, where the function doesn't take any argument.
            self.computed = Computed(
                lambda: self.computed.fn(obj),  # type: ignore
                name=self.computed.name,
            )

        if obj is not self.curried_obj:
            print("Obj:", obj)
            print("self.curried_obj:", self.curried_obj)
            raise RuntimeError(
                "Invariant violation: ComputedProperty must be accessed on the same object instance it was created for."
            )

        return self.computed.read()

    def __set__(self, obj: Any, value: Any) -> Never:
        raise AttributeError(f"Cannot set computed property '{self.name}'")


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

        for attr_name, attr_value in list(namespace.items()):
            if isinstance(attr_value, Computed):
                namespace[attr_name] = ComputedProperty(attr_name, attr_value)

        return super().__new__(mcs, name, bases, namespace)


class State(ABC, metaclass=StateMeta):
    """
    Base class for reactive state objects.

    Define state properties using type annotations:

    ```python
    class CounterState(ps.State):
        count: int = 0
        name: str = "Counter"

        @ps.computed
        def double_count(self):
            return self.count * 2

        @ps.state_effect
        def print_count(self):
            print(f"Count is now: {self.count}")
    ```

    Properties will automatically trigger re-renders when changed.
    """

    def __init__(self):
        """Initializes the state and registers effects."""
        # Effects are stored to keep them from being garbage collected.
        self._effects: list[Effect] = []
        for name, attr in self.__class__.__dict__.items():
            if callable(attr) and getattr(attr, "_is_effect", False):
                bound_method = getattr(self, name)
                effect = Effect(bound_method, name=f"{self.__class__.__name__}.{name}")
                self._effects.append(effect)

    def __repr__(self) -> str:
        """Return a developer-friendly representation of the state."""
        props = []

        # Annotated properties (Signals)
        for name in getattr(self.__class__, "__annotations__", {}):
            if not name.startswith("_"):
                prop_value = getattr(self, name)
                props.append(f"{name}={prop_value!r}")

        # Computed properties
        for name, value in self.__class__.__dict__.items():
            if isinstance(value, ComputedProperty):
                prop_value = getattr(self, name)
                props.append(f"{name}={prop_value!r} (computed)")

        return f"<{self.__class__.__name__} {' '.join(props)}>"

    def __str__(self) -> str:
        """Return a user-friendly representation of the state."""
        return self.__repr__()
