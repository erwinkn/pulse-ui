from __future__ import annotations

import json
from datetime import date

import pytest
from pulse_railway.constants import PULSE_RAILWAY_REDIS_URL
from pulse_railway.session import RailwayRedisSessionStore, RailwaySessionStore
from redis_fakes import FakeRedisClient


def test_railway_session_store_env_name_is_dedicated() -> None:
	assert PULSE_RAILWAY_REDIS_URL == "PULSE_RAILWAY_REDIS_URL"


def test_railway_session_store_resolves_env_url() -> None:
	store = RailwaySessionStore(
		env={PULSE_RAILWAY_REDIS_URL: "redis://shared:6379/0"},
	)

	assert store.configured_url() == "redis://shared:6379/0"


def test_railway_session_store_requires_dedicated_env_var() -> None:
	store = RailwaySessionStore(env={})

	with pytest.raises(RuntimeError, match=PULSE_RAILWAY_REDIS_URL):
		store._ensure_client()


@pytest.mark.asyncio
async def test_railway_session_store_serializes_through_redis_client() -> None:
	client = FakeRedisClient()
	store = RailwayRedisSessionStore(
		client=client,
		prefix="pulse:test",
	)

	await store.init()
	await store.save(
		"sid-1",
		{"today": "2026-04-05", "roles": ["admin"], "enabled": True},
	)
	assert json.loads(client.data["pulse:test:json-v1:sid-1"]) == {
		"$pulse": "session",
		"version": 1,
		"data": {
			"today": "2026-04-05",
			"roles": ["admin"],
			"enabled": True,
		},
	}

	session = await store.get("sid-1")

	assert session == {
		"today": "2026-04-05",
		"roles": ["admin"],
		"enabled": True,
	}
	await store.delete("sid-1")
	assert await store.get("sid-1") is None
	await store.close()
	assert client.closed is False


@pytest.mark.asyncio
async def test_railway_session_store_ignores_legacy_namespace() -> None:
	client = FakeRedisClient()
	legacy_payload = '[[[],[],[],[]],{"user_id":"user-1"}]'
	client.data["pulse:test:sid-1"] = legacy_payload
	store = RailwayRedisSessionStore(client=client, prefix="pulse:test")

	session = await store.get("sid-1")

	assert session is None
	assert client.data["pulse:test:sid-1"] == legacy_payload

	assert await store.create("sid-1") == {}
	assert json.loads(client.data["pulse:test:json-v1:sid-1"]) == {
		"$pulse": "session",
		"version": 1,
		"data": {},
	}

	await store.delete("sid-1")
	assert "pulse:test:json-v1:sid-1" not in client.data
	assert client.data["pulse:test:sid-1"] == legacy_payload


@pytest.mark.asyncio
async def test_railway_session_store_rejects_unknown_format_version() -> None:
	client = FakeRedisClient()
	client.data["pulse:session:json-v1:sid-1"] = (
		'{"$pulse":"session","version":2,"data":{}}'
	)
	store = RailwayRedisSessionStore(client=client)

	with pytest.raises(ValueError, match="session format version: 2"):
		await store.get("sid-1")


@pytest.mark.asyncio
async def test_railway_session_store_rejects_malformed_current_record() -> None:
	client = FakeRedisClient()
	client.data["pulse:session:json-v1:sid-1"] = "[]"
	store = RailwayRedisSessionStore(client=client)

	with pytest.raises(TypeError, match="Session data must be a JSON object"):
		await store.get("sid-1")


@pytest.mark.asyncio
async def test_railway_session_store_rejects_non_json_data() -> None:
	store = RailwayRedisSessionStore(client=FakeRedisClient())

	with pytest.raises(TypeError, match="JSON-compatible"):
		await store.save("sid-1", {"today": date(2026, 4, 5)})

	assert await store.get("sid-1") is None
