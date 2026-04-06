from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pulse as ps
import pytest
from pulse.kv import KVStoreConfig

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_PATH = ROOT / "examples/railway/main.py"


def load_example_module():
	spec = importlib.util.spec_from_file_location("pulse_railway_example", EXAMPLE_PATH)
	if spec is None or spec.loader is None:
		raise RuntimeError(f"Could not load {EXAMPLE_PATH}")
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def test_resolve_store_prefers_shared_redis_env() -> None:
	module = load_example_module()
	store = module.resolve_store({"PULSE_KV_URL": "redis://shared:6379/0"})

	assert store.config() == KVStoreConfig(kind="redis", url="redis://shared:6379/0")


def test_create_app_binds_session_store_to_shared_store() -> None:
	module = load_example_module()
	store = ps.MemoryKVStore()
	app = module.create_app(store=store)

	assert app.store is store
	assert isinstance(app.session_store, ps.SessionStore)
	assert app.session_store.store is store


@pytest.mark.asyncio
async def test_example_preserves_session_and_shared_store_across_app_instances(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	module = load_example_module()

	class SharedMemoryStore(ps.MemoryKVStore):
		async def close(self) -> None:
			return None

	shared_store = SharedMemoryStore()

	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	monkeypatch.setenv("PULSE_DEPLOYMENT_ID", "blue")
	blue_app = module.create_app(store=shared_store)
	blue_app.setup("http://testserver")
	async with blue_app.fastapi_lifespan(blue_app.fastapi):
		blue_transport = httpx.ASGITransport(app=blue_app.fastapi)
		async with httpx.AsyncClient(
			transport=blue_transport, base_url="http://testserver"
		) as client:
			session_response = await client.post(
				"/api/railway-example/session/increment"
			)
			shared_response = await client.post("/api/railway-example/shared/increment")
			meta_response = await client.get("/_pulse/meta")
			session_cookie = {
				blue_app.cookie.name: client.cookies.get(blue_app.cookie.name, "")
			}

	assert session_response.status_code == 200
	assert shared_response.status_code == 200
	assert meta_response.status_code == 200
	assert session_response.json()["counter"] == 1
	assert session_response.json()["first_deployment_id"] == "blue"
	assert shared_response.json()["count"] == 1
	assert shared_response.json()["last_writer"] == "blue"
	assert meta_response.json()["deployment_id"] == "blue"

	monkeypatch.setenv("PULSE_DEPLOYMENT_ID", "green")
	green_app = module.create_app(store=shared_store)
	green_app.setup("http://testserver")
	async with green_app.fastapi_lifespan(green_app.fastapi):
		green_transport = httpx.ASGITransport(app=green_app.fastapi)
		async with httpx.AsyncClient(
			transport=green_transport,
			base_url="http://testserver",
			cookies=session_cookie,
		) as client:
			session_response = await client.get("/api/railway-example/session")
			shared_response = await client.get("/api/railway-example/shared")
			meta_response = await client.get("/_pulse/meta")

	assert session_response.status_code == 200
	assert shared_response.status_code == 200
	assert meta_response.status_code == 200
	assert session_response.json()["counter"] == 1
	assert session_response.json()["first_deployment_id"] == "blue"
	assert shared_response.json()["count"] == 1
	assert shared_response.json()["last_writer"] == "blue"
	assert meta_response.json()["deployment_id"] == "green"
