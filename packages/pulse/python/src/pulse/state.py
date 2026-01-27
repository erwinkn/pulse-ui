"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

import inspect
import sys
import warnings
from abc import ABC, ABCMeta, abstractmethod
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import IntEnum
from types import UnionType
from typing import (
	TYPE_CHECKING,
	Annotated,
	Any,
	Generic,
	Never,
	TypeAlias,
	TypeVar,
	cast,
	get_args,
	get_origin,
	override,
)
from urllib.parse import urlencode

from pulse.context import PulseContext
from pulse.helpers import Disposable, values_equal
from pulse.reactive import (
	AsyncEffect,
	Computed,
	Effect,
	Scope,
	Signal,
)
from pulse.reactive_extensions import ReactiveProperty, reactive

T = TypeVar("T")


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


@dataclass(frozen=True)
class QueryParamSpec:
	name: str | None = None


if TYPE_CHECKING:
	QueryParam: TypeAlias = Annotated[T, QueryParamSpec]
else:

	class QueryParam(Generic[T]):
		def __class_getitem__(cls, params: Any):
			if not isinstance(params, tuple):
				params = (params,)
			if len(params) == 0 or len(params) > 2:
				raise TypeError(
					"QueryParam[...] expects a value type and an optional param name"
				)
			value_type = params[0]
			name: str | None = None
			if len(params) == 2:
				name = params[1]
				if not isinstance(name, str) or name == "":
					raise TypeError("QueryParam name must be a non-empty string")
			return Annotated[value_type, QueryParamSpec(name)]


@dataclass(frozen=True)
class QueryParamCodec:
	kind: str
	label: str
	optional: bool = False
	item: "QueryParamCodec | None" = None


def _query_param_warning(message: str) -> None:
	warnings.warn(message, stacklevel=3)


def _coerce_datetime(value: datetime, *, param: str) -> datetime:
	if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
		_query_param_warning(
			"[Pulse] QueryParam '" + param + "' received naive datetime; assuming UTC."
		)
		return value.replace(tzinfo=timezone.utc)
	return value


def _parse_bool(raw: str, *, param: str) -> bool:
	normalized = raw.strip().lower()
	if normalized in ("true", "1"):
		return True
	if normalized in ("false", "0"):
		return False
	raise ValueError(f"QueryParam '{param}' expected bool, got '{raw}'")


def _parse_date(raw: str, *, param: str) -> date:
	try:
		return date.fromisoformat(raw)
	except ValueError as exc:
		raise ValueError(
			f"QueryParam '{param}' expected date (YYYY-MM-DD), got '{raw}'"
		) from exc


def _parse_datetime(raw: str, *, param: str) -> datetime:
	value = raw
	if value.endswith("Z") or value.endswith("z"):
		value = value[:-1] + "+00:00"
	try:
		parsed = datetime.fromisoformat(value)
	except ValueError as exc:
		raise ValueError(
			f"QueryParam '{param}' expected datetime (ISO 8601), got '{raw}'"
		) from exc
	return _coerce_datetime(parsed, param=param)


def _serialize_datetime(value: datetime, *, param: str) -> str:
	coerced = _coerce_datetime(value, param=param)
	result = coerced.isoformat()
	if coerced.utcoffset() == timedelta(0) and result.endswith("+00:00"):
		return result[:-6] + "Z"
	return result


def _escape_list_item(value: str) -> str:
	return value.replace("\\", "\\\\").replace(",", "\\,")


def _split_list_items(raw: str, *, param: str) -> list[str]:
	if raw == "":
		return []
	items: list[str] = []
	buf: list[str] = []
	escaping = False
	for ch in raw:
		if escaping:
			if ch not in ("\\", ","):
				raise ValueError(f"QueryParam '{param}' has invalid escape '\\{ch}'")
			buf.append(ch)
			escaping = False
			continue
		if ch == "\\":
			escaping = True
			continue
		if ch == ",":
			items.append("".join(buf))
			buf = []
			continue
		buf.append(ch)
	if escaping:
		raise ValueError(f"QueryParam '{param}' has trailing escape '\\\\'")
	items.append("".join(buf))
	return items


