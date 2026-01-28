"""
Descriptors for reactive state classes.
"""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, Never, TypeVar, override

from pulse.reactive import AsyncEffect, Computed, Effect, Signal
from pulse.reactive_extensions import ReactiveProperty

T = TypeVar("T")

if TYPE_CHECKING:
	from pulse.state.state import State


class StateProperty(ReactiveProperty[Any]):
	"""
	Descriptor for reactive properties on State classes.

	StateProperty wraps a Signal and provides automatic reactivity for
	class attributes. When a property is read, it subscribes to the underlying
	Signal. When written, it updates the Signal and triggers re-renders.

	This class is typically not used directly. Instead, declare typed attributes
	on a State subclass, and the StateMeta metaclass will automatically convert
	them into StateProperty instances.

	Example:

	```python
	class MyState(ps.State):
	    count: int = 0  # Automatically becomes a StateProperty
	    name: str = "default"

	state = MyState()
	state.count = 5  # Updates the underlying Signal
	print(state.count)  # Reads from the Signal, subscribes to changes
	```
	"""

	pass


class InitializableProperty(ABC):
	@abstractmethod
	def initialize(self, state: "State", name: str) -> Any: ...


class ComputedProperty(Generic[T]):
	"""
	Descriptor for computed (derived) properties on State classes.

	ComputedProperty wraps a method that derives its value from other reactive
	properties. The computed value is cached and only recalculated when its
	dependencies change. Reading a computed property subscribes to it.

	Created automatically when using the @ps.computed decorator on a State method.

	Args:
		name: The property name (used for debugging and the private storage key).
		fn: The method that computes the value. Must take only `self` as argument.

	Example:

	```python
	class MyState(ps.State):
	    count: int = 0

	    @ps.computed
	    def doubled(self):
	        return self.count * 2

	state = MyState()
	print(state.doubled)  # 0
	state.count = 5
	print(state.doubled)  # 10 (automatically recomputed)
	```
	"""

	name: str
	private_name: str
	fn: "Callable[[State], T]"

	def __init__(self, name: str, fn: "Callable[[State], T]"):
		self.name = name
		self.private_name = f"__computed_{name}"
		# The computed_template holds the original method
		self.fn = fn

	def get_computed(self, obj: Any) -> Computed[T]:
		from pulse.state.state import State

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
			return self  # pyright: ignore[reportReturnType]

		return self.get_computed(obj).read()

	def __set__(self, obj: Any, value: Any) -> Never:
		raise AttributeError(f"Cannot set computed property '{self.name}'")


class StateEffect(Generic[T], InitializableProperty):
	"""
	Descriptor for side effects on State classes.

	StateEffect wraps a method that performs side effects when its dependencies
	change. The effect is initialized when the State instance is created and
	disposed when the State is disposed.

	Created automatically when using the @ps.effect decorator on a State method.
	Supports both sync and async methods.

		Args:
			fn: The effect function. Must take only `self` as argument.
			        Can return a cleanup function that runs before the next execution
			        or when the effect is disposed.
		name: Debug name for the effect. Defaults to "ClassName.method_name".
		immediate: If True, run synchronously when scheduled (sync effects only).
		lazy: If True, don't run on creation; wait for first dependency change.
		on_error: Callback for handling errors during effect execution.
		deps: Explicit dependencies. If provided, auto-tracking is disabled.
		interval: Re-run interval in seconds for polling effects.

	Example:

	```python
	class MyState(ps.State):
	    count: int = 0

	    @ps.effect
	    def log_count(self):
	        print(f"Count changed to: {self.count}")

	    @ps.effect
	    async def fetch_data(self):
	        data = await api.fetch(self.query)
	        self.data = data

	    @ps.effect
	    def subscribe(self):
	        unsub = event_bus.subscribe(self.handle_event)
	        return unsub  # Cleanup function
	```
	"""

	fn: "Callable[[State], T]"
	name: str | None
	immediate: bool
	on_error: "Callable[[Exception], None] | None"
	lazy: bool
	deps: "list[Signal[Any] | Computed[Any]] | None"
	update_deps: bool | None
	interval: float | None

	def __init__(
		self,
		fn: "Callable[[State], T]",
		name: str | None = None,
		immediate: bool = False,
		lazy: bool = False,
		on_error: "Callable[[Exception], None] | None" = None,
		deps: "list[Signal[Any] | Computed[Any]] | None" = None,
		update_deps: bool | None = None,
		interval: float | None = None,
	):
		self.fn = fn
		self.name = name
		self.immediate = immediate
		self.on_error = on_error
		self.lazy = lazy
		self.deps = deps
		self.update_deps = update_deps
		self.interval = interval

	@override
	def initialize(self, state: "State", name: str):
		bound_method = self.fn.__get__(state, state.__class__)
		# Select sync/async effect type based on bound method
		if inspect.iscoroutinefunction(bound_method):
			effect: Effect = AsyncEffect(
				bound_method,  # type: ignore[arg-type]
				name=self.name or f"{state.__class__.__name__}.{name}",
				lazy=self.lazy,
				on_error=self.on_error,
				deps=self.deps,
				update_deps=self.update_deps,
				interval=self.interval,
			)
		else:
			effect = Effect(
				bound_method,  # type: ignore[arg-type]
				name=self.name or f"{state.__class__.__name__}.{name}",
				immediate=self.immediate,
				lazy=self.lazy,
				on_error=self.on_error,
				deps=self.deps,
				update_deps=self.update_deps,
				interval=self.interval,
			)
		setattr(state, name, effect)
