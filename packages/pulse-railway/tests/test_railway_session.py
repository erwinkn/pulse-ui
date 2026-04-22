from __future__ import annotations

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
	await store.save("sid-1", {"today": date(2026, 4, 5)})

	session = await store.get("sid-1")

	assert session == {"today": date(2026, 4, 5)}
	await store.delete("sid-1")
	assert await store.get("sid-1") is None
	await store.close()
	assert client.closed is False
