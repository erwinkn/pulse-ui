"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

import sys
from abc import ABC, ABCMeta
from collections.abc import Iterator
from enum import IntEnum
from typing import Any, get_type_hints, override

from pulse.helpers import Disposable
from pulse.reactive import Computed, Effect, Scope, Signal
from pulse.reactive_extensions import ReactiveProperty
from pulse.state.property import (
	ComputedProperty,
	InitializableProperty,
	StateEffect,
	StateProperty,
)
from pulse.state.query_param import QueryParam, QueryParamProperty, extract_query_param


class StateMeta(ABCMeta):
	"""
	Metaclass that automatically converts annotated attributes into reactive properties.

	When a class uses StateMeta (via inheriting from State), the metaclass:

	1. Converts all public type-annotated attributes into StateProperty descriptors
	2. Converts all public non-callable values into StateProperty descriptors
	3. Skips private attributes (starting with '_')
	4. Preserves existing descriptors (StateProperty, ComputedProperty, StateEffect)

	This enables the declarative state definition pattern:

	Example:

	```python
	class MyState(ps.State):
	    count: int = 0        # Becomes StateProperty
	    name: str = "test"    # Becomes StateProperty
	    _private: int = 0     # Stays as regular attribute (not reactive)

	    @ps.computed
	    def doubled(self):    # Becomes ComputedProperty
	        return self.count * 2
	```
	"""

	def __new__(
		mcs,
		name: str,
		bases: tuple[type, ...],
		namespace: dict[str, Any],
		**kwargs: Any,
	):
		declared_annotations = dict(namespace.get("__annotations__", {}))
		cls = super().__new__(mcs, name, bases, namespace)
		resolved_annotations: dict[str, Any] = {}
		if declared_annotations:
			module = sys.modules.get(cls.__module__)
			globalns = module.__dict__ if module else {}
			if "QueryParam" not in globalns:
				globalns["QueryParam"] = QueryParam
			try:
				hints = get_type_hints(
					cls,
					globalns=globalns,
					localns=dict(cls.__dict__),
				)
			except Exception as exc:
				raise TypeError(
					f"Failed to resolve type annotations for {cls.__name__}: {exc}"
				) from exc
			for key, value in declared_annotations.items():
				resolved_annotations[key] = hints.get(key, value)

		# 1) Turn annotated fields into StateProperty descriptors
		for attr_name, annotation in resolved_annotations.items():
			# Do not wrap private/dunder attributes as reactive
			if attr_name.startswith("_"):
				continue
			default_value = cls.__dict__.get(attr_name)
			value_type, is_query_param = extract_query_param(annotation)
			if is_query_param:
				cls.__annotations__[attr_name] = value_type
				prop = QueryParamProperty(
					attr_name,
					default_value,
					value_type,
				)
				setattr(cls, attr_name, prop)
				prop.__set_name__(cls, attr_name)
			else:
				prop = StateProperty(attr_name, default_value)
				setattr(cls, attr_name, prop)
				prop.__set_name__(cls, attr_name)

		# 2) Turn non-annotated plain values into StateProperty descriptors
		for attr_name, value in list(cls.__dict__.items()):
			# Do not wrap private/dunder attributes as reactive
			if attr_name.startswith("_"):
				continue
			# Skip if already set as a descriptor we care about
			if isinstance(
				value,
				(StateProperty, ComputedProperty, StateEffect, InitializableProperty),
			):
				continue
			# Skip common callables and descriptors
			if callable(value) or isinstance(
				value, (staticmethod, classmethod, property)
			):
				continue
			# Convert plain class var into a StateProperty
			prop = StateProperty(attr_name, value)
			setattr(cls, attr_name, prop)
			prop.__set_name__(cls, attr_name)

		return cls

	@override
	def __call__(cls, *args: Any, **kwargs: Any):
		# Create the instance (runs __new__ and the class' __init__)
		instance = super().__call__(*args, **kwargs)
		# Ensure state effects are initialized even if user __init__ skipped super().__init__
		try:
			initializer = instance._initialize
		except AttributeError:
			return instance
		initializer()
		return instance


class StateStatus(IntEnum):
	UNINITIALIZED = 0
	INITIALIZING = 1
	INITIALIZED = 2


STATE_STATUS_FIELD = "__pulse_status__"


