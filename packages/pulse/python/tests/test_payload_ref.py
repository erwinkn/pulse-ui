# pyright: reportPrivateUsage=false

import asyncio
import gzip
import json

import httpx
import pulse as ps
import pulse.app as pulse_app
import pytest
from pulse.messages import ServerMessage
from pulse.serializer import Serialized, deserialize, serialize


def _server_message(text: str) -> ServerMessage:
	return {
		"type": "server_error",
		"path": "/",
		"error": {"message": text, "phase": "server"},
	}


def _global_message(text: str) -> ServerMessage:
	return {
		"type": "api_call",
		"id": "api-1",
		"url": f"/api/{text}",
		"method": "GET",
		"headers": {},
		"body": None,
		"credentials": "include",
	}


def _encoded(message: ServerMessage) -> str:
	return json.dumps(serialize(message), separators=(",", ":"))


def _decoded(payload: Serialized) -> dict[str, object]:
	decoded = deserialize(payload)
	assert isinstance(decoded, dict)
	return decoded


async def _client_with_render(app: ps.App) -> tuple[httpx.AsyncClient, str]:
	transport = httpx.ASGITransport(app=app.fastapi)
	client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8000")
	response = await client.get("/_pulse/health")
	assert response.status_code == 200
	session = next(iter(app.user_sessions.values()))
	render = app.create_render("render-1", session)
	return client, render.id


def test_payload_under_threshold_uses_socket_payload():
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded))

	payload = app._serialize_server_message("render-1", message)

	assert deserialize(payload) == message
	assert app._payload_stashes == {}


@pytest.mark.asyncio
async def test_payload_over_threshold_emits_ref_and_stashes_exact_json():
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)

	try:
		payload = app._serialize_server_message("render-1", message)
		ref = _decoded(payload)

		assert ref["type"] == "payload_ref"
		assert ref["size"] == len(encoded.encode())
		stash_value = app._payload_stashes["render-1"][str(ref["id"])]
		assert gzip.decompress(stash_value[0]).decode() == encoded
	finally:
		await app.close()


@pytest.mark.asyncio
async def test_payload_get_is_one_shot_and_404s_unknown_ids(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)
	app.setup("http://localhost:8000")
	client, render_id = await _client_with_render(app)
	try:
		payload = app._serialize_server_message(render_id, message)
		ref = _decoded(payload)

		unknown_render = await client.get(f"/_pulse/payloads/unknown/{ref['id']}")
		assert unknown_render.status_code == 404

		unknown_payload = await client.get(f"/_pulse/payloads/{render_id}/unknown")
		assert unknown_payload.status_code == 404

		response = await client.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
		assert response.status_code == 200
		assert response.text == encoded

		again = await client.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
		assert again.status_code == 404
	finally:
		await client.aclose()
		await app.close()


@pytest.mark.asyncio
async def test_payload_stash_ttl_expires_to_404(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	monkeypatch.setattr(pulse_app, "PAYLOAD_STASH_TTL", 0.01)
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)
	app.setup("http://localhost:8000")
	client, render_id = await _client_with_render(app)
	try:
		payload = app._serialize_server_message(render_id, message)
		ref = _decoded(payload)

		await asyncio.sleep(0.03)

		assert render_id not in app._payload_stashes
		response = await client.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
		assert response.status_code == 404
	finally:
		await client.aclose()
		await app.close()


@pytest.mark.asyncio
async def test_payload_fetch_cancels_timer(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	monkeypatch.setattr(pulse_app, "PAYLOAD_STASH_TTL", 0.01)
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)
	app.setup("http://localhost:8000")
	client, render_id = await _client_with_render(app)
	try:
		payload = app._serialize_server_message(render_id, message)
		ref = _decoded(payload)
		_, handle = app._payload_stashes[render_id][str(ref["id"])]

		response = await client.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
		assert response.status_code == 200
		assert response.text == encoded
		assert render_id not in app._payload_stashes
		assert handle not in app._timers._handles

		await asyncio.sleep(0.03)
		assert render_id not in app._payload_stashes
	finally:
		await client.aclose()
		await app.close()


@pytest.mark.asyncio
async def test_payload_get_returns_gzip(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)
	app.setup("http://localhost:8000")
	client, render_id = await _client_with_render(app)
	try:
		payload = app._serialize_server_message(render_id, message)
		ref = _decoded(payload)
		stash_value = app._payload_stashes[render_id][str(ref["id"])]
		assert gzip.decompress(stash_value[0]).decode() == encoded

		response = await client.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
		assert response.status_code == 200
		assert response.headers["content-encoding"] == "gzip"
		assert response.text == encoded
	finally:
		await client.aclose()
		await app.close()


@pytest.mark.asyncio
async def test_payload_get_denies_other_sessions(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)
	app.setup("http://localhost:8000")
	client, render_id = await _client_with_render(app)
	try:
		payload = app._serialize_server_message(render_id, message)
		ref = _decoded(payload)

		other_transport = httpx.ASGITransport(app=app.fastapi)
		other = httpx.AsyncClient(
			transport=other_transport, base_url="http://localhost:8000"
		)
		try:
			stolen = await other.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
			assert stolen.status_code == 404
		finally:
			await other.aclose()

		response = await client.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
		assert response.status_code == 200
	finally:
		await client.aclose()
		await app.close()


def test_threshold_none_never_offloads():
	message = _server_message("x" * 1024)
	app = ps.App(large_message_threshold=None)

	payload = app._serialize_server_message("render-1", message)

	assert deserialize(payload) == message
	assert app._payload_stashes == {}


@pytest.mark.asyncio
async def test_payload_stash_cleared_on_render_close(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	message = _server_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)
	app.setup("http://localhost:8000")
	session = await app.get_or_create_session(None)
	render = app.create_render("render-1", session)

	payload = app._serialize_server_message(render.id, message)
	ref = _decoded(payload)
	_, handle = app._payload_stashes[render.id][str(ref["id"])]
	app.close_render(render.id)

	assert render.id not in app._payload_stashes
	assert handle not in app._timers._handles
	await app.close()


@pytest.mark.asyncio
async def test_disconnected_queue_payload_ref_fetchable_after_reconnect(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	message = _global_message("x" * 64)
	encoded = _encoded(message)
	app = ps.App(large_message_threshold=len(encoded) - 1)
	app.setup("http://localhost:8000")
	client, render_id = await _client_with_render(app)
	try:
		render = app.render_sessions[render_id]
		render.send(message)

		sent: list[Serialized] = []
		render.connect(
			lambda msg: sent.append(app._serialize_server_message(render.id, msg))
		)

		assert len(sent) == 1
		ref = _decoded(sent[0])
		assert ref["type"] == "payload_ref"

		response = await client.get(f"/_pulse/payloads/{render_id}/{ref['id']}")
		assert response.status_code == 200
		assert response.text == encoded
	finally:
		await client.aclose()
		await app.close()
