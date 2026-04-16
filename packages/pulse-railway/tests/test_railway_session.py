from __future__ import annotations

from datetime import date

import pulse as ps
import pytest
from pulse_railway.constants import REDIS_URL
from pulse_railway.session import RailwayRedisSessionStore, railway_session_store


def test_redis_url_env_name_is_standard() -> None:
	assert REDIS_URL == "REDIS_URL"


def test_railway_session_store_resolves_env_url() -> None:
	store = railway_session_store(
		env={REDIS_URL: "redis://shared:6379/0"},
	)

	assert store.configured_url() == "redis://shared:6379/0"


@pytest.mark.asyncio
async def test_railway_session_store_uses_fallback_when_unconfigured() -> None:
	store = railway_session_store(fallback=ps.InMemorySessionStore())
	await store.init()

	await store.save("sid-1", {"count": 1})
	session = await store.get("sid-1")

	assert session == {"count": 1}
	await store.delete("sid-1")
	assert await store.get("sid-1") is None
	await store.close()


@pytest.mark.asyncio
async def test_railway_session_store_serializes_through_redis_client() -> None:
	class _FakeRedisClient:
		def __init__(self) -> None:
			self.data: dict[str, str] = {}
			self.closed = False

		async def get(self, key: str) -> str | None:
			return self.data.get(key)

		async def set(self, key: str, value: str) -> bool:
			self.data[key] = value
			return True

		async def delete(self, key: str) -> None:
			self.data.pop(key, None)

		async def aclose(self) -> None:
			self.closed = True

	client = _FakeRedisClient()
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
