from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pulse as ps
import pytest
from pulse_railway import RailwayRedisSessionStore
from pulse_railway.constants import PULSE_REDIS_URL

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


def test_railway_session_store_uses_redis_when_env_present() -> None:
	module = load_example_module()
	store = module.railway_session_store(env={PULSE_REDIS_URL: "redis://shared:6379/0"})

	assert isinstance(store, RailwayRedisSessionStore)
	assert store.configured_url() == "redis://shared:6379/0"


def test_create_app_uses_railway_session_store_by_default() -> None:
	module = load_example_module()
	app = module.create_app()

	assert isinstance(app.session_store, RailwayRedisSessionStore)


@pytest.mark.asyncio
async def test_example_preserves_session_across_app_instances(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	module = load_example_module()
	shared_session_store = module.railway_session_store(
		fallback=ps.InMemorySessionStore(),
	)

	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	monkeypatch.setenv("PULSE_DEPLOYMENT_ID", "blue")
	blue_app = module.create_app(session_store=shared_session_store)
	blue_app.setup("http://testserver")
	async with blue_app.fastapi_lifespan(blue_app.fastapi):
		blue_transport = httpx.ASGITransport(app=blue_app.fastapi)
		async with httpx.AsyncClient(
			transport=blue_transport, base_url="http://testserver"
		) as client:
			session_response = await client.post(
				"/api/railway-example/session/increment"
			)
			meta_response = await client.get("/_pulse/meta")
			session_cookie = {
				blue_app.cookie.name: client.cookies.get(blue_app.cookie.name, "")
			}

	assert session_response.status_code == 200
	assert meta_response.status_code == 200
	assert session_response.json()["counter"] == 1
	assert session_response.json()["first_deployment_id"] == "blue"
	assert session_response.json()["redis_target"] == "in-memory fallback"
	assert meta_response.json()["deployment_id"] == "blue"

	monkeypatch.setenv("PULSE_DEPLOYMENT_ID", "green")
	green_app = module.create_app(session_store=shared_session_store)
	green_app.setup("http://testserver")
	async with green_app.fastapi_lifespan(green_app.fastapi):
		green_transport = httpx.ASGITransport(app=green_app.fastapi)
		async with httpx.AsyncClient(
			transport=green_transport,
			base_url="http://testserver",
			cookies=session_cookie,
		) as client:
			session_response = await client.get("/api/railway-example/session")
			meta_response = await client.get("/_pulse/meta")

	assert session_response.status_code == 200
	assert meta_response.status_code == 200
	assert session_response.json()["counter"] == 1
	assert session_response.json()["first_deployment_id"] == "blue"
	assert session_response.json()["redis_target"] == "in-memory fallback"
	assert meta_response.json()["deployment_id"] == "green"


def _free_port() -> int:
	with socket.socket() as sock:
		sock.bind(("127.0.0.1", 0))
		sock.listen()
		return int(sock.getsockname()[1])


def test_railway_example_prod_smoke() -> None:
	if shutil.which("bun") is None or shutil.which("uv") is None:
		pytest.skip("bun and uv are required for the prod smoke test")

	port = _free_port()
	server_address = f"https://127.0.0.1:{port}"
	internal_server_address = f"http://127.0.0.1:{port}"
	base_env = os.environ.copy()
	base_env["PULSE_SERVER_ADDRESS"] = server_address
	base_env["PULSE_INTERNAL_SERVER_ADDRESS"] = internal_server_address
	base_env["PULSE_DEPLOYMENT_ID"] = "smoke"

	subprocess.run(
		["uv", "run", "pulse", "generate", "examples/railway/main.py", "--ci"],
		cwd=ROOT,
		check=True,
		env=base_env,
	)
	subprocess.run(
		["bun", "install", "--frozen-lockfile"],
		cwd=ROOT,
		check=True,
	)
	subprocess.run(
		["bun", "run", "build"],
		cwd=ROOT / "examples/railway/web",
		check=True,
	)

	env = dict(base_env)
	env.pop("NODE_ENV", None)
	process = subprocess.Popen(
		[
			"uv",
			"run",
			"pulse",
			"run",
			"examples/railway/main.py",
			"--prod",
			"--address",
			"127.0.0.1",
			"--port",
			str(port),
			"--no-find-port",
		],
		cwd=ROOT,
		env=env,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
	)
	try:
		deadline = time.time() + 30
		response: httpx.Response | None = None
		while time.time() < deadline:
			if process.poll() is not None:
				output = "" if process.stdout is None else process.stdout.read()
				raise AssertionError(f"prod smoke process exited early:\n{output}")
			try:
				response = httpx.get(internal_server_address, timeout=1.0)
			except httpx.HTTPError:
				time.sleep(0.5)
				continue
			if response.status_code == 200:
				break
			time.sleep(0.5)
		else:
			raise AssertionError("timed out waiting for prod smoke server")

		assert response is not None
		assert response.status_code == 200
		assert "Pulse Railway Session Store Smoke Test" in response.text
	finally:
		process.terminate()
		try:
			process.wait(timeout=10)
		except subprocess.TimeoutExpired:
			process.kill()
