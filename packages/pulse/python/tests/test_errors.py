import re
from pathlib import Path
from typing import Any, cast, get_args

import pulse as ps
import pytest
from fastapi.testclient import TestClient
from pulse.errors import ErrorCode
from pulse.user_session import InMemorySessionStore


@ps.component
def _test_page():
	return ps.div("ok")


class _DummyPulseRoute:
	def unique_path(self) -> str:
		return "/x"


class _DummyRouteContext:
	pulse_route: _DummyPulseRoute = _DummyPulseRoute()


class _DummyRender:
	id: str = "render-test"

	def __init__(self) -> None:
		self.sent: list[dict[str, Any]] = []

	def send(self, message: dict[str, Any]) -> None:
		self.sent.append(message)


def _build_api_app():
	app = ps.App(
		routes=[ps.Route("a", _test_page)],
		mode="subdomains",
		session_store=InMemorySessionStore(),
	)
	render_box: dict[str, ps.RenderSession] = {}

	@app.fastapi.get("/boom-with-route")
	async def boom_with_route():  # pyright: ignore[reportUnusedFunction]
		render = render_box["render"]
		mount = render.get_route_mount("/a")
		with ps.PulseContext.update(render=render, route=mount.route):
			raise RuntimeError("boom-with-route")

	@app.fastapi.get("/boom-without-route")
	async def boom_without_route():  # pyright: ignore[reportUnusedFunction]
		raise RuntimeError("boom-without-route")

	app.setup("http://localhost:8000")
	client = TestClient(app.asgi, raise_server_exceptions=False)
	health = client.get(f"{app.api_prefix}/health")
	assert health.status_code == 200
	sid = next(iter(app.user_sessions.keys()))
	client.cookies.set(app.cookie.name, sid)
	session = app.user_sessions[sid]
	render = app.create_render("render-api", session)
	sent: list[dict[str, Any]] = []
	render.connect(cast(Any, sent.append))
	with ps.PulseContext.update(session=session, render=render):
		render.prerender(["/a"])
		render.attach(
			"/a",
			{
				"pathname": "/a",
				"hash": "",
				"query": "",
				"queryParams": {},
				"pathParams": {},
				"catchall": [],
			},
		)
	render_box["render"] = render
	return app, client, render, sent


def test_errors_report_routes_to_render_with_route() -> None:
	app = ps.App()
	render = _DummyRender()
	details = {"callback": "x"}
	with ps.PulseContext(
		app=app,
		render=render,  # pyright: ignore[reportArgumentType]
		route=_DummyRouteContext(),  # pyright: ignore[reportArgumentType]
	):
		ps.PulseContext.get().errors.report(
			RuntimeError("boom"),
			code="callback",
			details=details,
		)

	assert details == {"callback": "x"}
	assert len(render.sent) == 1
	msg = render.sent[0]
	assert msg["type"] == "server_error"
	assert msg["path"] == "/x"
	assert msg["error"]["code"] == "callback"
	assert msg["error"]["details"]["callback"] == "x"


def test_pulse_context_update_can_clear_route() -> None:
	app = ps.App()
	with ps.PulseContext(
		app=app,
		route=_DummyRouteContext(),  # pyright: ignore[reportArgumentType]
	):
		current = ps.PulseContext.get()
		next_ctx = ps.PulseContext.update(route=None)

	assert next_ctx.route is None
	assert next_ctx.errors is not current.errors


def test_error_code_literals_match_ts_union() -> None:
	ts_file = Path("packages/pulse/js/src/messages.ts")
	match = re.search(
		r"export type ErrorCode\s*=\s*(.*?);",
		ts_file.read_text(),
		flags=re.DOTALL,
	)
	assert match is not None
	ts_codes = set(re.findall(r'"([^"]+)"', match.group(1)))
	py_codes = set(get_args(ErrorCode))
	assert py_codes == ts_codes


def test_runtime_has_no_loop_exception_handler_calls() -> None:
	root = Path("packages/pulse/python/src/pulse")
	for py_file in root.rglob("*.py"):
		text = py_file.read_text()
		assert "call_exception_handler(" not in text, str(py_file)


@pytest.mark.asyncio
async def test_api_error_with_render_and_route_reports_to_client_route() -> None:
	app, client, render, sent = _build_api_app()
	try:
		resp = client.get(
			"/boom-with-route",
			headers={"x-pulse-render-id": render.id},
		)
		assert resp.status_code == 500
		server_errors = [m for m in sent if m.get("type") == "server_error"]
		assert len(server_errors) == 1
		assert server_errors[0]["path"] == "/a"
		assert server_errors[0]["error"]["code"] == "api"
	finally:
		client.close()
		await app.close()


@pytest.mark.asyncio
async def test_api_error_with_render_but_no_route_logs_only() -> None:
	app, client, render, sent = _build_api_app()
	try:
		resp = client.get(
			"/boom-without-route",
			headers={"x-pulse-render-id": render.id},
		)
		assert resp.status_code == 500
		assert [m for m in sent if m.get("type") == "server_error"] == []
	finally:
		client.close()
		await app.close()


@pytest.mark.asyncio
async def test_api_error_without_render_logs_only() -> None:
	app, client, _render, sent = _build_api_app()
	try:
		resp = client.get("/boom-without-route")
		assert resp.status_code == 500
		assert [m for m in sent if m.get("type") == "server_error"] == []
	finally:
		client.close()
		await app.close()
