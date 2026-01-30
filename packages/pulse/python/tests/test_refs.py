from __future__ import annotations

from typing import Any, cast

import pytest
from pulse.channel import Channel
from pulse.refs import RefHandle


class DummyChannel:
	id: str = "chan-test"
	responses: list[Any]

	def __init__(self, responses: list[Any] | None = None) -> None:
		self.emitted: list[tuple[str, Any]] = []
		self.requested: list[tuple[str, Any, float | None]] = []
		self.responses = list(responses or [])

	def on(self, event: str, handler: Any):
		def _remove() -> None:
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
		return None


def make_handle(
	responses: list[Any] | None = None,
) -> tuple[RefHandle[Any], DummyChannel]:
	channel = DummyChannel(responses)
	handle = RefHandle(cast(Channel, cast(object, channel)), ref_id="ref-1")
	handle._on_mounted({"refId": "ref-1"})  # pyright: ignore[reportPrivateUsage]
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
