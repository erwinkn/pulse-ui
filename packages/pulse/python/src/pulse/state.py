"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

import inspect
from abc import ABC, ABCMeta, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any, Generic, Never, Self, TypeVar, cast, override

from pulse.reactive import (
	AsyncEffect,
	Computed,
	Effect,
	Scope,
	Signal,
)
from pulse.reactive_extensions import ReactiveProperty, unwrap

if TYPE_CHECKING:
	from pulse.query import QueryResult

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
	fields: "dict[str, StateFieldMetadata]"

	def clone(self) -> "StateMetadata":
		return StateMetadata({name: meta.clone() for name, meta in self.fields.items()})


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
				if attr_name in namespace:
					defaults[attr_name] = namespace[attr_name]
				kinds[attr_name] = "private"
			else:
				if attr_name in namespace:
					defaults[attr_name] = namespace[attr_name]
				kinds[attr_name] = "signal"
				namespace[attr_name] = StateProperty(
					attr_name, namespace.get(attr_name)
				)

		# 2) Inspect remaining attributes for queries, private data, and plain values
		for attr_name, value in list(namespace.items()):
			if attr_name.startswith("__") and attr_name.endswith("__"):
				continue
			if _is_private(attr_name):
				if _is_plain_state_attribute(value):
					defaults[attr_name] = value
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
			object.__setattr__(instance, STATE_POST_INIT_FIELD, True)
			try:
				post_init()
			finally:
				object.__setattr__(instance, STATE_POST_INIT_FIELD, False)
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
		fields: "dict[str, StateFieldMetadata]" = {}

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
STATE_POST_INIT_FIELD = "__pulse_in_post_init__"
_INTERNAL_PRIVATE_NAMES = {
	STATE_STATUS_FIELD,
	"_scope",
	STATE_POST_INIT_FIELD,
}


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
	__state_metadata__: StateMetadata

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

	def __post_init__(self): ...

	@override
	def __setattr__(self, name: str, value: Any) -> None:
		if name.startswith("_"):
			if name.startswith("__") or name in _INTERNAL_PRIVATE_NAMES:
				super().__setattr__(name, value)
				return

			meta: StateMetadata | None = getattr(
				self.__class__, "__state_metadata__", None
			)
			field_meta = meta.fields.get(name) if meta else None

			status = getattr(self, STATE_STATUS_FIELD, StateStatus.UNINITIALIZED)
			in_post_init = bool(getattr(self, STATE_POST_INIT_FIELD, False))

			if (
				status == StateStatus.UNINITIALIZED
				and not in_post_init
				and field_meta is None
			):
				raise AttributeError(
					f"Cannot set undeclared private attribute '{name}' during __init__. "
					+ "Declare it on the class or assign it in __post_init__."
				)

			super().__setattr__(name, value)
			return

		if (
			getattr(self, STATE_STATUS_FIELD, StateStatus.UNINITIALIZED)
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

	def drain(self) -> dict[str, Any]:
		"""
		Drain the state into a serializable payload capturing drainable fields.

		The payload structure mirrors the plan requirements, returning the class
		version alongside a mapping of field values so the result can be
		persisted or pickled safely.
		"""
		meta: StateMetadata = self.__class__.__state_metadata__
		values: dict[str, Any] = {}
		for name, field_meta in meta.fields.items():
			if not field_meta.drain:
				continue
			try:
				value = getattr(self, name)
			except AttributeError:
				continue
			if field_meta.kind is StateFieldKind.QUERY:
				query_value = cast("QueryResult[Any]", value)
				values[name] = self._drain_query_snapshot(query_value)
				continue
			values[name] = unwrap(value, untrack=True)
		return {
			"__version__": getattr(self.__class__, "__version__", 1),
			"values": values,
		}

	@override
	def __getstate__(self) -> dict[str, Any]:
		"""Delegate pickling to drain so Python tooling uses Pulse semantics."""
		return self.drain()

	@staticmethod
	def _drain_query_snapshot(query_value: "QueryResult[Any]") -> dict[str, Any]:
		"""
		Create a serializable snapshot of a preserved query result.
		"""
		return {
			"data": unwrap(query_value.data, untrack=True),
			"is_loading": bool(query_value.is_loading),
			"is_error": bool(query_value.is_error),
			"error": query_value.error,
			"has_loaded": bool(query_value.has_loaded),
		}

	def hydrate(self, state: dict[str, Any]) -> Self:
		"""
		Rehydrate a state from a previously drained payload, applying migrations,
		defaults, and preserved query snapshots as necessary.
		"""
		if not isinstance(state, dict):
			raise TypeError(
				f"{self.__class__.__name__}.hydrate expected payload to be a dict, "
				+ f"got {type(state).__name__!s}"
			)

		if "__version__" not in state:
			raise ValueError(
				f"{self.__class__.__name__}.hydrate payload missing '__version__' entry"
			)

		raw_version = state["__version__"]
		try:
			start_version = int(raw_version)
		except (TypeError, ValueError) as exc:
			raise ValueError(
				f"{self.__class__.__name__}.hydrate received non-integer '__version__': {raw_version!r}"
			) from exc

		try:
			values = state["values"]
		except Exception as exc:
			raise ValueError(
				f"{self.__class__.__name__}.hydrate payload access failed for 'values': {exc}"
			) from exc

		if not isinstance(values, dict):
			raise ValueError(
				f"{self.__class__.__name__}.hydrate expected 'values' to be a dict, "
				+ f"got {type(values).__name__!s}"
			)

		values = cast(dict[str, Any], values).copy()

		target_version = self.__version__
		if start_version > target_version:
			raise ValueError(
				f"{self.__class__.__name__} cannot down-hydrate from version "
				+ f"{start_version} into older schema {target_version}"
			)

		if start_version != target_version:
			try:
				values = self.__migrate__(start_version, target_version, dict(values))
			except NotImplementedError as exc:
				raise RuntimeError(
					f"{self.__class__.__name__} is missing migration coverage for payload "
					+ f"version {start_version} -> {target_version}"
				) from exc
			if not isinstance(values, dict):
				raise TypeError(
					f"{self.__class__.__name__}.__migrate__ must return a dict, got "
					+ f"{type(values).__name__!s}"
				)

		meta: StateMetadata = self.__state_metadata__
		preserved_query_snapshots: dict[str, dict[str, Any]] = {}
		missing_required: list[str] = []

		for name, field_meta in meta.fields.items():
			# Queries
			if field_meta.kind is StateFieldKind.QUERY:
				# We ignore preserved queries without a snapshot
				if field_meta.drain and name in values:
					snapshot = values.pop(name)
					if not isinstance(snapshot, dict):
						raise ValueError(
							f"{self.__class__.__name__}.hydrate expected preserved query '{name}' "
							+ f"to supply a dict snapshot, got {type(snapshot).__name__!s}"
						)
					preserved_query_snapshots[name] = snapshot
				continue

			if field_meta.kind is StateFieldKind.SIGNAL:
				if name in values:
					value = values.pop(name)
					setattr(self, name, value)
				elif field_meta.has_default:
					setattr(self, name, field_meta.default)
				else:
					missing_required.append(name)
				continue

			if field_meta.kind is StateFieldKind.PRIVATE:
				if name in values:
					value = values.pop(name)
					setattr(self, name, value)
				elif field_meta.has_default:
					setattr(self, name, field_meta.default)
				continue

		if missing_required:
			field_list = ", ".join(sorted(missing_required))
			raise ValueError(
				f"{self.__class__.__name__}.hydrate missing values for fields without defaults: "
				+ f"{field_list}. Provide defaults or supply values via __migrate__."
			)

		# Run the post-init hook to mirror normal construction.
		object.__setattr__(self, STATE_POST_INIT_FIELD, True)
		try:
			self.__post_init__()
		finally:
			object.__setattr__(self, STATE_POST_INIT_FIELD, False)

		# _initialize() will populate queries and scope/effects.
		self._initialize()

		# Rehydrate preserved query snapshots after queries have been initialized.
		for name, snapshot in preserved_query_snapshots.items():
			data = snapshot.get("data", None)
			is_loading = bool(snapshot.get("is_loading", False))
			is_error = bool(snapshot.get("is_error", False))
			error = snapshot.get("error", None)
			has_loaded = bool(snapshot.get("has_loaded", False))
			query_result = getattr(self, name)

			# Interact with QueryResult internals directly to avoid scheduling fetches.
			try:
				query_result._data.write(data)
				query_result._initial_data = data
				query_result._is_loading.write(is_loading)
				query_result._is_error.write(is_error)
				query_result._error.write(error)
				query_result._has_loaded.write(has_loaded)
			except AttributeError as e:
				raise TypeError(
					"Preserved query hydration expected a QueryResult-compatible object."
				) from e

		missing_private_after_init: list[str] = []
		for name, field_meta in meta.fields.items():
			if field_meta.kind is StateFieldKind.PRIVATE and not hasattr(self, name):
				missing_private_after_init.append(name)

		if missing_private_after_init:
			field_list = ", ".join(sorted(missing_private_after_init))
			raise ValueError(
				f"{self.__class__.__name__}.hydrate missing private fields after initialization: "
				+ f"{field_list}. Ensure __post_init__ assigns these attributes or provide defaults."
			)

		return self

	def __setstate__(self, state: dict[str, Any]) -> None:
		"""Support Python pickling by delegating to hydrate."""
		self.hydrate(state)
