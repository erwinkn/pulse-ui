from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
import pytest
from pulse.channel import Channel
from pulse.refs import Ref, RefNotMounted, RefsManager


class DummyChannel:
	id: str = "chan-test"
	responses: list[Any]

	def __init__(self, responses: list[Any] | None = None) -> None:
		self.emitted: list[tuple[str, Any]] = []
		self.requested: list[tuple[str, Any, float | None]] = []
		self.close_handlers: list[Any] = []
		self.responses = list(responses or [])

	def on(self, event: str, handler: Any):
		def _remove() -> None:
			return None

		return _remove

	def on_close(self, handler: Any):
		self.close_handlers.append(handler)

		def _remove() -> None:
			try:
				self.close_handlers.remove(handler)
			except ValueError:
				return None

		return _remove

	def emit(self, event: str, payload: Any = None) -> None:
		self.emitted.append((event, payload))

	async def request(
		self, event: str, payload: Any = None, *, timeout: float | None = None
	) -> Any:
		self.requested.append((event, payload, timeout))
		if self.responses:
			return self.responses.pop(0)
		return None

	def close(self) -> None:
		for handler in list(self.close_handlers):
			handler("closed")
		self.close_handlers.clear()


def make_handle(
	responses: list[Any] | None = None,
) -> tuple[Ref[Any], DummyChannel]:
	channel = DummyChannel(responses)
	manager = RefsManager(cast(Channel, cast(object, channel)))
	handle = Ref(ref_id="ref-1")
	handle.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	handle._handle_mounted()  # pyright: ignore[reportPrivateUsage]
	return handle, channel


@pytest.mark.asyncio
async def test_ref_attr_ops_payloads() -> None:
	handle, channel = make_handle(["alpha", "beta", "2", None])

	assert await handle.get_attr("data-test") == "alpha"
	assert await handle.set_attr("className", "btn") == "beta"
	assert await handle.set_attr("tabIndex", 2) == "2"
	await handle.remove_attr("data-test")

	assert channel.requested == [
		(
			"ref:request",
			{"refId": "ref-1", "op": "getAttr", "payload": {"name": "data-test"}},
			None,
		),
		(
			"ref:request",
			{
				"refId": "ref-1",
				"op": "setAttr",
				"payload": {"name": "class", "value": "btn"},
			},
			None,
		),
		(
			"ref:request",
			{
				"refId": "ref-1",
				"op": "setAttr",
				"payload": {"name": "tabindex", "value": 2},
			},
			None,
		),
		(
			"ref:request",
			{"refId": "ref-1", "op": "removeAttr", "payload": {"name": "data-test"}},
			None,
		),
	]


@pytest.mark.asyncio
async def test_ref_prop_ops_payloads() -> None:
	handle, channel = make_handle(["value", True, "next"])

	assert await handle.get_prop("value") == "value"
	assert await handle.get_prop("checked") is True
	assert await handle.set_prop("value", "next") == "next"

	assert channel.requested == [
		(
			"ref:request",
			{"refId": "ref-1", "op": "getProp", "payload": {"name": "value"}},
			None,
		),
		(
			"ref:request",
			{"refId": "ref-1", "op": "getProp", "payload": {"name": "checked"}},
			None,
		),
		(
			"ref:request",
			{
				"refId": "ref-1",
				"op": "setProp",
				"payload": {"name": "value", "value": "next"},
			},
			None,
		),
	]


@pytest.mark.asyncio
async def test_ref_attr_prop_validation() -> None:
	handle, _ = make_handle()

	with pytest.raises(ValueError, match="ref attribute name cannot start with 'on'"):
		await handle.get_attr("onClick")

	with pytest.raises(ValueError, match="ref attribute name must be non-empty"):
		await handle.set_attr("   ", "x")

	with pytest.raises(ValueError, match="Unsupported ref property"):
		await handle.get_prop("madeUp")

	with pytest.raises(ValueError, match="read-only"):
		await handle.set_prop("scrollHeight", 10)


def test_ref_emit_payloads() -> None:
	handle, channel = make_handle()

	handle.focus(prevent_scroll=True)
	handle.scroll_to(top=10, behavior="smooth")
	handle.scroll_by(left=5)
	handle.set_selection_range(1, 3, direction="forward")
	handle.submit()
	handle.reset()

	assert channel.emitted == [
		(
			"ref:call",
			{"refId": "ref-1", "op": "focus", "payload": {"preventScroll": True}},
		),
		(
			"ref:call",
			{
				"refId": "ref-1",
				"op": "scrollTo",
				"payload": {"top": 10, "behavior": "smooth"},
			},
		),
		(
			"ref:call",
			{"refId": "ref-1", "op": "scrollBy", "payload": {"left": 5}},
		),
		(
			"ref:call",
			{
				"refId": "ref-1",
				"op": "setSelectionRange",
				"payload": {"start": 1, "end": 3, "direction": "forward"},
			},
		),
		("ref:call", {"refId": "ref-1", "op": "submit", "payload": None}),
		("ref:call", {"refId": "ref-1", "op": "reset", "payload": None}),
	]