def _is_union_origin(origin: Any) -> bool:
	return origin is UnionType or (
		getattr(origin, "__module__", "") == "typing"
		and getattr(origin, "__qualname__", "") == "Union"
	)


def _build_query_param_codec(value_type: Any) -> QueryParamCodec:
	origin = get_origin(value_type)
	args = get_args(value_type)
	if _is_union_origin(origin):
		non_none = [arg for arg in args if arg is not type(None)]
		if len(non_none) != len(args) - 1:
			raise TypeError("QueryParam Optional types must include exactly one None")
		if len(non_none) != 1:
			raise TypeError("QueryParam Optional types must wrap a single type")
		inner = _build_query_param_codec(non_none[0])
		return QueryParamCodec(
			kind=inner.kind,
			label=inner.label,
			optional=True,
			item=inner.item,
		)
	if origin is list:
		if len(args) != 1:
			raise TypeError("QueryParam list types must specify an item type")
		item_codec = _build_query_param_codec(args[0])
		if item_codec.kind == "list":
			raise TypeError("QueryParam list types cannot be nested")
		return QueryParamCodec(
			kind="list",
			label=f"list[{item_codec.label}]",
			item=item_codec,
		)
	if value_type is str:
		return QueryParamCodec(kind="str", label="str")
	if value_type is int:
		return QueryParamCodec(kind="int", label="int")
	if value_type is float:
		return QueryParamCodec(kind="float", label="float")
	if value_type is bool:
		return QueryParamCodec(kind="bool", label="bool")
	if value_type is date:
		return QueryParamCodec(kind="date", label="date")
	if value_type is datetime:
		return QueryParamCodec(kind="datetime", label="datetime")
	raise TypeError(f"Unsupported QueryParam type: {value_type!r}")


def _parse_query_param_scalar(raw: str, *, codec: QueryParamCodec, param: str) -> Any:
	if raw == "" and codec.optional:
		return None
	if codec.kind == "str":
		return raw
	if codec.kind == "int":
		try:
			return int(raw)
		except ValueError as exc:
			raise ValueError(f"QueryParam '{param}' expected int, got '{raw}'") from exc
	if codec.kind == "float":
		try:
			return float(raw)
		except ValueError as exc:
			raise ValueError(
				f"QueryParam '{param}' expected float, got '{raw}'"
			) from exc
	if codec.kind == "bool":
		return _parse_bool(raw, param=param)
	if codec.kind == "date":
		return _parse_date(raw, param=param)
	if codec.kind == "datetime":
		return _parse_datetime(raw, param=param)
	raise TypeError(f"Unsupported QueryParam codec '{codec.kind}'")


def _parse_query_param_value(
	raw: str | None,
	*,
	default: Any,
	codec: QueryParamCodec,
	param: str,
) -> Any:
	if raw is None:
		if codec.optional:
			return None
		return default
	if raw == "" and codec.optional:
		return None
	if codec.kind == "list":
		assert codec.item is not None
		items: list[Any] = []
		for token in _split_list_items(raw, param=param):
			if token == "" and codec.item.optional:
				items.append(None)
				continue
			items.append(
				_parse_query_param_scalar(token, codec=codec.item, param=param)
			)
		return reactive(items)
	return _parse_query_param_scalar(raw, codec=codec, param=param)


def _serialize_query_param_scalar(
	value: Any, *, codec: QueryParamCodec, param: str
) -> str:
	if codec.kind == "str":
		if not isinstance(value, str):
			raise TypeError(f"QueryParam '{param}' expected str, got {type(value)!r}")
		return value
	if codec.kind == "int":
		if not isinstance(value, int) or isinstance(value, bool):
			raise TypeError(f"QueryParam '{param}' expected int, got {type(value)!r}")
		return str(value)
	if codec.kind == "float":
		if not isinstance(value, float):
			raise TypeError(f"QueryParam '{param}' expected float, got {type(value)!r}")
		return str(value)
	if codec.kind == "bool":
		if not isinstance(value, bool):
			raise TypeError(f"QueryParam '{param}' expected bool, got {type(value)!r}")
		return "true" if value else "false"
	if codec.kind == "date":
		if not isinstance(value, date) or isinstance(value, datetime):
			raise TypeError(f"QueryParam '{param}' expected date, got {type(value)!r}")
		return value.isoformat()
	if codec.kind == "datetime":
		if not isinstance(value, datetime):
			raise TypeError(
				f"QueryParam '{param}' expected datetime, got {type(value)!r}"
			)
		return _serialize_datetime(value, param=param)
	raise TypeError(f"Unsupported QueryParam codec '{codec.kind}'")


