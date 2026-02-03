from __future__ import annotations

import asyncio
import inspect
import re
import uuid
from collections.abc import Callable
from typing import Any, Generic, Literal, TypeVar, cast, overload, override

from pulse.channel import Channel
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.helpers import Disposable, call_flexible
from pulse.hooks.core import HOOK_CONTEXT, HookMetadata, HookState, hooks
from pulse.hooks.state import collect_component_identity
from pulse.scheduling import create_future, create_task

T = TypeVar("T")
Number = int | float

_ATTR_ALIASES: dict[str, str] = {
	"className": "class",
	"htmlFor": "for",
	"tabIndex": "tabindex",
}

_ATTR_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_:\-\.]*$")

_GETTABLE_PROPS: set[str] = {
	"value",
	"checked",
	"disabled",
	"readOnly",
	"selectedIndex",
	"selectionStart",
	"selectionEnd",
	"selectionDirection",
	"scrollTop",
	"scrollLeft",
	"scrollHeight",
	"scrollWidth",
	"clientWidth",
	"clientHeight",
	"offsetWidth",
	"offsetHeight",
	"innerText",
	"textContent",
	"className",
	"id",
	"name",
	"type",
	"tabIndex",
}

_SETTABLE_PROPS: set[str] = {
	"value",
	"checked",
	"disabled",
	"readOnly",
	"selectedIndex",
	"selectionStart",
	"selectionEnd",
	"selectionDirection",
	"scrollTop",
	"scrollLeft",
	"className",
	"id",
	"name",
	"type",
	"tabIndex",
}


def _normalize_attr_name(name: str) -> str:
	return _ATTR_ALIASES.get(name, name)


def _validate_attr_name(name: str) -> str:
	if not isinstance(name, str):
		raise TypeError("ref attribute name must be a string")
	trimmed = name.strip()
	if not trimmed:
		raise ValueError("ref attribute name must be non-empty")
	normalized = _normalize_attr_name(trimmed)
	if not _ATTR_NAME_PATTERN.match(normalized):
		raise ValueError(f"Invalid attribute name: {normalized}")
	if normalized.lower().startswith("on"):
		raise ValueError("ref attribute name cannot start with 'on'")
	return normalized


def _validate_prop_name(name: str, *, settable: bool) -> str:
	if not isinstance(name, str):
		raise TypeError("ref property name must be a string")
	trimmed = name.strip()
	if not trimmed:
		raise ValueError("ref property name must be non-empty")
	if trimmed not in _GETTABLE_PROPS:
		raise ValueError(f"Unsupported ref property: {trimmed}")
	if settable and trimmed not in _SETTABLE_PROPS:
		raise ValueError(f"Ref property is read-only: {trimmed}")
	return trimmed


class RefNotMounted(RuntimeError):
	"""Raised when a ref operation is attempted before mount."""


class RefTimeout(asyncio.TimeoutError):
	"""Raised when waiting for a ref mount times out."""


