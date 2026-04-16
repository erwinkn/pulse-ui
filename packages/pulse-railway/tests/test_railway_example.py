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
import pytest
from pulse_railway import RailwayRedisSessionStore, RailwaySessionStore
from pulse_railway.constants import PULSE_RAILWAY_REDIS_URL

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


def _free_port() -> int:
	with socket.socket() as sock:
		sock.bind(("127.0.0.1", 0))
		sock.listen()
		return int(sock.getsockname()[1])


def _start_redis_server() -> tuple[subprocess.Popen[str], str]:
	if shutil.which("redis-server") is None:
		pytest.skip("redis-server is required for the example smoke test")
	port = _free_port()
	process = subprocess.Popen(
		[
			"redis-server",
			"--save",
			"",
			"--appendonly",
			"no",
			"--bind",
			"127.0.0.1",
			"--port",
			str(port),
		],
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
	)
	deadline = time.time() + 10
	while time.time() < deadline:
		if process.poll() is not None:
			output = "" if process.stdout is None else process.stdout.read()
			raise AssertionError(f"redis-server exited early:\n{output}")
		try:
			with socket.create_connection(("127.0.0.1", port), timeout=0.5):
				return process, f"redis://127.0.0.1:{port}/0"
		except OSError:
			time.sleep(0.1)
	process.terminate()
	raise AssertionError("timed out waiting for redis-server")


def test_railway_session_store_uses_redis_when_env_present() -> None:
	module = load_example_module()
	store = module.RailwaySessionStore(
		env={PULSE_RAILWAY_REDIS_URL: "redis://shared:6379/0"}
	)

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
	class _FakeRedisClient:
		def __init__(self) -> None:
			self.data: dict[str, str] = {}

		async def get(self, key: str) -> str | None:
			return self.data.get(key)

		async def set(self, key: str, value: str) -> bool:
			self.data[key] = value
			return True

		async def delete(self, key: str) -> None:
			self.data.pop(key, None)

		async def aclose(self) -> None:
			return None

	module = load_example_module()
	shared_session_store = RailwaySessionStore(
		client=_FakeRedisClient(),
		prefix=module.SESSION_PREFIX,
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
	assert session_response.json()["behavior_version"] == "concurrent-v2"
	assert session_response.json()["first_deployment_id"] == "blue"
	assert session_response.json()["redis_target"] == "unconfigured"
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
	assert session_response.json()["behavior_version"] == "concurrent-v2"
	assert session_response.json()["first_deployment_id"] == "blue"
	assert session_response.json()["redis_target"] == "unconfigured"
	assert meta_response.json()["deployment_id"] == "green"


def test_railway_example_prod_smoke() -> None:
	if shutil.which("bun") is None or shutil.which("uv") is None:
		pytest.skip("bun and uv are required for the prod smoke test")

	redis_process, redis_url = _start_redis_server()
	port = _free_port()
	server_address = f"https://127.0.0.1:{port}"
	internal_server_address = f"http://127.0.0.1:{port}"
	base_env = os.environ.copy()
	base_env["PULSE_SERVER_ADDRESS"] = server_address
	base_env["PULSE_INTERNAL_SERVER_ADDRESS"] = internal_server_address
	base_env["PULSE_DEPLOYMENT_ID"] = "smoke"
	base_env[PULSE_RAILWAY_REDIS_URL] = redis_url

	try:
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
			assert "Pulse Railway Concurrent Deploy Smoke Test" in response.text
			assert "Behavior version: concurrent-v2" in response.text
		finally:
			process.terminate()
			try:
				process.wait(timeout=10)
			except subprocess.TimeoutExpired:
				process.kill()
	finally:
		redis_process.terminate()
		try:
			redis_process.wait(timeout=10)
		except subprocess.TimeoutExpired:
			redis_process.kill()
