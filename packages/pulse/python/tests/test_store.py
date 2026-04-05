from __future__ import annotations

from typing import override

import pulse as ps
import pytest


def test_store_hook_returns_current_app_store() -> None:
	app = ps.App(store=ps.MemoryKVStore())
	with ps.PulseContext(app=app):
		assert ps.store() is app.store
		assert ps.app() is app


@pytest.mark.asyncio
async def test_app_store_persists_server_sessions() -> None:
	app = ps.App(
		store=ps.MemoryKVStore(),
		session_store=ps.SessionStore(),
		mode="subdomains",
	)
	app.setup("http://localhost:8000")

	session = await app.get_or_create_session(None)
	session.data["count"] = 1
	assert isinstance(app.session_store, ps.SessionStore)
	await app.session_store.save(session.sid, {"count": 1})

	app.user_sessions.pop(session.sid)

	loaded = await app.get_or_create_session(session.sid)

	assert loaded.data["count"] == 1


def test_explicit_session_store_keeps_own_store() -> None:
	app_store = ps.MemoryKVStore()
	session_store = ps.SessionStore(store=ps.MemoryKVStore())

	app = ps.App(store=app_store, session_store=session_store)

	assert app.store is app_store
	assert app.session_store is session_store
	assert session_store.store is not app_store


def test_session_store_without_own_kv_binds_to_app_store() -> None:
	app_store = ps.MemoryKVStore()
	session_store = ps.SessionStore()

	app = ps.App(store=app_store, session_store=session_store)

	assert app.session_store is session_store
	assert session_store.store is app_store


def test_session_store_requires_explicit_or_app_store(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv("PULSE_ENV", "prod")

	with pytest.raises(RuntimeError, match="SessionStore requires"):
		ps.App(session_store=ps.SessionStore())


def test_in_memory_session_store_works_without_app_store(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv("PULSE_ENV", "prod")

	app = ps.App(session_store=ps.InMemorySessionStore())

	assert app.store is None
	assert isinstance(app.session_store, ps.InMemorySessionStore)


@pytest.mark.asyncio
async def test_app_lifespan_initializes_shared_store_once() -> None:
	class CountingStore(ps.MemoryKVStore):
		init_calls: int
		close_calls: int

		def __init__(self) -> None:
			super().__init__()
			self.init_calls = 0
			self.close_calls = 0

		@override
		async def init(self) -> None:
			self.init_calls += 1

		@override
		async def close(self) -> None:
			self.close_calls += 1

	store = CountingStore()
	app = ps.App(store=store, session_store=ps.SessionStore())

	async with app.fastapi_lifespan(app.fastapi):
		pass

	assert store.init_calls == 1
	assert store.close_calls == 1
