from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pulse as ps
from pulse_railway import RailwayPlugin, railway_session_store
from pulse_railway.constants import PULSE_DEPLOYMENT_ID, PULSE_REDIS_URL

SESSION_PREFIX = "pulse:railway-example:session"
BEHAVIOR_VERSION = "concurrent-v2"


def deployment_id(env: Mapping[str, str] | None = None) -> str:
	values = os.environ if env is None else env
	return values.get(PULSE_DEPLOYMENT_ID) or "local"


def now_iso() -> str:
	return datetime.now(UTC).replace(microsecond=0).isoformat()


def redis_target(env: Mapping[str, str] | None = None) -> str:
	values = os.environ if env is None else env
	return values.get(PULSE_REDIS_URL) or "in-memory fallback"


def session_snapshot() -> dict[str, Any]:
	ctx_session = ps.PulseContext.get().session
	if ctx_session is None:
		raise RuntimeError("Could not resolve current user session")
	session = ps.session()
	return {
		"sid": ctx_session.sid,
		"counter": int(session.get("counter") or 0),
		"behavior_version": BEHAVIOR_VERSION,
		"started_at": session.get("started_at") or "",
		"last_updated_at": session.get("last_updated_at") or "",
		"first_deployment_id": session.get("first_deployment_id") or "",
		"redis_target": redis_target(),
	}


def increment_session_counter() -> dict[str, Any]:
	session = ps.session()
	session["started_at"] = session.get("started_at") or now_iso()
	session["first_deployment_id"] = (
		session.get("first_deployment_id") or deployment_id()
	)
	session["counter"] = int(session.get("counter") or 0) + 1
	session["last_updated_at"] = now_iso()
	return session_snapshot()


@ps.component
def home():
	session_info = session_snapshot()

	return ps.div(
		ps.div(
			ps.span(
				f"Serving deployment: {deployment_id()}",
				className="rounded-full bg-slate-900 px-3 py-1 text-sm font-semibold text-white",
			),
			ps.span(
				f"Behavior version: {BEHAVIOR_VERSION}",
				className="ml-3 rounded-full bg-emerald-600 px-3 py-1 text-sm font-semibold text-white",
			),
			ps.h1(
				"Pulse Railway Concurrent Deploy Smoke Test",
				className="mt-6 text-4xl font-black tracking-tight text-slate-950",
			),
			ps.p(
				"One example app. Three checks: deployment affinity, concurrent old/new deployments, and Redis-backed server-side sessions.",
				className="mt-4 max-w-3xl text-lg text-slate-600",
			),
			className="mx-auto max-w-5xl px-6 pt-12",
		),
		ps.div(
			ps.section(
				ps.h2("Session store", className="text-2xl font-bold text-slate-950"),
				ps.p(
					"The app opts into pulse_railway.railway_session_store(). In this example it falls back to in-memory locally, but Railway injects the shared Redis URL on deploy.",
					className="mt-2 text-sm text-slate-600",
				),
				ps.div(
					ps.button(
						"Increment session counter",
						onClick=increment_session_counter,
						className="btn-primary",
					),
					className="mt-4",
				),
				ps.pre(
					json.dumps(session_info, indent=2, sort_keys=True),
					className="mt-4 overflow-x-auto rounded-2xl bg-slate-950 p-4 text-sm text-slate-100",
				),
				className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm",
			),
			className="mx-auto mt-8 max-w-5xl px-6 pb-6",
		),
		ps.section(
			ps.h2("HTTP probes", className="text-2xl font-bold text-slate-950"),
			ps.p(
				"Useful for smoke tests and deploy verification without opening DevTools.",
				className="mt-2 text-sm text-slate-600",
			),
			ps.pre(
				"\n".join(
					[
						"GET  /_pulse/meta",
						"GET  /api/railway-example/meta",
						"GET  /api/railway-example/session",
						"POST /api/railway-example/session/increment",
					]
				),
				className="mt-4 overflow-x-auto rounded-2xl bg-amber-100 p-4 text-sm text-amber-950",
			),
			className="mx-auto mb-12 max-w-5xl rounded-3xl border border-amber-200 bg-amber-50 px-6 py-6",
		),
		className="min-h-screen bg-[linear-gradient(180deg,#f8fafc_0%,#e2e8f0_100%)]",
	)


def register_probe_routes(app: ps.App) -> None:
	@app.fastapi.get("/api/railway-example/meta")
	async def railway_example_meta():  # pyright: ignore[reportUnusedFunction]
		return {
			"behavior_version": BEHAVIOR_VERSION,
			"deployment_id": deployment_id(),
			"session": session_snapshot(),
		}

	@app.fastapi.get("/api/railway-example/session")
	def railway_example_session():  # pyright: ignore[reportUnusedFunction]
		return session_snapshot()

	@app.fastapi.post("/api/railway-example/session/increment")
	def railway_example_session_increment():  # pyright: ignore[reportUnusedFunction]
		return increment_session_counter()


def create_app(
	*,
	session_store: ps.SessionStore | None = None,
) -> ps.App:
	app = ps.App(
		routes=[ps.Route("/", home)],
		plugins=[
			RailwayPlugin(
				project_id=os.environ.get("RAILWAY_PROJECT_ID"),
				environment_id=os.environ.get("RAILWAY_ENVIRONMENT_ID"),
			)
		],
		session_store=session_store
		or railway_session_store(
			prefix=SESSION_PREFIX,
			fallback=ps.InMemorySessionStore(),
		),
		server_address=os.environ.get("PULSE_SERVER_ADDRESS"),
		internal_server_address=os.environ.get("PULSE_INTERNAL_SERVER_ADDRESS"),
	)
	register_probe_routes(app)
	return app


app = create_app()
