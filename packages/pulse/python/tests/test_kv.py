from __future__ import annotations

from datetime import date
from pathlib import Path

import pulse as ps
import pytest


@pytest.mark.asyncio
async def test_memory_kv_store_supports_ttl_and_only_if_missing() -> None:
	store = ps.MemoryKVStore()
	await store.init()

	assert await store.set("alpha", "1", only_if_missing=True) is True
	assert await store.set("alpha", "2", only_if_missing=True) is False
	assert await store.get("alpha") == "1"

	assert await store.set("temp", "x", ttl_seconds=0) is True
	assert await store.get("temp") is None

	await store.close()


@pytest.mark.asyncio
async def test_sqlite_kv_store_persists_values_and_scans(tmp_path: Path) -> None:
	path = tmp_path / "pulse.sqlite3"
	store = ps.SQLiteKVStore(path)
	await store.init()

	assert await store.set("session:a", "A") is True
	assert await store.set("session:b", "B") is True
	assert await store.scan_prefix("session:") == ["session:a", "session:b"]

	await store.close()

	reopened = ps.SQLiteKVStore(path)
	await reopened.init()
	assert await reopened.get("session:a") == "A"
	await reopened.close()


@pytest.mark.asyncio
async def test_session_store_serializes_through_kv() -> None:
	store = ps.SessionStore(store=ps.MemoryKVStore())
	await store.init()
	await store.save("sid-1", {"today": date(2026, 4, 5)})

	session = await store.get("sid-1")

	assert session is not None
	assert session["today"] == date(2026, 4, 5)
	await store.close()


@pytest.mark.asyncio
async def test_app_uses_cookie_sessions_by_default_in_dev() -> None:
	app = ps.App(mode="subdomains")
	app.setup("http://localhost:8000")
	session: ps.UserSession | None = None

	try:
		assert isinstance(app.store, ps.SQLiteKVStore)
		assert isinstance(app.session_store, ps.CookieSessionStore)

		session = await app.get_or_create_session(None)

		assert session.get_cookie_value(app.cookie.name) is not None

		with ps.PulseContext(app=app):
			assert ps.app() is app
			assert ps.store() is app.store
	finally:
		if isinstance(app.session_store, ps.CookieSessionStore) and session is not None:
			session.dispose()
		if app.store is not None:
			await app.store.close()