@pytest.mark.asyncio
async def test_ref_set_style_payload() -> None:
	handle, channel = make_handle([None])

	await handle.set_style({"color": "red", "margin-top": 0})

	assert channel.requested == [
		(
			"ref:request",
			{
				"refId": "ref-1",
				"op": "setStyle",
				"payload": {"styles": {"color": "red", "margin-top": 0}},
			},
			None,
		),
	]


@pytest.mark.asyncio
async def test_ref_set_style_rejects_bool() -> None:
	handle, _ = make_handle()

	with pytest.raises(
		TypeError, match="set_style\\(\\) values must be string, number, or None"
	):
		await handle.set_style({"display": True})


def test_ref_can_be_created_without_render_session() -> None:
	handle = ps.ref()
	assert isinstance(handle, Ref)


@pytest.mark.asyncio
async def test_ref_detach_cancels_waiters() -> None:
	handle = Ref()
	channel = DummyChannel()
	manager = RefsManager(cast(Channel, cast(object, channel)))
	handle.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	waiter = asyncio.create_task(handle.wait_mounted())
	await asyncio.sleep(0)
	handle.detach()
	with pytest.raises(RefNotMounted, match="Ref detached"):
		await waiter


def test_ref_unmount_handlers_only_after_mount() -> None:
	events: list[str] = []

	handle = Ref()
	handle.on_unmount(lambda: events.append("unmount"))
	channel = DummyChannel()
	manager = RefsManager(cast(Channel, cast(object, channel)))
	handle.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	handle.detach()

	assert events == []


def test_ref_channel_close_detaches() -> None:
	handle = Ref()
	channel = DummyChannel()
	manager = RefsManager(cast(Channel, cast(object, channel)))
	handle.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	handle._handle_mounted()  # pyright: ignore[reportPrivateUsage]
	channel.close()
	assert handle.mounted is False
	with pytest.raises(RuntimeError, match="Ref is not attached"):
		_ = handle.channel_id


def test_ref_unmount_allows_remount() -> None:
	events: list[str] = []
	channel = DummyChannel()
	manager = RefsManager(cast(Channel, cast(object, channel)))
	handle = Ref(ref_id="ref-1")
	handle.on_mount(lambda: events.append("mount"))
	handle.on_unmount(lambda: events.append("unmount"))
	manager.begin_render("/")
	handle.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	manager.commit_render("/")
	manager_any = cast(Any, manager)
	manager_any._on_mounted({"refId": handle.id})
	manager_any._on_unmounted({"refId": handle.id})
	assert handle.mounted is False
	assert handle.channel_id == channel.id
	manager_any._on_mounted({"refId": handle.id})
	assert events == ["mount", "unmount", "mount"]


def test_ref_removed_from_render_detaches() -> None:
	events: list[str] = []
	channel = DummyChannel()
	manager = RefsManager(cast(Channel, cast(object, channel)))
	handle = Ref(ref_id="ref-1")
	handle.on_unmount(lambda: events.append("unmount"))
	manager.begin_render("/")
	handle.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	manager.commit_render("/")
	manager_any = cast(Any, manager)
	manager_any._on_mounted({"refId": handle.id})
	manager.begin_render("/")
	manager.commit_render("/")
	assert events == ["unmount"]
	with pytest.raises(RuntimeError, match="Ref is not attached"):
		_ = handle.channel_id


def test_ref_handler_exception_isolated() -> None:
	channel = DummyChannel()
	manager = RefsManager(cast(Channel, cast(object, channel)))
	bad = Ref(ref_id="ref-bad")
	good = Ref(ref_id="ref-good")
	events: list[str] = []

	def boom() -> None:
		raise ValueError("boom")

	bad.on_mount(boom)
	good.on_mount(lambda: events.append("ok"))
	manager.begin_render("/")
	bad.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	good.attach(
		manager,
		render=SimpleNamespace(),
		route_ctx=None,
		route_path="/",
	)
	manager.commit_render("/")
	manager_any = cast(Any, manager)
	manager_any._on_mounted({"refId": bad.id})
	manager_any._on_mounted({"refId": good.id})
	assert events == ["ok"]
