"""Spec for the request/reply primitive behind call_api, run_js, and
Channel.request: correlation id -> future, resolved synchronously."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.messages import ClientMessage
from pulse.middleware import Deny, Ok, PulseMiddleware
from pulse.replies import PendingReplies
from pulse.render_session import RenderSession
from pulse.serializer import serialize
from pulse.user_session import UserSession


def _future() -> asyncio.Future[object]:
	return asyncio.get_running_loop().create_future()


@pytest.mark.asyncio
async def test_resolve_sets_result_and_pops():
	replies = PendingReplies()
	fut = _future()
	replies.register("r1", fut)

	replies.resolve("r1", {"x": 1})

	assert fut.result() == {"x": 1}
	assert len(replies) == 0
	assert "r1" not in replies


@pytest.mark.asyncio
async def test_reject_sets_exception_and_pops():
	replies = PendingReplies()
	fut = _future()
	replies.register("r1", fut)

	replies.reject("r1", RuntimeError("boom"))

	with pytest.raises(RuntimeError, match="boom"):
		fut.result()
	assert len(replies) == 0


@pytest.mark.asyncio
async def test_apply_reply_resolves_payload():
	replies = PendingReplies()
	fut = _future()
	replies.register("r1", fut)

	replies.apply({"type": "reply", "id": "r1", "payload": 7})

	assert fut.result() == 7
	assert len(replies) == 0


@pytest.mark.asyncio
async def test_apply_reply_rejects_on_error():
	replies = PendingReplies()
	fut = _future()
	replies.register("r1", fut)

	replies.apply({"type": "reply", "id": "r1", "error": "boom"})

	with pytest.raises(RuntimeError, match="boom"):
		fut.result()


@pytest.mark.asyncio
async def test_unknown_id_is_a_noop():
	replies = PendingReplies()
	replies.resolve("missing", 1)
	replies.reject("missing", RuntimeError("boom"))
	replies.discard("missing")


@pytest.mark.asyncio
async def test_duplicate_register_fails():
	replies = PendingReplies()
	replies.register("r1", _future())
	with pytest.raises(ValueError, match="Duplicate"):
		replies.register("r1", _future())


@pytest.mark.asyncio
async def test_resolve_after_discard_is_a_noop():
	# A late reply racing a timeout must lose silently.
	replies = PendingReplies()
	fut = _future()
	replies.register("r1", fut)
	replies.discard("r1")

	replies.resolve("r1", 42)

	assert not fut.done()


@pytest.mark.asyncio
async def test_resolve_on_already_done_future_is_a_noop():
	replies = PendingReplies()
	fut = _future()
	replies.register("r1", fut)
	fut.cancel()

	replies.resolve("r1", 42)
	assert fut.cancelled()


@pytest.mark.asyncio
async def test_reject_where_only_hits_matching_cancel_key():
	replies = PendingReplies()
	ch_a1, ch_a2, ch_b, plain = _future(), _future(), _future(), _future()
	replies.register("a1", ch_a1, cancel_key="ch-a")
	replies.register("a2", ch_a2, cancel_key="ch-a")
	replies.register("b1", ch_b, cancel_key="ch-b")
	replies.register("p1", plain)

	replies.reject_where("ch-a", RuntimeError("closed"))

	with pytest.raises(RuntimeError):
		ch_a1.result()
	with pytest.raises(RuntimeError):
		ch_a2.result()
	assert not ch_b.done()
	assert not plain.done()
	assert len(replies) == 2


@pytest.mark.asyncio
async def test_cancel_all_cancels_and_clears():
	replies = PendingReplies()
	f1, f2 = _future(), _future()
	replies.register("r1", f1)
	replies.register("r2", f2, cancel_key="ch")

	replies.cancel_all()

	assert f1.cancelled()
	assert f2.cancelled()
	assert len(replies) == 0


@pytest.mark.asyncio
async def test_socket_reply_resolves_and_skips_middleware():
	class Tracking(PulseMiddleware):
		called: bool = False

		@override
		async def message(
			self, *, data: ClientMessage, session: Any, next: Any
		) -> Ok[None] | Deny:
			self.called = True
			return await next()

	middleware = Tracking()
	app = ps.App(middleware=middleware)
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = cast(UserSession, cast(object, session))
	app._socket_to_render["socket-1"] = render.id  # pyright: ignore[reportPrivateUsage]

	fut: asyncio.Future[object] = asyncio.get_running_loop().create_future()
	render.replies.register("corr-1", fut)

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize({"type": "reply", "id": "corr-1", "payload": 7}),
	)

	assert fut.result() == 7
	assert middleware.called is False
	render.close()
