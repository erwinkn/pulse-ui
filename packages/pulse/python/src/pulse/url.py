"""The URL currently displayed by a render session's browser tab."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override
from urllib.parse import urlencode

from pulse.helpers import Disposable, values_equal
from pulse.messages import ServerNavigateToMessage
from pulse.reactive import Effect, Scope, Signal
from pulse.reactive_extensions import reactive, unwrap
from pulse.routing import RouteInfo
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


class SessionUrl(Disposable):
	"""The URL currently displayed by the session's browser tab.

	A render session is one browser tab, so it has exactly one URL. Every
	mount reports the same pathname/hash/query params (they all derive from
	the client's single ``location``); only ``pathParams``/``catchall`` are
	mount-specific, and those live on `RouteContext`.

	Typed ``QueryParam`` fields share one Signal per name via ``param()``.
	"""

	pathname: str
	hash: str
	query_params: dict[str, str]
	_send: Callable[[ServerNavigateToMessage], Any]
	_slots: dict[str, _QueryParamSlot]
	_sync_effect: Effect | None

	def __init__(self, send: Callable[[ServerNavigateToMessage], Any]) -> None:
		self.pathname = ""
		self.hash = ""
		self.query_params = {}
		self._send = send
		self._slots = {}
		self._sync_effect = None

	def apply(self, info: RouteInfo) -> None:
		"""Record the URL the client is currently displaying.

		Called by every `RouteContext` on creation and on route updates. All
		mounts report the same URL, so this is last-writer-wins by design.
		"""
		self.pathname = info["pathname"]
		self.hash = info["hash"]
		self.query_params = dict(info["queryParams"])
		for name, slot in self._slots.items():
			self._apply_slot(name, slot)

	def param(self, name: str, codec: QueryParamCodec, default: Any) -> Signal[Any]:
		if not name:
			raise RuntimeError("QueryParam param name was not resolved")
		slot = self._slots.get(name)
		if slot is None:
			raw = self.query_params.get(name)
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
			self._ensure_sync()
			return slot.signal
		if slot.codec != codec or not values_equal(slot.default, default):
			raise ValueError(
				f"QueryParam '{name}' is already registered as {slot.codec.label} "
				+ f"with default {slot.default!r}"
			)
		return slot.signal

	def prime(self) -> None:
		if self._sync_effect:
			self._sync_effect.run()

	@override
	def dispose(self) -> None:
		if self._sync_effect:
			self._sync_effect.dispose()
			self._sync_effect = None
		self._slots.clear()

	def _ensure_sync(self) -> None:
		if self._sync_effect is not None:
			return
		with Scope():
			self._sync_effect = Effect(
				self._sync_to_route,
				name="SessionUrl:query_param",
				lazy=True,
			)

	def _apply_slot(self, name: str, slot: _QueryParamSlot) -> None:
		raw = self.query_params.get(name)
		parsed = parse_query_param_value(
			raw,
			default=slot.default,
			codec=slot.codec,
			param=name,
		)
		if values_equal(slot.signal.value, parsed):
			return
		slot.signal.write(reactive(parsed))

	def _sync_to_route(self) -> None:
		if not self.pathname:
			return
		current_params = dict(self.query_params)
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
		path = self.pathname
		query = urlencode(query_params)
		if query:
			path += "?" + query
		if self.hash:
			if self.hash.startswith("#"):
				path += self.hash
			else:
				path += "#" + self.hash
		self._send(
			ServerNavigateToMessage(
				type="navigate_to",
				path=path,
				replace=True,
				hard=False,
				sourcePath=self.pathname,
			)
		)
