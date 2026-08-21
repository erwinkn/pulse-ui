"""Decision semantics of MiddlewareStack.

Decision hooks must return Ok or Deny; anything else raises (fail closed).
Decisions propagate through `next()` — an inner Deny is final because the
command never ran, so an outer Ok cannot override it.
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
async def test_non_decision_return_fails_closed():
	applied: list[str] = []
	stack = MiddlewareStack([ReturnGarbage()])

	with pytest.raises(TypeError, match="must return Ok or Deny"):
		await stack.message(data=_MSG, session={}, next=_terminal(applied))


@pytest.mark.asyncio
async def test_inner_deny_propagates_through_outer_middleware():
	applied: list[str] = []
	stack = MiddlewareStack([Passthrough(), DenyMessage()])

	res = await stack.message(data=_MSG, session={}, next=_terminal(applied))

	assert isinstance(res, Deny)
	assert applied == []


@pytest.mark.asyncio
async def test_inner_deny_is_final_even_if_outer_returns_ok():
	# The denied command never ran, so an outer Ok would mean
	# "allowed but not executed" — the stack refuses that.
	applied: list[str] = []
	stack = MiddlewareStack([OverrideInnerDeny(), DenyMessage()])

	res = await stack.message(data=_MSG, session={}, next=_terminal(applied))

	assert isinstance(res, Deny)
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
async def test_connect_non_decision_return_fails_closed():
	class GarbageConnect(PulseMiddleware):
		@override
		async def connect(self, *, request: Any, session: Any, next: Any) -> Any:
			await next()
			return None

	stack = MiddlewareStack([GarbageConnect()])

	async def terminal() -> Ok[None]:
		return Ok()

	with pytest.raises(TypeError, match="must return Ok or Deny"):
		await stack.connect(
			request=cast(Any, SimpleNamespace()), session={}, next=terminal
		)


@pytest.mark.asyncio
async def test_garbage_return_cannot_swallow_inner_deny():
	applied: list[str] = []
	stack = MiddlewareStack([ReturnGarbage(), DenyMessage()])

	with pytest.raises(TypeError, match="must return Ok or Deny"):
		await stack.message(data=_MSG, session={}, next=_terminal(applied))
	assert applied == []


@pytest.mark.asyncio
async def test_channel_inner_deny_is_final_even_if_outer_returns_ok():
	class OverrideChannelDeny(PulseMiddleware):
		@override
		async def channel(self, *, next: Any, **kwargs: Any) -> Any:
			await next()
			return Ok(None)

	applied: list[str] = []
	stack = MiddlewareStack([OverrideChannelDeny(), DenyChannel()])

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


def _bind(app: ps.App, render: RenderSession, session: Any) -> None:
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = cast(UserSession, cast(object, session))
	app._socket_to_render["socket-1"] = render.id  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_message_middleware_exception_is_reported_to_client(
	monkeypatch: pytest.MonkeyPatch,
):
	class Boom(PulseMiddleware):
		@override
		async def message(self, *, data: Any, session: Any, next: Any) -> Any:
			raise RuntimeError("boom")

	app = ps.App(middleware=[Boom()])
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	_bind(app, render, session)

	reported: list[tuple[Any, ...]] = []

	def report_error(*args: Any) -> None:
		reported.append(args)

	monkeypatch.setattr(render, "report_error", report_error)

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize({"type": "callback", "path": "/", "callback": "k", "args": []}),
	)

	assert len(reported) == 1
	path, phase, exc = reported[0][:3]
	assert (path, phase) == ("/", "server")
	assert isinstance(exc, RuntimeError)
	render.close()


@pytest.mark.asyncio
async def test_channel_middleware_exception_sends_request_error(
	monkeypatch: pytest.MonkeyPatch,
):
	class Boom(PulseMiddleware):
		@override
		async def channel(self, *, next: Any, **kwargs: Any) -> Any:
			raise RuntimeError("boom")

	app = ps.App(middleware=[Boom()])
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	_bind(app, render, session)

	errors: list[tuple[str, str]] = []

	def send_error(req_id: str, message: str) -> None:
		errors.append((req_id, message))

	monkeypatch.setattr(render.channels, "send_error", send_error)

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize(
			{
				"type": "channel_message",
				"channel": "ch-1",
				"event": "ping",
				"payload": None,
				"requestId": "req-1",
			}
		),
	)

	assert errors == [("req-1", "boom")]
	render.close()
