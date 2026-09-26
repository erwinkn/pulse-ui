"""The URL currently displayed by a render session's browser tab."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, override
from urllib.parse import urlencode

from pulse.helpers import values_equal
from pulse.messages import ServerNavigateToMessage
from pulse.reactive import Effect, Scope, Signal
from pulse.reactive_extensions import reactive, unwrap
from pulse.resources import (
	Resource,
	ResourceOwner,
	ResourceScope,
	suspend_resource_scope,
)
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
	holders: "dict[ResourceScope, _ViewHandle]" = field(default_factory=dict)


@dataclass
class _QueryParamSlot:
	raw: Signal[str | None]
	views: list[_TypedView]


class _ViewHandle(Resource):
	"""One scope's claim on a typed view of a query parameter.

	A view is shared by every declaration with the same codec and default, so
	it is refcounted: when the last holder is disposed the view is dropped.
	The raw slot and the URL are untouched, they belong to the session.
	"""

	_url: "SessionUrl"
	_name: str
	_view: _TypedView
	_scope: ResourceScope

	def __init__(
		self,
		url: "SessionUrl",
		name: str,
		view: _TypedView,
		scope: ResourceScope,
	) -> None:
		self._url = url
		self._name = name
		self._view = view
		self._scope = scope

	@override
	def dispose(self) -> None:
		self._url.release_view(self._name, self._view, self._scope)


class SessionUrl(ResourceOwner):
	"""The URL currently displayed by the session's browser tab.

	A render session is one browser tab, so it has exactly one URL. Every
	mount reports the same pathname/hash/query params (they all derive from
	the client's single ``location``); only ``pathParams``/``catchall`` are
	mount-specific, and those live on `RouteContext`.

	Typed ``QueryParam`` fields share one raw slot per name via ``param()``.
	Each declaration gets a typed view of that raw value, so declarations
	with different codecs or defaults can coexist.

	The raw value is the source of truth and the views are derived from it: a
	view only pushes to the URL when its value differs from what the current
	raw value decodes to. Loading a URL therefore never rewrites it, even when
	a value equals one view's default.

	A parameter name has exactly one raw URL value. Writing a value that
	serializes as absent (for example, one view's default) resets every other
	view of that name to its own default. A declaration registered while a
	write is unflushed seeds from the current raw value and converges on the
	next sync flush.

	Slot writes are immediate and session-owned. If a State constructor raises
	after writing a query parameter, its write is intentionally retained for
	other states sharing the session slot.

	Raw slots live as long as the session, because the URL string is the source
	of truth and survives navigation. Typed views do not: each is refcounted by
	the `ResourceScope`s that asked for it and is dropped when the last of them
	is disposed, so a dead declaration can no longer fail to decode a later URL
	change on behalf of live ones. Dropping a view leaves the slot and the URL
	untouched.
	"""

	pathname: str
	hash: str
	query_params: dict[str, str]
	_send: Callable[[ServerNavigateToMessage], Any]
	_slots: dict[str, _QueryParamSlot]
	_sync_effect: Effect | None
	_applied_params: dict[str, str]
	_pending: list[dict[str, str]]
	_closed: bool
	_route_revision: Signal[int]
	_resource_scope: ResourceScope | None

	def __init__(self, send: Callable[[ServerNavigateToMessage], Any]) -> None:
		self._resource_scope = ResourceScope(label="SessionUrl")
		self.pathname = ""
		self.hash = ""
		self.query_params = {}
		self._send = send
		self._slots = {}
		self._sync_effect = None
		self._applied_params = {}
		self._pending = []
		self._closed = False
		self._route_revision = Signal(0, name="SessionUrl:route_revision")

	def apply(self, info: RouteInfo) -> None:
		"""Record the URL the client is currently displaying.

		Called by every `RouteContext` on creation and on route updates. All
		mounts report the same URL, so this is last-writer-wins by design.
		"""
		if self._closed:
			return
		incoming_params = dict(info["queryParams"])
		incoming_owned = {name: incoming_params.get(name) for name in self._slots}
		pending_index = next(
			(
				index
				for index, entry in enumerate(self._pending)
				if incoming_owned == {name: entry.get(name) for name in self._slots}
			),
			None,
		)
		if pending_index is None:
			pending = []
			updates = [
				(name, slot, incoming_params.get(name))
				for name, slot in self._slots.items()
				if incoming_params.get(name) != self._applied_params.get(name)
			]
		else:
			pending = self._pending[pending_index + 1 :]
			updates = []

		self.pathname = info["pathname"]
		self.hash = info["hash"]
		self._applied_params = incoming_params
		self.query_params = incoming_params
		self._pending = pending
		self._route_revision.write(self._route_revision.value + 1)
		first_error: Exception | None = None
		for name, slot, raw in updates:
			errors = self._set_raw(name, slot, raw)
			if first_error is None and errors:
				first_error = errors[0]
		if self._sync_effect is not None:
			self._sync_effect.schedule()
		if first_error is not None:
			raise first_error from None

	def param(
		self,
		name: str,
		codec: QueryParamCodec,
		default: Any,
		*,
		owner: ResourceScope | None = None,
	) -> Signal[Any]:
		"""Return the signal of the typed view for ``name``, creating it if needed.

		``owner`` is the scope of the declaration asking for the view; it becomes
		one of the view's holders, and the view is dropped when every holder has
		been disposed.
		"""
		if self._closed:
			raise RuntimeError("SessionUrl is closed")
		if not name:
			raise RuntimeError("QueryParam param name was not resolved")
		slot = self._slots.get(name)
		if slot is None:
			slot = _QueryParamSlot(
				raw=Signal(self.query_params.get(name), name=f"QueryParam.raw.{name}"),
				views=[],
			)
			self._slots[name] = slot
			self._ensure_sync()
		view = next(
			(
				candidate
				for candidate in slot.views
				if candidate.codec == codec and values_equal(candidate.default, default)
			),
			None,
		)
		if view is None:
			value = self._parse(slot.raw.value, codec=codec, default=default, name=name)
			view = _TypedView(
				codec=codec,
				default=default,
				signal=Signal(
					reactive(value),  # pyright: ignore[reportUnknownArgumentType]
					name=f"QueryParam.{name}",
				),
			)
			slot.views.append(view)
		if owner is not None and owner not in view.holders:
			handle = _ViewHandle(self, name, view, owner)
			view.holders[owner] = handle
			owner.own(handle)
		return view.signal

	def release_view(self, name: str, view: _TypedView, scope: ResourceScope) -> None:
		"""Drop one scope's claim on a typed view, and the view if it was the last.

		A write the view has not pushed yet lands in the raw slot on the way out:
		writes belong to the session, like the slot itself. Beyond that the slot
		and the URL are left alone, dropping a view never rewrites them.
		"""
		view.holders.pop(scope, None)
		if view.holders:
			return
		slot = self._slots.get(name)
		if slot is None:
			return
		self._push_view(name, slot, view)
		slot.views = [candidate for candidate in slot.views if candidate is not view]
		self.prime()

	def prime(self) -> None:
		if self._sync_effect is not None and not self._closed:
			self._sync_effect.schedule()

	@override
	def on_dispose(self) -> None:
		self._closed = True
		self._sync_effect = None
		self._slots.clear()

	def _ensure_sync(self) -> None:
		if self._sync_effect is not None:
			return
		# The sync effect belongs to the session, not to whichever scope
		# happened to declare the first query parameter.
		with suspend_resource_scope(), Scope():
			self._sync_effect = Effect(
				self._sync_to_route,
				name="SessionUrl:query_param",
				lazy=True,
			)
		self.resources.own(self._sync_effect)

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

	def _set_raw(
		self, name: str, slot: _QueryParamSlot, raw: str | None
	) -> list[Exception]:
		slot.raw.write(raw)
		errors: list[Exception] = []
		for view in slot.views:
			try:
				parsed = self._parse(
					raw,
					codec=view.codec,
					default=view.default,
					name=name,
				)
			except Exception as error:
				errors.append(error)
				continue
			if values_equal(view.signal.value, parsed):
				continue
			view.signal.write(reactive(parsed))
		return errors

	def _push_view(
		self, name: str, slot: _QueryParamSlot, view: _TypedView
	) -> Exception | None:
		"""Write a view's value into the raw slot when it diverges from it."""
		value = view.signal.read()
		if view.codec.kind == "list" and value is not None:
			# Read through the reactive list so an in-place mutation re-runs
			# the sync effect.
			value = unwrap(value)
		raw = slot.raw.value
		try:
			decoded = self._parse(
				raw, codec=view.codec, default=view.default, name=name
			)
		except Exception:
			# The raw value does not decode for this view. The URL is the
			# source of truth, so it stays; `apply` reports the error.
			return None
		if values_equal(value, decoded):
			# The view still holds what `raw` decodes to, so nobody wrote it and
			# it has nothing to push. Serializing anyway would rewrite the URL on
			# load whenever a value happens to equal this view's default, and
			# reset sibling views declaring another default for the same name.
			return None
		serialized = serialize_query_param_value(
			value,
			default=view.default,
			codec=view.codec,
			param=name,
		)
		if serialized == raw:
			return None
		errors = self._set_raw(name, slot, serialized)
		return errors[0] if errors else None

	def _sync_to_route(self) -> None:
		self._route_revision.read()
		if not self.pathname:
			return
		first_error: Exception | None = None
		for name, slot in self._slots.items():
			for view in slot.views:
				error = self._push_view(name, slot, view)
				if first_error is None:
					first_error = error

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
		self._pending.append(query_params)
		if first_error is not None:
			raise first_error from None
