"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

from abc import ABC, ABCMeta
from typing import Any, Callable, Generic, Never, TypeVar

from pulse.reactive import Scope, Signal, Computed, Effect
from pulse.query import QueryProperty


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
    ):
        self.fn = fn

    def initialize(self, state: "State", name: str):
        bound_method = self.fn.__get__(state, state.__class__)
        effect = Effect(
            bound_method,
            name=f"{state.__class__.__name__}.{name}",
        )
        setattr(state, name, effect)


class StateMeta(ABCMeta):
    """
    Metaclass that automatically converts annotated attributes into reactive properties.
    """

    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        annotations = namespace.get("__annotations__", {})

        # 1) Turn annotated fields into StateProperty descriptors
        for attr_name in annotations:
            if attr_name.startswith("__"):
                continue
            default_value = namespace.get(attr_name)
            namespace[attr_name] = StateProperty(attr_name, default_value)

        # 2) Turn non-annotated plain values into StateProperty descriptors
        for attr_name, value in list(namespace.items()):
            if attr_name.startswith("__"):
                continue
            # Skip if already set as a descriptor we care about
            if isinstance(
                value, (StateProperty, ComputedProperty, StateEffect, QueryProperty)
            ):
                continue
            # Skip common callables and descriptors
            if callable(value) or isinstance(
                value, (staticmethod, classmethod, property)
            ):
                continue
            # Convert plain class var into a StateProperty
            namespace[attr_name] = StateProperty(attr_name, value)

        return super().__new__(mcs, name, bases, namespace)

    def __call__(cls, *args, **kwargs):
        # Create the instance (runs __new__ and the class' __init__)
        instance = super().__call__(*args, **kwargs)
        # Ensure state effects are initialized even if user __init__ skipped super().__init__
        try:
            initializer = getattr(instance, "_initialize")
        except AttributeError:
            return instance
        initializer()
        return instance


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

    __scope__: Scope

    def __init__(self):
        """Initializes the state and registers effects."""
        self._initialize()

    def _initialize(self):
        # Idempotent: avoid double-initialization when subclass calls super().__init__
        if getattr(self, "__state_initialized__", False):
            return
        setattr(self, "__state_initialized__", True)

        self.scope = Scope()
        with self.scope:
            # Traverse MRO so effects declared on base classes are also initialized
            for cls in self.__class__.__mro__:
                if cls is State or cls is ABC:
                    continue
                for name, attr in cls.__dict__.items():
                    # If the attribute is shadowed in a subclass with a non-StateEffect, skip
                    if getattr(self.__class__, name, attr) is not attr:
                        continue
                    # Validate query properties have a key defined
                    if isinstance(attr, QueryProperty):
                        if getattr(attr, "key_fn", None) is None:
                            raise RuntimeError(
                                f"State query '{name}' is missing a '@{name}.key' definition"
                            )
                        # Initialize query now so Effect exists and can be managed by hooks
                        attr.initialize(self)
                    if isinstance(attr, StateEffect):
                        attr.initialize(self, name)

    def properties(self):
        """Iterate over the state's `Signal` instances, including base classes."""
        seen: set[str] = set()
        for cls in self.__class__.__mro__:
            if cls in (State, ABC):
                continue
            for name, prop in cls.__dict__.items():
                if name in seen:
                    continue
                if isinstance(prop, StateProperty):
                    seen.add(name)
                    yield prop.get_signal(self)

    def computeds(self):
        """Iterate over the state's `Computed` instances, including base classes."""
        seen: set[str] = set()
        for cls in self.__class__.__mro__:
            if cls in (State, ABC):
                continue
            for name, comp_prop in cls.__dict__.items():
                if name in seen:
                    continue
                if isinstance(comp_prop, ComputedProperty):
                    seen.add(name)
                    yield comp_prop.get_computed(self)

    def effects(self):
        """Iterate over the state's `Effect` instances."""
        for value in self.__dict__.values():
            if isinstance(value, Effect):
                yield value
            # if isinstance(value,QueryProperty):
            #     value.

    def dispose(self):
        disposed = set()
        for value in self.__dict__.values():
            if isinstance(value, Effect):
                value.dispose()
                disposed.add(value)

        # TODO: remove this debug check
        if len(set(self.scope.effects) - disposed) > 0:
            raise RuntimeError(f"State.dispose() missed effects defined on its Scope: {[e.name for e in self.scope.effects]}")

    def __repr__(self) -> str:
        """Return a developer-friendly representation of the state."""
        props: list[str] = []

        # Include StateProperty values from MRO
        seen: set[str] = set()
        for cls in self.__class__.__mro__:
            if cls in (State, ABC):
                continue
            for name, value in cls.__dict__.items():
                if name in seen:
                    continue
                if isinstance(value, StateProperty):
                    seen.add(name)
                    prop_value = getattr(self, name)
                    props.append(f"{name}={prop_value!r}")

        # Include ComputedProperty values from MRO
        seen.clear()
        for cls in self.__class__.__mro__:
            if cls in (State, ABC):
                continue
            for name, value in cls.__dict__.items():
                if name in seen:
                    continue
                if isinstance(value, ComputedProperty):
                    seen.add(name)
                    prop_value = getattr(self, name)
                    props.append(f"{name}={prop_value!r} (computed)")

        return f"<{self.__class__.__name__} {' '.join(props)}>"

    def __str__(self) -> str:
        """Return a user-friendly representation of the state."""
        return self.__repr__()