class State(Disposable, metaclass=StateMeta):
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

	Override `on_dispose()` to run cleanup code when the state is disposed:
	```python
	class MyState(ps.State):
	    def on_dispose(self):
	        # Clean up timers, connections, etc.
	        self.timer.cancel()
	        self.connection.close()
	```
	"""

	@override
	def __setattr__(self, name: str, value: Any) -> None:
		if (
			# Allow writing private/internal attributes
			name.startswith("_")
			# Allow writing during initialization
			or getattr(self, STATE_STATUS_FIELD, StateStatus.UNINITIALIZED)
			== StateStatus.INITIALIZING
		):
			super().__setattr__(name, value)
			return

		# Route reactive properties through their descriptor
		cls_attr = getattr(self.__class__, name, None)
		if isinstance(cls_attr, ReactiveProperty):
			cls_attr.__set__(self, value)
			return

		if isinstance(cls_attr, ComputedProperty):
			raise AttributeError(f"Cannot set computed property '{name}'")

		# Reject all other public writes
		raise AttributeError(
			"Cannot set non-reactive property '"
			+ name
			+ "' on "
			+ self.__class__.__name__
			+ ". "
			+ "To make '"
			+ name
			+ "' reactive, declare it with a type annotation at the class level: "
			+ "'"
			+ name
			+ ": <type> = <default_value>'"
			+ "Otherwise, make it private with an underscore: 'self._"
			+ name
			+ " = <value>'"
		)

	_scope: Scope

	def _initialize(self):
		# Idempotent: avoid double-initialization when subclass calls super().__init__
		status = getattr(self, STATE_STATUS_FIELD, StateStatus.UNINITIALIZED)
		if status == StateStatus.INITIALIZED:
			return
		if status == StateStatus.INITIALIZING:
			raise RuntimeError(
				"Circular state initialization, this is a Pulse internal error"
			)
		setattr(self, STATE_STATUS_FIELD, StateStatus.INITIALIZING)

		self._scope = Scope()
		with self._scope:
			# Traverse MRO so effects declared on base classes are also initialized
			for cls in self.__class__.__mro__:
				if cls is State or cls is ABC:
					continue
				for name, attr in cls.__dict__.items():
					# If the attribute is shadowed in a subclass with a non-StateEffect, skip
					if getattr(self.__class__, name, attr) is not attr:
						continue
					if isinstance(attr, InitializableProperty):
						# Initialize properties like state effects or queries
						attr.initialize(self, name)

		setattr(self, STATE_STATUS_FIELD, StateStatus.INITIALIZED)

	def properties(self) -> Iterator[Signal[Any]]:
		"""
		Iterate over the state's reactive Signal instances.

		Traverses the class hierarchy (MRO) to include properties from base classes.
		Each Signal is yielded only once, even if shadowed in subclasses.

		Yields:
			Signal[Any]: Each reactive property's underlying Signal instance.

		Example:
			for signal in state.properties():
			    print(signal.name, signal.value)
		"""
		seen: set[str] = set()
		for cls in self.__class__.__mro__:
			if cls in (State, ABC):
				continue
			for name, prop in cls.__dict__.items():
				if name in seen:
					continue
				if isinstance(prop, ReactiveProperty):
					seen.add(name)
					yield prop.get_signal(self)

	def computeds(self) -> Iterator[Computed[Any]]:
		"""
		Iterate over the state's Computed instances.

		Traverses the class hierarchy (MRO) to include computed properties from
		base classes. Each Computed is yielded only once.

		Yields:
			Computed[Any]: Each computed property's underlying Computed instance.

		Example:
			for computed in state.computeds():
			    print(computed.name, computed.read())
		"""
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

	def effects(self) -> Iterator[Effect]:
		"""
		Iterate over the state's Effect instances.

		Returns effects that have been initialized on this state instance.
		Effects are created from @ps.effect decorated methods when the
		state is instantiated.

		Yields:
			Effect: Each effect instance attached to this state.

		Example:
			for effect in state.effects():
			    print(effect.name)
		"""
		for value in self.__dict__.values():
			if isinstance(value, Effect):
				yield value

	def on_dispose(self) -> None:
		"""
		Override this method to run cleanup code when the state is disposed.

		This is called automatically when `dispose()` is called, before effects are disposed.
		Use this to clean up timers, connections, or other resources.
		"""
		pass

	@override
	def dispose(self) -> None:
		"""
		Clean up the state, disposing all effects and resources.

		Calls on_dispose() first for user-defined cleanup, then disposes all
		Disposable instances attached to this state (including effects).

		This method is called automatically when the state goes out of scope
		or when explicitly cleaning up. After disposal, the state should not
		be used.

		Raises:
			RuntimeError: If any effects defined on the state's scope were not
			        properly disposed.
		"""
		# Call user-defined cleanup hook first
		self.on_dispose()
		for value in self.__dict__.values():
			if isinstance(value, Disposable):
				value.dispose()

		undisposed_effects = [e for e in self._scope.effects if not e.__disposed__]
		if len(undisposed_effects) > 0:
			raise RuntimeError(
				f"State.dispose() missed effects defined on its Scope: {[e.name for e in undisposed_effects]}"
			)

	@override
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
				if isinstance(value, ReactiveProperty):
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

	@override
	def __str__(self) -> str:
		"""Return a user-friendly representation of the state."""
		return self.__repr__()
