"""The URL currently displayed by a render session's browser tab."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, override
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
class _TypedView:
	codec: QueryParamCodec
	default: Any
	signal: Signal[Any]


@dataclass
class _QueryParamSlot:
	raw: Signal[str | None]
	views: list[_TypedView]


class SessionUrl(Disposable):
	"""The URL currently displayed by the session's browser tab.

	A render session is one browser tab, so it has exactly one URL. Every
	mount reports the same pathname/hash/query params (they all derive from
	the client's single ``location``); only ``pathParams``/``catchall`` are
	mount-specific, and those live on `RouteContext`.

	Typed ``QueryParam`` fields share one raw slot per name via ``param()``.
	Each declaration gets a typed view of that raw value, so declarations
	with different codecs or defaults can coexist.

	Slot writes are immediate and session-owned. If a State constructor raises
	after writing a query parameter, its write is intentionally retained for
	other states sharing the session slot.
	"""

	pathname: str
	hash: str
	query_params: dict[str, str]
	_send: Callable[[ServerNavigateToMessage], Any]
	_slots: dict[str, _QueryParamSlot]
	_sync_effect: Effect | None
	_applied_params: dict[str, str]
	_commanded_params: dict[str, str] | None
	_closed: bool
	_route_revision: Signal[int]
	__idempotent_dispose__: ClassVar[bool] = True

	def __init__(self, send: Callable[[ServerNavigateToMessage], Any]) -> None:
		self.pathname = ""
		self.hash = ""
		self.query_params = {}
		self._send = send
		self._slots = {}
		self._sync_effect = None
		self._applied_params = {}
		self._commanded_params = None
		self._closed = False
		self._route_revision = Signal(0, name="SessionUrl:route_revision")

	def apply(self, info: RouteInfo) -> None:
		"""Record the URL the client is currently displaying.

		Called by every `RouteContext` on creation and on route updates. All
		mounts report the same URL, so this is last-writer-wins by design.
		"""
		if self._closed:
			return
		self.pathname = info["pathname"]
		self.hash = info["hash"]
		self._route_revision.write(self._route_revision.value + 1)
		incoming_params = dict(info["queryParams"])
		for name, slot in self._slots.items():
			incoming = incoming_params.get(name)
			applied = self._applied_params.get(name)
			if incoming != applied and (
				self._commanded_params is None
				or incoming != self._commanded_params.get(name)
			):
				self._set_raw(name, slot, incoming)
		self._applied_params = incoming_params
		self.query_params = incoming_params
		if self._sync_effect is not None:
			self._sync_effect.schedule()

	def param(self, name: str, codec: QueryParamCodec, default: Any) -> Signal[Any]:
		if self._closed:
			raise RuntimeError("SessionUrl is closed")
		if not name:
			raise RuntimeError("QueryParam param name was not resolved")
		slot = self._slots.get(name)
		if slot is None:
			raw = self.query_params.get(name)
			value = self._parse(raw, codec=codec, default=default, name=name)
			view = _TypedView(
				codec=codec,
				default=default,
				signal=Signal(
					reactive(value),  # pyright: ignore[reportUnknownArgumentType]
					name=f"QueryParam.{name}",
				),
			)
			slot = _QueryParamSlot(
				raw=Signal(raw, name=f"QueryParam.raw.{name}"),
				views=[view],
			)
			self._slots[name] = slot
			self._ensure_sync()
			return view.signal
		for view in slot.views:
			if view.codec == codec and values_equal(view.default, default):
				return view.signal
		value = self._parse(
			slot.raw.value,
			codec=codec,
			default=default,
			name=name,
		)
		view = _TypedView(
			codec=codec,
			default=default,
			signal=Signal(
				reactive(value),  # pyright: ignore[reportUnknownArgumentType]
				name=f"QueryParam.{name}",
			),
		)
		slot.views.append(view)
		return view.signal

	def prime(self) -> None:
		if self._sync_effect is not None and not self._closed:
			self._sync_effect.schedule()

	@override
	def dispose(self) -> None:
		if self._closed:
			return
		self._closed = True
		if self._sync_effect is not None:
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

	def _parse(
		self,
		raw: str | None,
		*,
		codec: QueryParamCodec,
		default: Any,
		name: str,
	) -> Any:
		return parse_query_param_value(
			raw,
			default=default,
			codec=codec,
			param=name,
		)

	def _set_raw(self, name: str, slot: _QueryParamSlot, raw: str | None) -> None:
		slot.raw.write(raw)
		for view in slot.views:
			parsed = self._parse(
				raw,
				codec=view.codec,
				default=view.default,
				name=name,
			)
			if values_equal(view.signal.value, parsed):
				continue
			view.signal.write(reactive(parsed))

	def _sync_to_route(self) -> None:
		self._route_revision.read()
		if not self.pathname:
			return
		for name, slot in self._slots.items():
			for view in slot.views:
				value = view.signal.read()
				if view.codec.kind == "list" and value is not None:
					value = unwrap(value)
				serialized = serialize_query_param_value(
					value,
					default=view.default,
					codec=view.codec,
					param=name,
				)
				if serialized != slot.raw.value:
					self._set_raw(name, slot, serialized)

		current_params = dict(self._applied_params)
		query_params = dict(current_params)
		for name, slot in self._slots.items():
			raw = slot.raw.value
			if raw is None:
				query_params.pop(name, None)
			else:
				query_params[name] = raw

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
		self._commanded_params = query_params
