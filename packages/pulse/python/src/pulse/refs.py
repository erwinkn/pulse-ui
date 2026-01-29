from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Callable
from typing import Any, Generic, TypeVar, cast, override

from pulse.channel import Channel, channel
from pulse.helpers import Disposable
from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.hooks.state import collect_component_identity
from pulse.scheduling import create_future

T = TypeVar("T")


class RefNotMounted(RuntimeError):
	"""Raised when a ref operation is attempted before mount."""


class RefTimeout(asyncio.TimeoutError):
	"""Raised when waiting for a ref mount times out."""


class RefHandle(Disposable, Generic[T]):
	"""Server-side handle for a client DOM ref."""

	__slots__: tuple[str, ...] = (
		"_channel",
		"id",
		"_mounted",
		"_mount_waiters",
		"_mount_handlers",
		"_unmount_handlers",
	)

	_channel: Channel
	id: str
	_mounted: bool
	_mount_waiters: list[asyncio.Future[None]]
	_mount_handlers: list[Callable[[], Any]]
	_unmount_handlers: list[Callable[[], Any]]

	def __init__(self, channel: Channel, *, ref_id: str | None = None) -> None:
		self._channel = channel
		self.id = ref_id or uuid.uuid4().hex
		self._mounted = False
		self._mount_waiters = []
		self._mount_handlers = []
		self._unmount_handlers = []
		self._channel.on("ref:mounted", self._on_mounted)
		self._channel.on("ref:unmounted", self._on_unmounted)

	@property
	def channel_id(self) -> str:
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

	def focus(self) -> None:
		self._emit("focus")

	def blur(self) -> None:
		self._emit("blur")

	def click(self) -> None:
		self._emit("click")

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

	def _emit(self, op: str, payload: Any = None) -> None:
		self._ensure_mounted()
		self._channel.emit(
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
		return await self._channel.request(
			"ref:request",
			{"refId": self.id, "op": op, "payload": payload},
			timeout=timeout,
		)

	def _ensure_mounted(self) -> None:
		if not self._mounted:
			raise RefNotMounted("Ref is not mounted")

	def _on_mounted(self, payload: Any) -> None:
		if isinstance(payload, dict):
			ref_id = cast(dict[str, Any], payload).get("refId")
			if ref_id is not None and str(ref_id) != self.id:
				return
		self._mounted = True
		for fut in list(self._mount_waiters):
			if not fut.done():
				fut.set_result(None)
		self._mount_waiters.clear()
		for handler in list(self._mount_handlers):
			try:
				handler()
			except Exception:
				# Fail early: propagate on next render via error log if desired
				raise

	def _on_unmounted(self, payload: Any) -> None:
		if isinstance(payload, dict):
			ref_id = cast(dict[str, Any], payload).get("refId")
			if ref_id is not None and str(ref_id) != self.id:
				return
		self._mounted = False
		for handler in list(self._unmount_handlers):
			try:
				handler()
			except Exception:
				raise

	@override
	def dispose(self) -> None:
		self._mounted = False
		for fut in list(self._mount_waiters):
			if not fut.done():
				fut.set_exception(RefNotMounted("Ref disposed"))
		self._mount_waiters.clear()
		self._mount_handlers.clear()
		self._unmount_handlers.clear()
		self._channel.close()

	@override
	def __repr__(self) -> str:
		return f"RefHandle(id={self.id}, channel={self.channel_id})"


class RefHookState(HookState):
	__slots__ = ("instances", "called_keys")  # pyright: ignore[reportUnannotatedClassAttribute]
	instances: dict[tuple[str, Any], RefHandle[Any]]
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

	def get_or_create(self, identity: Any, key: str | None) -> RefHandle[Any]:
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
			return existing

		handle = RefHandle(channel())
		self.instances[full_identity] = handle
		return handle

	@override
	def dispose(self) -> None:
		for handle in self.instances.values():
			try:
				handle.dispose()
			except Exception:
				pass
		self.instances.clear()


def _ref_factory():
	return RefHookState()


_ref_hook = hooks.create(
	"pulse:core.ref",
	_ref_factory,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.ref handles",
	),
)


def ref(*, key: str | None = None) -> RefHandle[Any]:
	"""Create or retrieve a stable ref handle for a component.

	Args:
		key: Optional key to disambiguate multiple refs created at the same callsite.
	"""
	if key is not None and not isinstance(key, str):
		raise TypeError("ref() key must be a string")
	if key == "":
		raise ValueError("ref() requires a non-empty string key")

	identity: Any
	if key is None:
		frame = inspect.currentframe()
		assert frame is not None
		caller = frame.f_back
		assert caller is not None
		identity = collect_component_identity(caller)
	else:
		identity = key

	hook_state = _ref_hook()
	return hook_state.get_or_create(identity, key)


__all__ = ["RefHandle", "RefNotMounted", "RefTimeout", "ref"]
