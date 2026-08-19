"""Decision semantics of MiddlewareStack.

Coercion happens once, where each user hook returns: anything that is
not Ok/Deny counts as allow. Decisions propagate through `next()` —
an inner Deny reaches the caller unless an outer middleware overrides it.
"""

from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.messages import ClientMessage
from pulse.middleware import Deny, MiddlewareStack, Ok, PulseMiddleware
from pulse.render_session import RenderSession
from pulse.serializer import serialize
from pulse.user_session import UserSession


class Passthrough(PulseMiddleware):
	pass


class DenyMessage(PulseMiddleware):
	@override
	async def message(self, *, data: Any, session: Any, next: Any) -> Any:
		return Deny()


class ReturnGarbage(PulseMiddleware):
	@override
	async def message(self, *, data: Any, session: Any, next: Any) -> Any:
		await next()
		return "not a decision"


class OverrideInnerDeny(PulseMiddleware):
	@override
	async def message(self, *, data: Any, session: Any, next: Any) -> Any:
		await next()
		return Ok(None)


class DenyChannel(PulseMiddleware):
	@override
	async def channel(self, *, next: Any, **kwargs: Any) -> Any:
		return Deny()


_MSG = cast(
	ClientMessage,
	cast(object, {"type": "callback", "path": "/", "callback": "k", "args": []}),
)


def _terminal(applied: list[str]):
	async def next() -> Ok[None]:
		applied.append("apply")
		return Ok()

	return next


@pytest.mark.asyncio
async def test_non_decision_return_is_allow():
	applied: list[str] = []
	stack = MiddlewareStack([ReturnGarbage()])

	res = await stack.message(data=_MSG, session={}, next=_terminal(applied))

	assert isinstance(res, Ok)
	assert applied == ["apply"]


@pytest.mark.asyncio
async def test_inner_deny_propagates_through_outer_middleware():
	applied: list[str] = []
	stack = MiddlewareStack([Passthrough(), DenyMessage()])

	res = await stack.message(data=_MSG, session={}, next=_terminal(applied))

	assert isinstance(res, Deny)
	assert applied == []


@pytest.mark.asyncio
async def test_outer_middleware_can_override_inner_deny():
	applied: list[str] = []
	stack = MiddlewareStack([OverrideInnerDeny(), DenyMessage()])

	res = await stack.message(data=_MSG, session={}, next=_terminal(applied))

	assert isinstance(res, Ok)
	assert applied == []


@pytest.mark.asyncio
async def test_channel_inner_deny_propagates():
	applied: list[str] = []
	stack = MiddlewareStack([Passthrough(), DenyChannel()])

	async def terminal() -> Ok[None]:
		applied.append("apply")
		return Ok()

	res = await stack.channel(
		channel_id="ch-1",
		event="ping",
		payload=None,
		request_id=None,
		session={},
		next=terminal,
	)

	assert isinstance(res, Deny)
	assert applied == []


@pytest.mark.asyncio
async def test_inner_deny_reports_deny_error_to_client(
	monkeypatch: pytest.MonkeyPatch,
):
	# Regression: the stack used to mask a non-outermost Deny into Ok, so
	# the command was dropped without the client ever seeing a deny error.
	app = ps.App(middleware=[Passthrough(), DenyMessage()])
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = cast(UserSession, cast(object, session))
	app._socket_to_render["socket-1"] = render.id  # pyright: ignore[reportPrivateUsage]

	reported: list[tuple[Any, ...]] = []

	def report_error(*args: Any) -> None:
		reported.append(args)

	monkeypatch.setattr(render, "report_error", report_error)

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize({"type": "callback", "path": "/", "callback": "k", "args": []}),
	)

	assert len(reported) == 1
	path, phase, _exc, details = reported[0]
	assert (path, phase, details) == ("/", "server", {"kind": "deny"})
	render.close()


@pytest.mark.asyncio
async def test_allow_still_applies_command():
	applied: list[str] = []
	stack = MiddlewareStack([Passthrough(), Passthrough()])

	res = await stack.message(data=_MSG, session={}, next=_terminal(applied))

	assert isinstance(res, Ok)
	assert applied == ["apply"]


@pytest.mark.asyncio
async def test_connect_non_decision_return_is_allow():
	class GarbageConnect(PulseMiddleware):
		@override
		async def connect(self, *, request: Any, session: Any, next: Any) -> Any:
			await next()
			return None

	stack = MiddlewareStack([GarbageConnect()])

	async def terminal() -> Ok[None]:
		return Ok()

	res = await stack.connect(
		request=cast(Any, SimpleNamespace()), session={}, next=terminal
	)
	assert isinstance(res, Ok)
