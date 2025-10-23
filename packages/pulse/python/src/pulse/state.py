"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

import inspect
from abc import ABC, ABCMeta, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, Generic, Never, TypeVar, override

from pulse.reactive import (
	AsyncEffect,
	Computed,
	Effect,
	Scope,
	Signal,
)
from pulse.reactive_extensions import MISSING, ReactiveProperty

T = TypeVar("T")


class StateProperty(ReactiveProperty[Any]):
	pass


class InitializableProperty(ABC):
	@abstractmethod
	def initialize(self, state: "State", name: str) -> Any: ...


class ComputedProperty(Generic[T]):
	"""
	Descriptor for computed properties on State classes.
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
	fn: "Callable[[State], T]"
	name: str | None
	immediate: bool
	on_error: "Callable[[Exception], None] | None"
	lazy: bool
	deps: "list[Signal[Any] | Computed[Any]] | None"

	def __init__(
		self,
		fn: "Callable[[State], T]",
		name: str | None = None,
		immediate: bool = False,
		lazy: bool = False,
		on_error: "Callable[[Exception], None] | None" = None,
		deps: "list[Signal[Any] | Computed[Any]] | None" = None,
	):
		self.fn = fn
		self.name = name
		self.immediate = immediate
		self.on_error = on_error
		self.lazy = lazy
		self.deps = deps

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
			)
		else:
			effect = Effect(
				bound_method,  # type: ignore[arg-type]
				name=self.name or f"{state.__class__.__name__}.{name}",
				immediate=self.immediate,
				lazy=self.lazy,
				on_error=self.on_error,
				deps=self.deps,
			)
		setattr(state, name, effect)


def _is_private(name: str) -> bool:
	return name.startswith("_") and not name.startswith("__")


def _is_plain_state_attribute(value: Any) -> bool:
	return not callable(value) and not isinstance(
		value,
		(
			staticmethod,
			classmethod,
			property,
			StateProperty,
			ComputedProperty,
			InitializableProperty,
		),
	)


class StateFieldKind(str, Enum):
	SIGNAL = "signal"
	QUERY = "query"
	PRIVATE = "private"


@dataclass
class StateFieldMetadata:
	name: str
	kind: StateFieldKind
	drain: bool
	has_default: bool
	default: Any = None
	descriptor: Any | None = None
	defined_on: type[Any] | None = None
	preserve: bool | None = None

	def clone(self) -> "StateFieldMetadata":
		return StateFieldMetadata(
			name=self.name,
			kind=self.kind,
			drain=self.drain,
			has_default=self.has_default,
			default=self.default,
			descriptor=self.descriptor,
			defined_on=self.defined_on,
			preserve=self.preserve,
		)


@dataclass
class StateMetadata:
	fields: "OrderedDict[str, StateFieldMetadata]"

	def clone(self) -> "StateMetadata":
		return StateMetadata(
			OrderedDict((name, meta.clone()) for name, meta in self.fields.items())
		)


class StateMeta(ABCMeta):
	"""
	Metaclass that automatically converts annotated attributes into reactive properties.
	"""

	def __new__(
		mcs,
		name: str,
		bases: tuple[type, ...],
		namespace: dict[str, Any],
		**kwargs: Any,
	):
		annotations = namespace.get("__annotations__", {})
		defaults: dict[str, Any] = {}
		kinds: dict[str, str] = {}

		# 1) Turn annotated fields into StateProperty descriptors (skipping private)
		for attr_name in annotations:
			if attr_name.startswith("__") and attr_name.endswith("__"):
				continue
			if _is_private(attr_name):
				defaults[attr_name] = (
					namespace[attr_name] if attr_name in namespace else MISSING
				)
				kinds[attr_name] = "private"
			else:
				has_default = attr_name in namespace
				default_value = namespace[attr_name] if has_default else None
				raw_default = default_value if has_default else MISSING
				defaults[attr_name] = raw_default
				kinds[attr_name] = "signal"
				namespace[attr_name] = StateProperty(attr_name, default_value)

		# 2) Inspect remaining attributes for queries, private data, and plain values
		for attr_name, value in list(namespace.items()):
			if attr_name.startswith("__") and attr_name.endswith("__"):
				continue
			if _is_private(attr_name):
				if _is_plain_state_attribute(value):
					defaults[attr_name] = value
				elif attr_name not in defaults:
					defaults[attr_name] = MISSING
				kinds[attr_name] = "private"
				continue
			if kinds.get(attr_name) == "signal":
				continue
			if getattr(value, "__pulse_kind__", None) == "query":
				kinds[attr_name] = "query"
				continue
			if not _is_plain_state_attribute(value):
				continue
			defaults[attr_name] = value
			kinds[attr_name] = "signal"
			namespace[attr_name] = StateProperty(attr_name, value)

		cls = super().__new__(mcs, name, bases, namespace)
		mcs._build_state_metadata(
			cls,
			defaults,
			kinds,
		)
		return cls

	@override
	def __call__(cls, *args: Any, **kwargs: Any):
		# Create the instance (runs __new__ and the class' __init__)
		instance = super().__call__(*args, **kwargs)
		post_init = getattr(instance, "__post_init__", None)
		if callable(post_init):
			post_init()
		# Ensure state effects are initialized even if user __init__ skipped super().__init__
		try:
			instance._initialize()
		except AttributeError:
			...
		return instance

	@staticmethod
	def _build_state_metadata(
		cls: type,  # pyright: ignore[reportSelfClsParameterName]
		defaults: dict[str, Any],
		kinds: dict[str, str],
	) -> None:
		fields: "OrderedDict[str, StateFieldMetadata]" = OrderedDict()

		for base in reversed(cls.__mro__[1:]):
			if base in (ABC, object):
				continue
			base_meta: StateMetadata | None = getattr(base, "__state_metadata__", None)
			if base_meta is None:
				continue
			for name, meta in base_meta.fields.items():
				fields[name] = meta.clone()

		for attr_name, kind in kinds.items():
			if kind == "signal":
				descriptor = getattr(cls, attr_name, None)
				if not isinstance(descriptor, StateProperty):
					continue
				default = defaults.get(attr_name, None)
				has_default = attr_name in defaults
				fields[attr_name] = StateFieldMetadata(
					name=attr_name,
					kind=StateFieldKind.SIGNAL,
					drain=True,
					has_default=has_default,
					default=default,
					descriptor=descriptor,
					defined_on=cls,
				)
			elif kind == "query":
				attr = getattr(cls, attr_name, None)
				preserve = bool(getattr(attr, "preserve", False))
				fields[attr_name] = StateFieldMetadata(
					name=attr_name,
					kind=StateFieldKind.QUERY,
					drain=preserve,
					has_default=False,
					default=None,
					descriptor=attr,
					defined_on=cls,
					preserve=preserve,
				)
			elif kind == "private":
				default = defaults.get(attr_name, None)
				has_default = attr_name in defaults
				fields[attr_name] = StateFieldMetadata(
					name=attr_name,
					kind=StateFieldKind.PRIVATE,
					drain=False,
					has_default=has_default,
					default=default,
					descriptor=None,
					defined_on=cls,
				)

		cls.__state_metadata__ = StateMetadata(fields)


class StateStatus(IntEnum):
	UNINITIALIZED = 0
	INITIALIZING = 1
	INITIALIZED = 2


STATE_STATUS_FIELD = "__pulse_status__"


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

	__version__: int = 1

	@classmethod
	def __migrate__(
		cls,
		start_version: int,
		target_version: int,
		values: dict[str, Any],
	) -> dict[str, Any]:
		raise NotImplementedError(
			f"{cls.__name__} must override __migrate__ to handle state migrations"
		)

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
		"""Iterate over the state's `Signal` instances, including base classes."""
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

		if len(set(self._scope.effects) - disposed) > 0:
			raise RuntimeError(
				f"State.dispose() missed effects defined on its Scope: {[e.name for e in self._scope.effects]}"
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