def _serialize_query_param_value(
	value: Any,
	*,
	default: Any,
	codec: QueryParamCodec,
	param: str,
) -> str | None:
	if value is None:
		return None
	if values_equal(value, default):
		return None
	if codec.kind == "list":
		if not isinstance(value, list):
			raise TypeError(f"QueryParam '{param}' expected list, got {type(value)!r}")
		assert codec.item is not None
		items = cast(list[Any], value)
		if len(items) == 0:
			return None
		parts: list[str] = []
		for item in items:
			if item is None:
				if codec.item.optional:
					parts.append("")
					continue
				raise TypeError(f"QueryParam '{param}' list items cannot be None")
			parts.append(
				_escape_list_item(
					_serialize_query_param_scalar(item, codec=codec.item, param=param)
				)
			)
		return ",".join(parts)
	return _serialize_query_param_scalar(value, codec=codec, param=param)


def _extract_query_param_spec(annotation: Any) -> tuple[Any, QueryParamSpec | None]:
	origin = get_origin(annotation)
	if origin is Annotated:
		args = get_args(annotation)
		base = args[0]
		specs = [meta for meta in args[1:] if isinstance(meta, QueryParamSpec)]
		if len(specs) > 1:
			raise TypeError(
				"QueryParam annotation cannot include multiple QueryParam specs"
			)
		return base, specs[0] if specs else None
	return annotation, None


class QueryParamProperty(StateProperty, InitializableProperty):
	value_type: Any
	param_name: str | None
	codec: QueryParamCodec

	def __init__(
		self,
		name: str,
		default: Any,
		value_type: Any,
		param_name: str | None,
	):
		super().__init__(name, default)
		self.value_type = value_type
		self.param_name = param_name
		self.codec = _build_query_param_codec(value_type)

	@override
	def __set_name__(self, owner: type[Any], name: str) -> None:
		super().__set_name__(owner, name)
		if self.param_name is None:
			self.param_name = name

	@override
	def initialize(self, state: "State", name: str) -> None:
		ctx = PulseContext.get()
		if ctx.render is None or ctx.route is None:
			raise RuntimeError(
				"QueryParam properties require a route render context. Create the state inside a component render."
			)
		sync = _get_query_param_sync(ctx.render, ctx.route)
		sync.register(state, name, self)


@dataclass
class QueryParamBinding:
	param: str
	state: "State"
	prop: QueryParamProperty
	attr_name: str

	def signal(self) -> Signal[Any]:
		return self.prop.get_signal(self.state)

	def default(self) -> Any:
		return self.prop.default

	def codec(self) -> QueryParamCodec:
		return self.prop.codec


