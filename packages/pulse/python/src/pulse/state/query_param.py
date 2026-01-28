"""
Query parameter bindings for State properties.
"""

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import UnionType
from typing import (
	TYPE_CHECKING,
	Any,
	Generic,
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
from pulse.reactive import Effect, Scope, Signal
from pulse.reactive_extensions import reactive, unwrap
from pulse.state.property import InitializableProperty, StateProperty

T = TypeVar("T")

if TYPE_CHECKING:
	from pulse.state.state import State


if TYPE_CHECKING:
	QueryParam: TypeAlias = T
else:

	class QueryParam(Generic[T]):
		"""
		Query parameter binding for State properties.

		Usage:
		    q: QueryParam[str] = ""
		    page: QueryParam[int] = 1

		At type-check time, QueryParam[T] is treated as T.
		At runtime, QueryParam[T] is detected by StateMeta and converted to QueryParamProperty.
		"""

		pass


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


def extract_query_param(annotation: Any) -> tuple[Any, bool]:
	"""Extract the inner type from QueryParam[T] if present."""
	origin = get_origin(annotation)
	if origin is QueryParam:
		args = get_args(annotation)
		if len(args) != 1:
			raise TypeError(
				"QueryParam expects a single type argument (e.g. QueryParam[str])."
			)
		return args[0], True
	return annotation, False


class QueryParamProperty(StateProperty, InitializableProperty):
	value_type: Any
	param_name: str
	codec: QueryParamCodec
	default_value: Any

	def __init__(
		self,
		name: str,
		default: Any,
		value_type: Any,
	):
		self.default_value = unwrap(default, untrack=True)
		super().__init__(name, default)
		self.value_type = value_type
		self.param_name = name
		self.codec = _build_query_param_codec(value_type)

	@override
	def __set_name__(self, owner: type[Any], name: str) -> None:
		super().__set_name__(owner, name)
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
		return self.prop.default_value

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
			codec = binding.codec()
			if codec.kind == "list" and value is not None:
				value = unwrap(value)
			serialized = _serialize_query_param_value(
				value,
				default=binding.default(),
				codec=codec,
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
			if hash_frag.startswith("#"):
				path += hash_frag
			else:
				path += "#" + hash_frag
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
