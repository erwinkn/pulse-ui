"""Spec for the request/reply primitive behind call_api, eval_js, and
Channel.request: correlation id -> future, resolved synchronously."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.messages import ClientMessage
from pulse.middleware import Deny, Ok, PulseMiddleware
from pulse.render_session import RenderSession
from pulse.replies import PendingReplies
from pulse.serializer import serialize
from pulse.user_session import UserSession


@pytest.mark.asyncio
async def test_resolve_sets_result_and_pops():
	replies = PendingReplies()
	with replies.pending() as reply:
		replies.resolve(reply.id, {"x": 1})

		assert reply.future.result() == {"x": 1}
		assert len(replies) == 0
		assert reply.id not in replies


@pytest.mark.asyncio
async def test_reject_sets_exception_and_pops():
	replies = PendingReplies()
	with replies.pending() as reply:
		replies.reject(reply.id, RuntimeError("boom"))

		with pytest.raises(RuntimeError, match="boom"):
			reply.future.result()
		assert len(replies) == 0


@pytest.mark.asyncio
async def test_apply_reply_resolves_payload():
	replies = PendingReplies()
	with replies.pending() as reply:
		replies.apply({"type": "reply", "id": reply.id, "payload": 7})

		assert reply.future.result() == 7
		assert len(replies) == 0


@pytest.mark.asyncio
async def test_apply_reply_rejects_on_error():
	replies = PendingReplies()
	with replies.pending(error=ValueError) as reply:
		replies.apply({"type": "reply", "id": reply.id, "error": "boom"})

		with pytest.raises(ValueError, match="boom"):
			reply.future.result()
		assert len(replies) == 0


@pytest.mark.asyncio
async def test_unknown_id_is_a_noop():
	replies = PendingReplies()
	replies.resolve("missing", 1)
	replies.reject("missing", RuntimeError("boom"))
	replies.discard("missing")


@pytest.mark.asyncio
async def test_pending_generates_unique_ids():
	replies = PendingReplies()
	with replies.pending() as first, replies.pending() as second:
		assert first.id != second.id
		assert first.id in replies
		assert second.id in replies


@pytest.mark.asyncio
async def test_resolve_after_discard_is_a_noop():
	# A late reply racing a timeout must lose silently.
	replies = PendingReplies()
	with replies.pending() as reply:
		replies.discard(reply.id)

		replies.resolve(reply.id, 42)

		assert not reply.future.done()


@pytest.mark.asyncio
async def test_resolve_on_already_done_future_is_a_noop():
	replies = PendingReplies()
	with replies.pending() as reply:
		reply.future.cancel()

		replies.resolve(reply.id, 42)
		assert reply.future.cancelled()


@pytest.mark.asyncio
async def test_reject_where_only_hits_matching_cancel_key():
	replies = PendingReplies()
	with (
		replies.pending(cancel_key="ch-a") as ch_a1,
		replies.pending(cancel_key="ch-a") as ch_a2,
		replies.pending(cancel_key="ch-b") as ch_b,
		replies.pending() as plain,
	):
		replies.reject_where("ch-a", RuntimeError("closed"))

		with pytest.raises(RuntimeError):
			ch_a1.future.result()
		with pytest.raises(RuntimeError):
			ch_a2.future.result()
		assert not ch_b.future.done()
		assert not plain.future.done()
		assert len(replies) == 2


@pytest.mark.asyncio
async def test_cancel_all_cancels_and_clears():
	replies = PendingReplies()
	with replies.pending() as first, replies.pending(cancel_key="ch") as second:
		replies.cancel_all()

		assert first.future.cancelled()
		assert second.future.cancelled()
		assert len(replies) == 0


@pytest.mark.asyncio
async def test_pending_cleans_up_on_timeout():
	replies = PendingReplies()
	with pytest.raises(asyncio.TimeoutError):
		with replies.pending() as reply:
			await asyncio.wait_for(reply.future, timeout=0)
	assert len(replies) == 0


@pytest.mark.asyncio
async def test_pending_cleans_up_on_outer_cancellation():
	replies = PendingReplies()

	async def wait_for_reply() -> None:
		with replies.pending() as reply:
			await reply.future

	task = asyncio.create_task(wait_for_reply())
	await asyncio.sleep(0)
	task.cancel()
	with pytest.raises(asyncio.CancelledError):
		await task
	assert len(replies) == 0


@pytest.mark.asyncio
async def test_pending_cleans_up_on_body_exception():
	replies = PendingReplies()
	with pytest.raises(RuntimeError, match="send failed"):
		with replies.pending():
			raise RuntimeError("send failed")
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

	with render.replies.pending() as reply:
		await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize({"type": "reply", "id": reply.id, "payload": 7}),
		)

		assert reply.future.result() == 7
		assert middleware.called is False
	render.close()