class QueryParamSync(Disposable):
	route: Any
	render: Any
	_bindings: dict[str, QueryParamBinding]
	_route_effect: Effect | None
	_state_effect: Effect | None

	def __init__(self, render: Any, route: Any) -> None:
		self.render = render
		self.route = route
		self._bindings = {}
		self._route_effect = None
		self._state_effect = None

	def register(
		self, state: "State", attr_name: str, prop: QueryParamProperty
	) -> None:
		param = prop.param_name
		if not param:
			raise RuntimeError("QueryParam param name was not resolved")
		if param in self._bindings:
			raise ValueError(f"QueryParam '{param}' is already bound in this route")
		binding = QueryParamBinding(
			param=param,
			state=state,
			prop=prop,
			attr_name=attr_name,
		)
		self._bindings[param] = binding
		self._ensure_effects()
		self._apply_route_to_binding(binding)
		self._prime_effects()

	def _ensure_effects(self) -> None:
		if self._route_effect is None or self._state_effect is None:
			with Scope():
				if self._route_effect is None:
					self._route_effect = Effect(
						self._sync_from_route,
						name="QueryParamSync:route",
						lazy=True,
					)
				if self._state_effect is None:
					self._state_effect = Effect(
						self._sync_to_route,
						name="QueryParamSync:state",
						lazy=True,
					)

	def _prime_effects(self) -> None:
		if self._route_effect:
			self._route_effect.run()
		if self._state_effect:
			self._state_effect.run()

	def _query_params_untracked(self) -> dict[str, str]:
		try:
			query_params = dict.__getitem__(self.route.info, "queryParams")
		except KeyError:
			return {}
		if isinstance(query_params, dict):
			return dict(cast(dict[str, str], query_params))
		return dict(cast(Mapping[str, str], query_params))

	def _hash_untracked(self) -> str:
		try:
			return dict.__getitem__(self.route.info, "hash")
		except KeyError:
			return ""

	def _pathname_untracked(self) -> str:
		try:
			return dict.__getitem__(self.route.info, "pathname")
		except KeyError:
			return "/"

	def _apply_route_to_binding(self, binding: QueryParamBinding) -> None:
		query_params = self.route.queryParams
		raw = query_params.get(binding.param)
		parsed = _parse_query_param_value(
			raw,
			default=binding.default(),
			codec=binding.codec(),
			param=binding.param,
		)
		signal = binding.signal()
		current = signal.value
		if values_equal(current, parsed):
			return
		binding.prop.__set__(binding.state, parsed)

	def _sync_from_route(self) -> None:
		_ = self.route.queryParams
		for binding in self._bindings.values():
			self._apply_route_to_binding(binding)

	def _sync_to_route(self) -> None:
		query_params = self._query_params_untracked()
		for binding in self._bindings.values():
			signal = binding.signal()
			value = signal.read()
			serialized = _serialize_query_param_value(
				value,
				default=binding.default(),
				codec=binding.codec(),
				param=binding.param,
			)
			if serialized is None:
				query_params.pop(binding.param, None)
			else:
				query_params[binding.param] = serialized

		current_params = self._query_params_untracked()
		if query_params == current_params:
			return
		path = self._pathname_untracked()
		query = urlencode(query_params)
		if query:
			path += "?" + query
		hash_frag = self._hash_untracked()
		if hash_frag:
			path += hash_frag
		self.render.send(
			{
				"type": "navigate_to",
				"path": path,
				"replace": True,
				"hard": False,
			}
		)

	@override
	def dispose(self) -> None:
		if self._route_effect:
			self._route_effect.dispose()
			self._route_effect = None
		if self._state_effect:
			self._state_effect.dispose()
			self._state_effect = None
		self._bindings.clear()


def _get_query_param_sync(render: Any, route: Any) -> QueryParamSync:
	try:
		sync = route._query_param_sync
	except AttributeError:
		sync = QueryParamSync(render, route)
		route._query_param_sync = sync
	return sync


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
		annotations = namespace.get("__annotations__", {})
		if annotations:
			module = namespace.get("__module__")
			globalns = sys.modules[module].__dict__ if module in sys.modules else {}
			for key, value in list(annotations.items()):
				if isinstance(value, str) and "QueryParam" in value:
					try:
						annotations[key] = eval(value, globalns, namespace)
					except Exception:
						pass

		# 1) Turn annotated fields into StateProperty descriptors
		for attr_name, annotation in annotations.items():
			# Do not wrap private/dunder attributes as reactive
			if attr_name.startswith("_"):
				continue
			default_value = namespace.get(attr_name)
			value_type, spec = _extract_query_param_spec(annotation)
			if spec is not None:
				annotations[attr_name] = value_type
				namespace[attr_name] = QueryParamProperty(
					attr_name,
					default_value,
					value_type,
					spec.name,
				)
			else:
				namespace[attr_name] = StateProperty(attr_name, default_value)

		# 2) Turn non-annotated plain values into StateProperty descriptors
		for attr_name, value in list(namespace.items()):
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
			namespace[attr_name] = StateProperty(attr_name, value)

		return super().__new__(mcs, name, bases, namespace)

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
