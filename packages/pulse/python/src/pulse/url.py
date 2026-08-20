"""The URL currently displayed by a render session's browser tab."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode

from pulse.helpers import values_equal
from pulse.messages import ServerNavigateToMessage
from pulse.reactive import Effect, Scope, Signal, Untrack
from pulse.reactive_extensions import ReactiveDict, reactive, unwrap
from pulse.state.query_param import (
	QueryParamCodec,
	parse_query_param_value,
	serialize_query_param_value,
)


@dataclass
class _QueryParamSlot:
	codec: QueryParamCodec
	default: Any
	signal: Signal[Any]


class SessionUrl(ReactiveDict[str, Any]):
	"""The URL currently displayed by the session's browser tab.

	A render session is one browser tab, so it has exactly one URL. Every
	mount reports the same pathname/hash/query params (they all derive from
	the client's single ``location``); only ``pathParams``/``catchall`` are
	mount-specific, and those live on `RouteContext`.

	Typed ``QueryParam`` fields share one Signal per name via ``param()``.
	"""

	_send: Callable[[ServerNavigateToMessage], Any]
	_slots: dict[str, _QueryParamSlot]
	_route_effect: Effect | None
	_state_effect: Effect | None

	def __init__(self, send: Callable[[ServerNavigateToMessage], Any]) -> None:
		super().__init__({"pathname": "", "hash": "", "queryParams": {}})
		self._send = send
		self._slots = {}
		self._route_effect = None
		self._state_effect = None

	def param(self, name: str, codec: QueryParamCodec, default: Any) -> Signal[Any]:
		if not name:
			raise RuntimeError("QueryParam param name was not resolved")
		slot = self._slots.get(name)
		if slot is None:
			raw = self["queryParams"].get(name)
			value: Any = parse_query_param_value(
				raw,
				default=default,
				codec=codec,
				param=name,
			)
			slot = _QueryParamSlot(
				codec=codec,
				default=default,
				signal=Signal(
					reactive(value),  # pyright: ignore[reportUnknownArgumentType]
					name=f"QueryParam.{name}",
				),
			)
			self._slots[name] = slot
			self._ensure_effects()
			return slot.signal
		if slot.codec != codec or not values_equal(slot.default, default):
			raise ValueError(
				f"QueryParam '{name}' is already registered as {slot.codec.label} "
				+ f"with default {slot.default!r}"
			)
		return slot.signal

	def prime(self) -> None:
		if self._route_effect and self._route_effect.runs == 0:
			self._route_effect.run()
		if self._state_effect:
			self._state_effect.run()

	def dispose(self) -> None:
		if self._route_effect:
			self._route_effect.dispose()
			self._route_effect = None
		if self._state_effect:
			self._state_effect.dispose()
			self._state_effect = None
		self._slots.clear()

	def _ensure_effects(self) -> None:
		if self._route_effect is None or self._state_effect is None:
			with Scope():
				if self._route_effect is None:
					self._route_effect = Effect(
						self._sync_from_route,
						name="SessionUrl:query_param:route",
						lazy=True,
					)
				if self._state_effect is None:
					self._state_effect = Effect(
						self._sync_to_route,
						name="SessionUrl:query_param:state",
						lazy=True,
					)

	def _apply_route_to_slot(self, name: str, slot: _QueryParamSlot) -> None:
		raw = self["queryParams"].get(name)
		parsed = parse_query_param_value(
			raw,
			default=slot.default,
			codec=slot.codec,
			param=name,
		)
		if values_equal(slot.signal.value, parsed):
			return
		slot.signal.write(reactive(parsed))

	def _sync_from_route(self) -> None:
		_ = self["queryParams"]
		if self._route_effect and self._route_effect.runs == 0:
			return
		for name, slot in self._slots.items():
			self._apply_route_to_slot(name, slot)

	def _sync_to_route(self) -> None:
		with Untrack():
			current_params = dict(cast(Mapping[str, str], self["queryParams"]))
			pathname = self["pathname"]
			hash_frag = self["hash"]
		if not pathname:
			return
		query_params = dict(current_params)
		for name, slot in self._slots.items():
			value = slot.signal.read()
			if slot.codec.kind == "list" and value is not None:
				value = unwrap(value)
			serialized = serialize_query_param_value(
				value,
				default=slot.default,
				codec=slot.codec,
				param=name,
			)
			if serialized is None:
				query_params.pop(name, None)
			else:
				query_params[name] = serialized

		if query_params == current_params:
			return
		path = pathname
		query = urlencode(query_params)
		if query:
			path += "?" + query
		if hash_frag:
			if hash_frag.startswith("#"):
				path += hash_frag
			else:
				path += "#" + hash_frag
		self._send(
			ServerNavigateToMessage(
				type="navigate_to",
				path=path,
				replace=True,
				hard=False,
				sourcePath=pathname,
			)
		)
