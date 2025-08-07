"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

from abc import ABC, ABCMeta
from typing import Any, Callable, Generic, Never, TypeVar

from pulse.reactive import Signal, Computed, Effect


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

    def get_signal(self, obj) -> Signal:
        if not hasattr(obj, self.private_name):
            # Create the signal on first access
            signal = Signal(
                self.default_value, name=f"{obj.__class__.__name__}.{self.name}"
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


class ComputedProperty(Generic[T]):
    """
    Descriptor for computed properties on State classes.
    """

    def __init__(self, name: str, fn: "Callable[[State], T]"):
        self.name = name
        self.private_name = f"__computed_{name}"
        # The computed_template holds the original method
        self.fn = fn

    def get_computed(self, obj) -> Computed[T]:
        if not isinstance(obj, State):
            raise ValueError(
                f"Computed property {self.name} defined on a non-State class"
            )
        if not hasattr(obj, self.private_name):
            # Create the computed on first access for this instance
            bound_method = self.fn.__get__(obj, obj.__class__)
            new_computed = Computed(
                bound_method,
                name=f"{obj.__class__.__name__}.{self.name}",
            )
            setattr(obj, self.private_name, new_computed)
        return getattr(obj, self.private_name)

    def __get__(self, obj: Any, objtype: Any = None) -> T:
        if obj is None:
            return self  # type: ignore

        return self.get_computed(obj).read()

    def __set__(self, obj: Any, value: Any) -> Never:
        raise AttributeError(f"Cannot set computed property '{self.name}'")


class StateEffect(Generic[T]):
    def __init__(
        self,
        fn: "Callable[[State], T]",
        immediate: bool = False,
    ):
        self.fn = fn
        self.immediate = immediate


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

        @ps.computed
        def double_count(self):
            return self.count * 2

        @ps.effect
        def print_count(self):
            print(f"Count is now: {self.count}")
    ```

    Properties will automatically trigger re-renders when changed.
    """

    def __init__(self):
        """Initializes the state and registers effects."""
        for name, attr in self.__class__.__dict__.items():
            if isinstance(attr, StateEffect):
                bound_method = attr.fn.__get__(self, self.__class__)
                effect = Effect(
                    bound_method,
                    name=f"{self.__class__.__name__}.{name}",
                    immediate=attr.immediate,
                    lazy=True,
                )
                # Set the effect directly on the instance, making it callable
                setattr(self, name, effect)

    def properties(self):
        """Iterate over the state's `Signal` instances."""
        for prop in self.__class__.__dict__.values():
            if isinstance(prop, StateProperty):
                yield prop.get_signal(self)

    def computeds(self):
        """Iterate over the state's `Computed` instances."""
        for comp_prop in self.__class__.__dict__.values():
            if isinstance(comp_prop, ComputedProperty):
                yield comp_prop.get_computed(self)

    def effects(self):
        """Iterate over the state's `Effect` instances."""
        for value in self.__dict__.values():
            if isinstance(value, Effect):
                yield value

    def dispose(self):
        for value in self.__dict__.values():
            if isinstance(value, Effect):
                value.dispose()

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
