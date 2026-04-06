from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import pulse as ps
from pulse_railway import RailwayPlugin

SESSION_PREFIX = "pulse:railway-example:session"
USER_COUNTER_KEY = "pulse:railway-example:user-code:counter"
USER_LAST_WRITE_KEY = "pulse:railway-example:user-code:last-write"


def deployment_id(env: Mapping[str, str] | None = None) -> str:
	values = os.environ if env is None else env
	return values.get("PULSE_DEPLOYMENT_ID") or "local"


def now_iso() -> str:
	return datetime.now(UTC).replace(microsecond=0).isoformat()


def resolve_store(env: Mapping[str, str] | None = None) -> ps.KVStore:
	values = os.environ if env is None else env
	kind = values.get("PULSE_KV_KIND")
	url = values.get("PULSE_KV_URL") or values.get("PULSE_REDIS_URL")
	path = values.get("PULSE_KV_PATH")
	if kind not in {None, "redis", "sqlite"}:
		raise RuntimeError(f"Unsupported PULSE_KV_KIND: {kind}")
	if kind == "redis":
		if url is None:
			raise RuntimeError("PULSE_KV_URL is required when PULSE_KV_KIND=redis")
		return ps.RedisKVStore.from_url(url)
	if kind == "sqlite":
		if path is None:
			raise RuntimeError("PULSE_KV_PATH is required when PULSE_KV_KIND=sqlite")
		return ps.SQLiteKVStore(path)
	if url is not None:
		return ps.RedisKVStore.from_url(url)
	if path is not None:
		return ps.SQLiteKVStore(path)
	return ps.SQLiteKVStore(".pulse/railway-example.sqlite3")


def store_snapshot(store: ps.KVStore | None = None) -> dict[str, Any]:
	current_store = ps.store() if store is None else store
	config = current_store.config()
	if config is None:
		return {
			"kind": "memory",
			"shareable": False,
			"target": "in-process",
		}
	target = config.url or config.path or "configured"
	return {
		"kind": config.kind,
		"shareable": config.shareable,
		"target": target,
	}