class Ref(Disposable, Generic[T]):
	"""Server-side handle for a client DOM ref."""

	__slots__: tuple[str, ...] = (
		"_channel",
		"_render",
		"_route_ctx",
		"id",
		"_mounted",
		"_mount_waiters",
		"_mount_handlers",
		"_unmount_handlers",
		"callback",
		"_remove_mount",
		"_remove_unmount",
		"_remove_close",
	)

	id: str
	callback: Callable[[Ref[Any] | None], Any] | None
	_channel: Channel | None
	_render: Any | None
	_route_ctx: Any | None
	_mounted: bool
	_mount_waiters: list[asyncio.Future[None]]
	_mount_handlers: list[Callable[[], Any]]
	_unmount_handlers: list[Callable[[], Any]]
	_remove_mount: Callable[[], None] | None
	_remove_unmount: Callable[[], None] | None
	_remove_close: Callable[[], None] | None

	def __init__(self, *, ref_id: str | None = None) -> None:
		self._channel = None
		self._render = None
		self._route_ctx = None
		self.id = ref_id or uuid.uuid4().hex
		self.callback = None
		self._mounted = False
		self._mount_waiters = []
		self._mount_handlers = []
		self._unmount_handlers = []
		self._remove_mount = None
		self._remove_unmount = None
		self._remove_close = None

	@property
	def channel_id(self) -> str:
		if self._channel is None:
			raise RuntimeError("Ref is not attached to a channel")
		return self._channel.id

	@property
	def mounted(self) -> bool:
		return self._mounted

	def on_mount(self, handler: Callable[[], Any]) -> Callable[[], None]:
		self._mount_handlers.append(handler)

		def _remove() -> None:
			try:
				self._mount_handlers.remove(handler)
			except ValueError:
				return

		return _remove

	def on_unmount(self, handler: Callable[[], Any]) -> Callable[[], None]:
		self._unmount_handlers.append(handler)

		def _remove() -> None:
			try:
				self._unmount_handlers.remove(handler)
			except ValueError:
				return

		return _remove

	def bind_callback(self, handler: Callable[[Ref[Any] | None], Any]) -> None:
		self.callback = handler

	def attach(self, channel: Channel, *, render: Any, route_ctx: Any | None) -> None:
		if self._channel is not None:
			if self._channel is channel:
				self._render = render
				self._route_ctx = route_ctx
				return
			raise RuntimeError("Ref is already attached to a different channel")
		self._channel = channel
		self._render = render
		self._route_ctx = route_ctx
		self._remove_mount = channel.on("ref:mounted", self._on_mounted)
		self._remove_unmount = channel.on("ref:unmounted", self._on_unmounted)
		self._remove_close = channel.on_close(lambda _reason=None: self.detach())

	def detach(self, *, reason: str | None = None) -> None:
		_ = reason
		if self._channel is None:
			return
		if self._mounted:
			self._mounted = False
			self._run_handlers(self._unmount_handlers, label="unmount")
			self._run_ref_callback(None, label="ref_callback_unmount")
		for fut in list(self._mount_waiters):
			if not fut.done():
				fut.set_exception(RefNotMounted("Ref detached"))
		self._mount_waiters.clear()
		if self._remove_mount is not None:
			self._remove_mount()
			self._remove_mount = None
		if self._remove_unmount is not None:
			self._remove_unmount()
			self._remove_unmount = None
		if self._remove_close is not None:
			self._remove_close()
			self._remove_close = None
		self.callback = None
		self._channel = None
		self._render = None
		self._route_ctx = None

	async def wait_mounted(self, timeout: float | None = None) -> None:
		if self._mounted:
			return
		fut = create_future()
		self._mount_waiters.append(fut)
		try:
			if timeout is None:
				await fut
			else:
				await asyncio.wait_for(fut, timeout=timeout)
		except asyncio.TimeoutError as exc:
			raise RefTimeout("Timed out waiting for ref to mount") from exc
		finally:
			if fut in self._mount_waiters:
				self._mount_waiters.remove(fut)

	def focus(self, *, prevent_scroll: bool | None = None) -> None:
		payload = None
		if prevent_scroll is not None:
			if not isinstance(prevent_scroll, bool):
				raise TypeError("focus() prevent_scroll must be a bool")
			payload = {"preventScroll": prevent_scroll}
		self._emit("focus", payload)

	def blur(self) -> None:
		self._emit("blur")

	def click(self) -> None:
		self._emit("click")

	def submit(self) -> None:
		self._emit("submit")

	def reset(self) -> None:
		self._emit("reset")

	def scroll_into_view(
		self,
		*,
		behavior: str | None = None,
		block: str | None = None,
		inline: str | None = None,
	) -> None:
		payload = {
			k: v
			for k, v in {
				"behavior": behavior,
				"block": block,
				"inline": inline,
			}.items()
			if v is not None
		}
		self._emit("scrollIntoView", payload if payload else None)

	def scroll_to(
		self,
		*,
		top: float | int | None = None,
		left: float | int | None = None,
		behavior: str | None = None,
	) -> None:
		if top is not None and not isinstance(top, (int, float)):
			raise TypeError("scroll_to() top must be a number")
		if left is not None and not isinstance(left, (int, float)):
			raise TypeError("scroll_to() left must be a number")
		if behavior is not None and not isinstance(behavior, str):
			raise TypeError("scroll_to() behavior must be a string")
		payload = {
			k: v
			for k, v in {
				"top": top,
				"left": left,
				"behavior": behavior,
			}.items()
			if v is not None
		}
		self._emit("scrollTo", payload if payload else None)

	def scroll_by(
		self,
		*,
		top: float | int | None = None,
		left: float | int | None = None,
		behavior: str | None = None,
	) -> None:
		if top is not None and not isinstance(top, (int, float)):
			raise TypeError("scroll_by() top must be a number")
		if left is not None and not isinstance(left, (int, float)):
			raise TypeError("scroll_by() left must be a number")
		if behavior is not None and not isinstance(behavior, str):
			raise TypeError("scroll_by() behavior must be a string")
		payload = {
			k: v
			for k, v in {
				"top": top,
				"left": left,
				"behavior": behavior,
			}.items()
			if v is not None
		}
		self._emit("scrollBy", payload if payload else None)

	async def measure(self, *, timeout: float | None = None) -> dict[str, Any] | None:
		result = await self._request("measure", timeout=timeout)
		if result is None:
			return None
		if isinstance(result, dict):
			return result
		raise TypeError("measure() expected dict result")

	async def get_value(self, *, timeout: float | None = None) -> Any:
		return await self._request("getValue", timeout=timeout)

	async def set_value(self, value: Any, *, timeout: float | None = None) -> Any:
		return await self._request("setValue", {"value": value}, timeout=timeout)

	async def get_text(self, *, timeout: float | None = None) -> str | None:
		result = await self._request("getText", timeout=timeout)
		if result is None:
			return None
		if isinstance(result, str):
			return result
		raise TypeError("get_text() expected string result")

	async def set_text(self, text: str, *, timeout: float | None = None) -> str | None:
		result = await self._request("setText", {"text": text}, timeout=timeout)
		if result is None:
			return None
		if isinstance(result, str):
			return result
		raise TypeError("set_text() expected string result")

	def select(self) -> None:
		self._emit("select")

	def set_selection_range(
		self, start: int, end: int, *, direction: str | None = None
	) -> None:
		if not isinstance(start, int) or not isinstance(end, int):
			raise TypeError("set_selection_range() requires integer start/end")
		if direction is not None and not isinstance(direction, str):
			raise TypeError("set_selection_range() direction must be a string")
		payload: dict[str, Any] = {"start": start, "end": end}
		if direction is not None:
			payload["direction"] = direction
		self._emit("setSelectionRange", payload)

	@overload
	async def get_attr(
		self,
		name: Literal[
			"className",
			"class",
			"id",
			"name",
			"type",
			"title",
			"placeholder",
			"role",
			"href",
			"src",
			"alt",
			"htmlFor",
			"for",
			"tabIndex",
			"tabindex",
			"aria-label",
			"aria-hidden",
			"data-test",
			"value",
		],
		*,
		timeout: float | None = None,
	) -> str | None: ...

	@overload
	async def get_attr(
		self, name: str, *, timeout: float | None = None
	) -> str | None: ...

	async def get_attr(self, name: str, *, timeout: float | None = None) -> str | None:
		normalized = _validate_attr_name(name)
		result = await self._request("getAttr", {"name": normalized}, timeout=timeout)
		if result is None:
			return None
		if isinstance(result, str):
			return result
		raise TypeError("get_attr() expected string result")

	@overload
	async def set_attr(
		self,
		name: Literal[
			"className",
			"class",
			"id",
			"name",
			"type",
			"title",
			"placeholder",
			"role",
			"href",
			"src",
			"alt",
			"htmlFor",
			"for",
			"tabIndex",
			"tabindex",
			"aria-label",
			"aria-hidden",
			"data-test",
			"value",
		],
		value: str | int | float | bool | None,
		*,
		timeout: float | None = None,
	) -> str | None: ...

	@overload
	async def set_attr(
		self,
		name: str,
		value: Any,
		*,
		timeout: float | None = None,
	) -> str | None: ...

	async def set_attr(
		self, name: str, value: Any, *, timeout: float | None = None
	) -> str | None:
		normalized = _validate_attr_name(name)
		result = await self._request(
			"setAttr", {"name": normalized, "value": value}, timeout=timeout
		)
		if result is None:
			return None
		if isinstance(result, str):
			return result
		raise TypeError("set_attr() expected string result")

	async def remove_attr(self, name: str, *, timeout: float | None = None) -> None:
		normalized = _validate_attr_name(name)
		await self._request("removeAttr", {"name": normalized}, timeout=timeout)

	@overload
	async def get_prop(
		self, name: Literal["value"], *, timeout: float | None = None
	) -> str: ...

	@overload
	async def get_prop(
		self, name: Literal["checked"], *, timeout: float | None = None
	) -> bool: ...

	@overload
	async def get_prop(
		self, name: Literal["disabled"], *, timeout: float | None = None
	) -> bool: ...

	@overload
	async def get_prop(
		self, name: Literal["readOnly"], *, timeout: float | None = None
	) -> bool: ...

	@overload
	async def get_prop(
		self, name: Literal["selectedIndex"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["selectionStart"], *, timeout: float | None = None
	) -> Number | None: ...

	@overload
	async def get_prop(
		self, name: Literal["selectionEnd"], *, timeout: float | None = None
	) -> Number | None: ...

	@overload
	async def get_prop(
		self, name: Literal["selectionDirection"], *, timeout: float | None = None
	) -> str | None: ...

	@overload
	async def get_prop(
		self, name: Literal["scrollTop"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["scrollLeft"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["scrollHeight"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["scrollWidth"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["clientWidth"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["clientHeight"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["offsetWidth"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["offsetHeight"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(
		self, name: Literal["innerText"], *, timeout: float | None = None
	) -> str: ...

	@overload
	async def get_prop(
		self, name: Literal["textContent"], *, timeout: float | None = None
	) -> str | None: ...

	@overload
	async def get_prop(
		self, name: Literal["className"], *, timeout: float | None = None
	) -> str: ...

	@overload
	async def get_prop(
		self, name: Literal["id"], *, timeout: float | None = None
	) -> str: ...

	@overload
	async def get_prop(
		self, name: Literal["name"], *, timeout: float | None = None
	) -> str: ...

	@overload
	async def get_prop(
		self, name: Literal["type"], *, timeout: float | None = None
	) -> str: ...

	@overload
	async def get_prop(
		self, name: Literal["tabIndex"], *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def get_prop(self, name: str, *, timeout: float | None = None) -> Any: ...

	async def get_prop(self, name: str, *, timeout: float | None = None) -> Any:
		prop = _validate_prop_name(name, settable=False)
		return await self._request("getProp", {"name": prop}, timeout=timeout)

	@overload
	async def set_prop(
		self, name: Literal["value"], value: str, *, timeout: float | None = None
	) -> str: ...

	@overload
	async def set_prop(
		self, name: Literal["checked"], value: bool, *, timeout: float | None = None
	) -> bool: ...

	@overload
	async def set_prop(
		self, name: Literal["disabled"], value: bool, *, timeout: float | None = None
	) -> bool: ...

	@overload
	async def set_prop(
		self, name: Literal["readOnly"], value: bool, *, timeout: float | None = None
	) -> bool: ...

	@overload
	async def set_prop(
		self,
		name: Literal["selectedIndex"],
		value: Number,
		*,
		timeout: float | None = None,
	) -> Number: ...

	@overload
	async def set_prop(
		self,
		name: Literal["selectionStart"],
		value: Number | None,
		*,
		timeout: float | None = None,
	) -> Number | None: ...

	@overload
	async def set_prop(
		self,
		name: Literal["selectionEnd"],
		value: Number | None,
		*,
		timeout: float | None = None,
	) -> Number | None: ...

	@overload
	async def set_prop(
		self,
		name: Literal["selectionDirection"],
		value: str | None,
		*,
		timeout: float | None = None,
	) -> str | None: ...

	@overload
	async def set_prop(
		self, name: Literal["scrollTop"], value: Number, *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def set_prop(
		self,
		name: Literal["scrollLeft"],
		value: Number,
		*,
		timeout: float | None = None,
	) -> Number: ...

	@overload
	async def set_prop(
		self, name: Literal["className"], value: str, *, timeout: float | None = None
	) -> str: ...

	@overload
	async def set_prop(
		self, name: Literal["id"], value: str, *, timeout: float | None = None
	) -> str: ...

	@overload
	async def set_prop(
		self, name: Literal["name"], value: str, *, timeout: float | None = None
	) -> str: ...

	@overload
	async def set_prop(
		self, name: Literal["type"], value: str, *, timeout: float | None = None
	) -> str: ...

	@overload
	async def set_prop(
		self, name: Literal["tabIndex"], value: Number, *, timeout: float | None = None
	) -> Number: ...

	@overload
	async def set_prop(
		self, name: str, value: Any, *, timeout: float | None = None
	) -> Any: ...

	async def set_prop(
		self, name: str, value: Any, *, timeout: float | None = None
	) -> Any:
		prop = _validate_prop_name(name, settable=True)
		return await self._request(
			"setProp", {"name": prop, "value": value}, timeout=timeout
		)

	async def set_style(
		self, styles: dict[str, Any], *, timeout: float | None = None
	) -> None:
		if not isinstance(styles, dict):
			raise TypeError("set_style() requires a dict")
		for key, value in styles.items():
			if not isinstance(key, str) or not key:
				raise ValueError("set_style() keys must be non-empty strings")
			if isinstance(value, bool):
				raise TypeError("set_style() values must be string, number, or None")
			if value is not None and not isinstance(value, (str, int, float)):
				raise TypeError("set_style() values must be string, number, or None")
		await self._request("setStyle", {"styles": styles}, timeout=timeout)

	def _emit(self, op: str, payload: Any = None) -> None:
		self._ensure_mounted()
		channel = self._channel
		if channel is None:
			raise RefNotMounted("Ref is not attached")
		channel.emit(
			"ref:call",
			{"refId": self.id, "op": op, "payload": payload},
		)

	async def _request(
		self,
		op: str,
		payload: Any = None,
		*,
		timeout: float | None = None,
	) -> Any:
		self._ensure_mounted()
		channel = self._channel
		if channel is None:
			raise RefNotMounted("Ref is not attached")
		return await channel.request(
			"ref:request",
			{"refId": self.id, "op": op, "payload": payload},
			timeout=timeout,
		)

	def _ensure_mounted(self) -> None:
		if self._channel is None:
			raise RefNotMounted("Ref is not attached")
		if not self._mounted:
			raise RefNotMounted("Ref is not mounted")

	def _on_mounted(self, payload: Any) -> None:
		if self._channel is None:
			return
		if isinstance(payload, dict):
			ref_id = cast(dict[str, Any], payload).get("refId")
			if ref_id is not None and str(ref_id) != self.id:
				return
		self._mounted = True
		for fut in list(self._mount_waiters):
			if not fut.done():
				fut.set_result(None)
		self._mount_waiters.clear()
		self._run_handlers(self._mount_handlers, label="mount")
		self._run_ref_callback(self, label="ref_callback_mount")

	def _on_unmounted(self, payload: Any) -> None:
		if self._channel is None:
			return
		if isinstance(payload, dict):
			ref_id = cast(dict[str, Any], payload).get("refId")
			if ref_id is not None and str(ref_id) != self.id:
				return
		self.detach()

	def _run_ref_callback(self, value: Ref[Any] | None, *, label: str) -> None:
		if self.callback is None:
			return
		self._run_handler(self.callback, label=label, args=(value,))

	def _run_handler(
		self,
		handler: Callable[..., Any],
		*,
		label: str,
		args: tuple[Any, ...],
	) -> None:
		def _invoke() -> None:
			try:
				result = call_flexible(handler, *args)
			except Exception:
				# Fail early: propagate on next render via error log if desired
				raise
			if inspect.isawaitable(result):
				task = create_task(result, name=f"ref:{self.id}:{label}")

				def _on_done(done_task: asyncio.Future[Any]) -> None:
					if done_task.cancelled():
						return
					try:
						done_task.result()
					except asyncio.CancelledError:
						return
					except Exception as exc:
						loop = done_task.get_loop()
						loop.call_exception_handler(
							{
								"message": f"Unhandled exception in ref {label} handler",
								"exception": exc,
								"context": {"ref_id": self.id, "handler": label},
							}
						)

				task.add_done_callback(_on_done)

		ctx = PULSE_CONTEXT.get()
		if ctx is not None and self._render is not None:
			with PulseContext(
				app=ctx.app,
				session=ctx.session,
				render=self._render,
				route=self._route_ctx,
			):
				_invoke()
			return
		_invoke()

	def _run_handlers(self, handlers: list[Callable[[], Any]], *, label: str) -> None:
		for handler in list(handlers):
			self._run_handler(handler, label=label, args=())

	@override
	def dispose(self) -> None:
		self.detach(reason="dispose")
		for fut in list(self._mount_waiters):
			if not fut.done():
				fut.set_exception(RefNotMounted("Ref disposed"))
		self._mount_waiters.clear()
		self._mount_handlers.clear()
		self._unmount_handlers.clear()
		self.callback = None

	@override
	def __repr__(self) -> str:
		if self._channel is None:
			return f"Ref(id={self.id}, attached=False)"
		return f"Ref(id={self.id}, channel={self._channel.id})"


class RefHookState(HookState):
	__slots__: tuple[str, ...] = (
		"instances",
		"called_keys",
	)
	instances: dict[tuple[str, Any], Ref[Any]]
	called_keys: set[tuple[str, Any]]

	def __init__(self) -> None:
		super().__init__()
		self.instances = {}
		self.called_keys = set()

	def _make_key(self, identity: Any, key: str | None) -> tuple[str, Any]:
		if key is None:
			return ("code", identity)
		return ("key", key)

	@override
	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		self.called_keys.clear()

	def get_or_create(self, identity: Any, key: str | None) -> tuple[Ref[Any], bool]:
		full_identity = self._make_key(identity, key)
		if full_identity in self.called_keys:
			if key is None:
				raise RuntimeError(
					"`pulse.ref` can only be called once per component render at the same location. "
					+ "Use the `key` parameter to disambiguate: ps.ref(key=unique_value)"
				)
			raise RuntimeError(
				f"`pulse.ref` can only be called once per component render with key='{key}'"
			)
		self.called_keys.add(full_identity)

		existing = self.instances.get(full_identity)
		if existing is not None:
			if existing.__disposed__:
				key_label = f"key='{key}'" if key is not None else "callsite"
				raise RuntimeError(
					"`pulse.ref` found a disposed cached Ref for "
					+ key_label
					+ ". Do not dispose handles returned by `pulse.ref`."
				)
			return existing, False

		handle = Ref()
		self.instances[full_identity] = handle
		return handle, True

	@override
	def dispose(self) -> None:
		for handle in self.instances.values():
			try:
				handle.dispose()
			except Exception:
				pass
		self.instances.clear()


ref_hook_state = hooks.create(
	"pulse:core.ref",
	factory=RefHookState,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.ref handles",
	),
)


def ref(
	*,
	key: str | None = None,
	on_mount: Callable[[], Any] | None = None,
	on_unmount: Callable[[], Any] | None = None,
) -> Ref[Any]:
	"""Create or retrieve a stable ref handle for a component.

	Args:
		key: Optional key to disambiguate multiple refs created at the same callsite.
		on_mount: Optional handler called when the ref mounts.
		on_unmount: Optional handler called when the ref unmounts.
	"""
	if key is not None and not isinstance(key, str):
		raise TypeError("ref() key must be a string")
	if key == "":
		raise ValueError("ref() requires a non-empty string key")
	if on_mount is not None and not callable(on_mount):
		raise TypeError("ref() on_mount must be callable")
	if on_unmount is not None and not callable(on_unmount):
		raise TypeError("ref() on_unmount must be callable")

	if HOOK_CONTEXT.get() is None:
		handle = Ref()
		if on_mount is not None:
			handle.on_mount(on_mount)
		if on_unmount is not None:
			handle.on_unmount(on_unmount)
		return handle

	identity: Any
	if key is None:
		frame = inspect.currentframe()
		assert frame is not None
		caller = frame.f_back
		assert caller is not None
		identity = collect_component_identity(caller)
	else:
		identity = key

	hook_state = ref_hook_state()
	handle, created = hook_state.get_or_create(identity, key)
	if created:
		if on_mount is not None:
			handle.on_mount(on_mount)
		if on_unmount is not None:
			handle.on_unmount(on_unmount)
	return handle


__all__ = ["Ref", "RefNotMounted", "RefTimeout", "ref"]