def session_snapshot() -> dict[str, Any]:
	ctx_session = ps.PulseContext.get().session
	if ctx_session is None:
		raise RuntimeError("Could not resolve current user session")
	session = ps.session()
	return {
		"sid": ctx_session.sid,
		"counter": int(session.get("counter") or 0),
		"started_at": session.get("started_at") or "",
		"last_updated_at": session.get("last_updated_at") or "",
		"first_deployment_id": session.get("first_deployment_id") or "",
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


async def shared_snapshot(store: ps.KVStore | None = None) -> dict[str, Any]:
	current_store = ps.store() if store is None else store
	count = int(await current_store.get(USER_COUNTER_KEY) or "0")
	last_write_raw = await current_store.get(USER_LAST_WRITE_KEY)
	last_write: dict[str, Any] = {}
	if last_write_raw is not None:
		last_write = cast(dict[str, Any], json.loads(last_write_raw))
	return {
		"count": count,
		"last_writer": last_write.get("deployment_id") or "",
		"updated_at": last_write.get("updated_at") or "",
		"store": store_snapshot(current_store),
	}


async def increment_shared_counter(store: ps.KVStore | None = None) -> dict[str, Any]:
	current_store = ps.store() if store is None else store
	count = int(await current_store.get(USER_COUNTER_KEY) or "0") + 1
	await current_store.set(USER_COUNTER_KEY, str(count))
	await current_store.set(
		USER_LAST_WRITE_KEY,
		json.dumps(
			{
				"deployment_id": deployment_id(),
				"updated_at": now_iso(),
			},
			separators=(",", ":"),
		),
	)
	return await shared_snapshot(current_store)


class SharedStoreState(ps.State):
	count: int = 0
	last_writer: str = ""
	updated_at: str = ""

	async def refresh(self) -> None:
		snapshot = await shared_snapshot()
		self.count = snapshot["count"]
		self.last_writer = str(snapshot["last_writer"])
		self.updated_at = str(snapshot["updated_at"])

	async def increment(self) -> None:
		snapshot = await increment_shared_counter()
		self.count = snapshot["count"]
		self.last_writer = str(snapshot["last_writer"])
		self.updated_at = str(snapshot["updated_at"])


@ps.component
def home():
	with ps.init():
		shared = SharedStoreState()

	store_info = store_snapshot()
	session_info = session_snapshot()

	return ps.div(
		ps.div(
			ps.span(
				f"Serving deployment: {deployment_id()}",
				className="rounded-full bg-slate-900 px-3 py-1 text-sm font-semibold text-white",
			),
			ps.h1(
				"Pulse Railway Shared Redis Smoke Test",
				className="mt-6 text-4xl font-black tracking-tight text-slate-950",
			),
			ps.p(
				"One example app. Three checks: pulse-railway deployment tracking, server-side sessions, and direct app KV reads/writes.",
				className="mt-4 max-w-3xl text-lg text-slate-600",
			),
			className="mx-auto max-w-5xl px-6 pt-12",
		),
		ps.div(
			ps.section(
				ps.h2("Store", className="text-2xl font-bold text-slate-950"),
				ps.p(
					"Expose Redis through app.store so pulse-railway can reuse it across router, janitor, and backend services.",
					className="mt-2 text-sm text-slate-600",
				),
				ps.pre(
					json.dumps(store_info, indent=2, sort_keys=True),
					className="mt-4 overflow-x-auto rounded-2xl bg-slate-950 p-4 text-sm text-slate-100",
				),
				className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm",
			),
			ps.section(
				ps.h2("Session", className="text-2xl font-bold text-slate-950"),
				ps.p(
					"Backed by ps.SessionStore(prefix=...) and the same app store.",
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
			ps.section(
				ps.h2("User Code", className="text-2xl font-bold text-slate-950"),
				ps.p(
					"These buttons call ps.store() directly from Pulse handlers. Deploy again and confirm the values survive.",
					className="mt-2 text-sm text-slate-600",
				),
				ps.div(
					ps.button(
						"Refresh shared counter",
						onClick=shared.refresh,
						className="btn-secondary",
					),
					ps.button(
						"Increment shared counter",
						onClick=shared.increment,
						className="btn-primary ml-3",
					),
					className="mt-4",
				),
				ps.pre(
					json.dumps(
						{
							"count": shared.count,
							"last_writer": shared.last_writer,
							"updated_at": shared.updated_at,
						},
						indent=2,
						sort_keys=True,
					),
					className="mt-4 overflow-x-auto rounded-2xl bg-slate-950 p-4 text-sm text-slate-100",
				),
				className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm",
			),
			className="mx-auto mt-8 grid max-w-5xl gap-6 px-6 pb-6 lg:grid-cols-3",
		),
		ps.section(
			ps.h2("HTTP Probes", className="text-2xl font-bold text-slate-950"),
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
						"GET  /api/railway-example/shared",
						"POST /api/railway-example/shared/increment",
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
			"deployment_id": deployment_id(),
			"session": session_snapshot(),
			"shared": await shared_snapshot(),
			"store": store_snapshot(),
		}

	@app.fastapi.get("/api/railway-example/session")
	def railway_example_session():  # pyright: ignore[reportUnusedFunction]
		return session_snapshot()

	@app.fastapi.post("/api/railway-example/session/increment")
	def railway_example_session_increment():  # pyright: ignore[reportUnusedFunction]
		return increment_session_counter()

	@app.fastapi.get("/api/railway-example/shared")
	async def railway_example_shared():  # pyright: ignore[reportUnusedFunction]
		return await shared_snapshot()

	@app.fastapi.post("/api/railway-example/shared/increment")
	async def railway_example_shared_increment():  # pyright: ignore[reportUnusedFunction]
		return await increment_shared_counter()


def create_app(*, store: ps.KVStore | None = None) -> ps.App:
	app = ps.App(
		routes=[ps.Route("/", home)],
		plugins=[RailwayPlugin()],
		store=resolve_store() if store is None else store,
		session_store=ps.SessionStore(prefix=SESSION_PREFIX),
		server_address=os.environ.get("PULSE_SERVER_ADDRESS"),
		internal_server_address=os.environ.get("PULSE_INTERNAL_SERVER_ADDRESS"),
	)
	register_probe_routes(app)
	return app


app = create_app()
