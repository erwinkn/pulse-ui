import asyncio
import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any, final
from unittest.mock import AsyncMock, Mock

import pulse.cli.reload as reload_mod
import pytest
import uvicorn
from aiohttp import web
from pulse.app import App
from pulse.cli.dev_worker import (
	DEVELOPMENT_GRACEFUL_TIMEOUT,
	WorkerConfig,
	build_server_config,
)
from pulse.cli.reload import (
	GenerationSupervisor,
	GenerationWorker,
	PulseWatchFilter,
	publish_staged_tree,
	wait_for_change_or_exit,
)
from pulse.codegen.codegen import Codegen, CodegenConfig
from pulse.env import ENV_PULSE_CODEGEN_OUTPUT
from pulse.routing import RouteTree
from starlette.types import Receive, Scope, Send
from watchfiles import Change


@final
class FakeProcess:
	def __init__(self) -> None:
		self.alive = True
		self.exitcode = 0
		self.terminated = False
		self.sentinel, self._sentinel_write = os.pipe()

	def is_alive(self) -> bool:
		return self.alive

	def exit(self, code: int) -> None:
		if not self.alive:
			return
		self.alive = False
		self.exitcode = code
		os.close(self._sentinel_write)

	def terminate(self) -> None:
		self.terminated = True
		self.exit(-15)

	def kill(self) -> None:
		self.exit(-9)

	def join(self, timeout: float | None = None) -> None:
		return None


@final
class FakeControl:
	def __init__(self, process: FakeProcess | None = None) -> None:
		self.sent: list[dict[str, Any]] = []
		self.closed = False
		self.process = process

	def send(self, message: dict[str, Any]) -> None:
		self.sent.append(message)
		if message.get("type") == "drain" and self.process is not None:
			self.process.exit(0)

	def close(self) -> None:
		self.closed = True


def fake_worker(generation: int, stage: Path) -> GenerationWorker:
	process = FakeProcess()
	return GenerationWorker(generation, process, FakeControl(process), stage)


async def wait_until(predicate: Any) -> None:
	async def poll() -> None:
		while not predicate():
			await asyncio.sleep(0.01)

	await asyncio.wait_for(poll(), timeout=2)


async def start_http_server(
	handler: Any,
) -> tuple[web.AppRunner, int]:
	app = web.Application()
	app.router.add_route("*", "/{path:.*}", handler)
	runner = web.AppRunner(app)
	await runner.setup()
	sock = socket.socket()
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	sock.bind(("127.0.0.1", 0))
	sock.listen()
	port = sock.getsockname()[1]
	await web.SockSite(runner, sock).start()
	return runner, port


def supervisor_shell(tmp_path: Path) -> GenerationSupervisor:
	supervisor = object.__new__(GenerationSupervisor)
	supervisor.live_path = tmp_path / "web" / "app" / "pulse"
	supervisor.live_path.parent.mkdir(parents=True)
	supervisor.watch_roots = (tmp_path,)
	supervisor.vite_port = None
	supervisor.vite_secret = None
	supervisor.plain = True
	supervisor.desired = 0
	supervisor.changed = asyncio.Event()
	supervisor.filter = PulseWatchFilter((tmp_path,), (supervisor.live_path,))
	supervisor._stage_parent = (  # pyright: ignore[reportPrivateUsage]
		supervisor.live_path.parent / ".pulse.pulse-reload"
	)
	supervisor._stage_parent.mkdir()  # pyright: ignore[reportPrivateUsage]
	supervisor._stage_root = (  # pyright: ignore[reportPrivateUsage]
		supervisor._stage_parent / "run-test"  # pyright: ignore[reportPrivateUsage]
	)
	supervisor._stage_root.mkdir()  # pyright: ignore[reportPrivateUsage]
	supervisor._listen_socket = Mock()  # pyright: ignore[reportPrivateUsage]
	supervisor.active = None
	supervisor.candidate = None
	supervisor._announced_ready = False  # pyright: ignore[reportPrivateUsage]
	return supervisor


@pytest.mark.asyncio
async def test_active_worker_exit_unblocks_supervisor() -> None:
	class ExitedProcess:
		exitcode: int = 130

		def is_alive(self) -> bool:
			return False

	assert await wait_for_change_or_exit(asyncio.Event(), ExitedProcess()) == 130


@pytest.mark.parametrize("plain", [True, False])
@pytest.mark.asyncio
async def test_watch_announces_reload_with_semantic_formatting(
	plain: bool,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	async def one_change(*_args: object, **_kwargs: object):
		yield {(Change.modified, "/app/main.py")}

	monkeypatch.setattr(reload_mod, "awatch", one_change)
	supervisor = object.__new__(GenerationSupervisor)
	supervisor.watch_roots = (Path("/app"),)
	supervisor.filter = PulseWatchFilter((Path("/app"),), ())
	supervisor.desired = 0
	supervisor.changed = asyncio.Event()
	supervisor.plain = plain

	await supervisor._watch()  # pyright: ignore[reportPrivateUsage]

	output = capsys.readouterr().out
	assert supervisor.desired == 1
	assert supervisor.changed.is_set()
	if plain:
		assert output == "Changes detected, reloading...\n"
	else:
		assert output == (
			"\033[1;33mChanges detected,\033[0m \033[1mreloading...\033[0m\n"
		)


def test_watch_filter_accepts_python_and_exact_registered_sources(
	tmp_path: Path,
) -> None:
	app_root = tmp_path / "app"
	generated = app_root / "web" / "app" / "pulse"
	external = tmp_path / "shared" / "theme.css"
	application_root = app_root
	filter_ = PulseWatchFilter(
		(application_root,),
		(generated,),
		{external},
	)

	assert filter_(Change.modified, str(application_root / "main.py"))
	assert filter_(Change.modified, str(external))
	assert not filter_(Change.modified, str(external.with_name("other.css")))
	assert not filter_(Change.modified, str(generated / "route.py"))
	assert not filter_(Change.modified, str(app_root / "web" / "app.tsx"))
	assert not filter_(Change.modified, str(app_root / "node_modules" / "tool.py"))
	assert not filter_(Change.modified, str(app_root / "dist" / "bundle.py"))


def test_new_external_asset_adds_its_parent_watch_root(tmp_path: Path) -> None:
	supervisor = supervisor_shell(tmp_path / "app")
	external = tmp_path / "shared" / "theme.css"

	assert supervisor._add_watch_sources(  # pyright: ignore[reportPrivateUsage]
		[str(external)]
	)
	assert external.parent.resolve() in supervisor.watch_roots
	assert supervisor.filter(Change.modified, str(external))
	assert not supervisor._add_watch_sources(  # pyright: ignore[reportPrivateUsage]
		[str(external)]
	)


def test_publish_staged_tree_replaces_one_complete_generation(tmp_path: Path) -> None:
	live = tmp_path / "web" / "app" / "pulse"
	stage = tmp_path / ".pulse" / "generation-2"
	(live / "old").mkdir(parents=True)
	(live / "old" / "route.tsx").write_text("old")
	(stage / "new").mkdir(parents=True)
	(stage / "new" / "route.tsx").write_text("new")

	published = publish_staged_tree(stage, live)

	assert not (live / "old").exists()
	assert (live / "new" / "route.tsx").read_text() == "new"
	assert not stage.exists()
	assert published == [live / "new" / "route.tsx", live / "old" / "route.tsx"]


def test_publish_staged_tree_preserves_unchanged_files(tmp_path: Path) -> None:
	live = tmp_path / "web" / "app" / "pulse"
	stage = tmp_path / ".pulse" / "run-1" / "generation-2"
	(live / "route.tsx").parent.mkdir(parents=True)
	(live / "route.tsx").write_text("unchanged")
	(stage / "route.tsx").parent.mkdir(parents=True)
	(stage / "route.tsx").write_text("unchanged")
	before = (live / "route.tsx").stat()

	published = publish_staged_tree(stage, live)

	after = (live / "route.tsx").stat()
	assert after.st_ino == before.st_ino
	assert after.st_mtime_ns == before.st_mtime_ns
	assert published == []


def test_cleanup_stale_stages_preserves_recovery_backup(tmp_path: Path) -> None:
	stage_root = tmp_path / ".pulse" / "reload" / "pulse"
	(stage_root / "run-old" / "generation-1").mkdir(parents=True)
	(stage_root / "live-backup-preparing").mkdir()
	(stage_root / "live-backup").mkdir()

	reload_mod._cleanup_stale_stages(  # pyright: ignore[reportPrivateUsage]
		stage_root
	)

	assert not (stage_root / "run-old").exists()
	assert not (stage_root / "live-backup-preparing").exists()
	assert (stage_root / "live-backup").exists()


def test_publish_staged_tree_restores_live_tree_on_replace_failure(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	live = tmp_path / "web" / "app" / "pulse"
	stage = live.parent / ".pulse.pulse-reload" / "run-1" / "generation-2"
	(live / "route.tsx").parent.mkdir(parents=True)
	(live / "route.tsx").write_text("old")
	(stage / "route.tsx").parent.mkdir(parents=True)
	(stage / "route.tsx").write_text("new")
	replace = os.replace
	calls = 0

	def fail_publish(source: Path, destination: Path) -> None:
		nonlocal calls
		calls += 1
		if calls == 2:
			raise OSError("publish failed")
		replace(source, destination)

	monkeypatch.setattr(os, "replace", fail_publish)

	with pytest.raises(OSError, match="publish failed"):
		publish_staged_tree(stage, live)

	assert (live / "route.tsx").read_text() == "old"
	assert (stage / "route.tsx").read_text() == "new"
	assert not (stage.parents[1] / "live-backup").exists()


def test_publish_staged_tree_recovers_backup_left_by_interrupted_publish(
	tmp_path: Path,
) -> None:
	live = tmp_path / "web" / "app" / "pulse"
	stage = live.parent / ".pulse.pulse-reload" / "run-1" / "generation-2"
	backup = stage.parents[1] / "live-backup"
	(backup / "route.tsx").parent.mkdir(parents=True)
	(backup / "route.tsx").write_text("last good")
	(stage / "route.tsx").parent.mkdir(parents=True)
	(stage / "route.tsx").write_text("new")

	publish_staged_tree(stage, live)

	assert (live / "route.tsx").read_text() == "new"
	assert not backup.exists()


def test_codegen_stage_does_not_touch_live_tree(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	web_root = tmp_path / "web"
	live = web_root / "app" / "pulse"
	stage = tmp_path / ".pulse" / "generation-1"
	(live / "keep.ts").parent.mkdir(parents=True)
	(live / "keep.ts").write_text("last good")
	monkeypatch.setenv(ENV_PULSE_CODEGEN_OUTPUT, str(stage))
	codegen = Codegen(
		RouteTree([]),
		CodegenConfig(web_dir=web_root, pulse_dir="pulse", base_dir=tmp_path),
	)

	codegen.generate_all("http://localhost:8000")

	assert (live / "keep.ts").read_text() == "last good"
	assert (stage / "routes.ts").exists()


@pytest.mark.asyncio
async def test_vite_commit_retries_500_and_accepts_idempotent_response() -> None:
	# Response shapes mirror vite.ts exactly: a lost-success retry hits the
	# plugin's equal-generation path, which replies 200 {status: "committed"}.
	attempts = 0

	async def commit(_request: web.Request) -> web.Response:
		nonlocal attempts
		attempts += 1
		if attempts == 1:
			return web.json_response({"status": "error"}, status=500)
		return web.json_response({"status": "committed", "generation": 4})

	runner, port = await start_http_server(commit)
	supervisor = object.__new__(GenerationSupervisor)
	supervisor.vite_port = port
	supervisor.vite_secret = "test-secret"
	try:
		assert await supervisor._retry_vite(  # pyright: ignore[reportPrivateUsage]
			"POST", "/__pulse/commit", 4
		)
	finally:
		await runner.cleanup()

	assert attempts == 2


@pytest.mark.asyncio
async def test_vite_commit_accepts_superseded_generation() -> None:
	# vite.ts answers 409 {status: "stale"} with its latestGeneration, which is
	# strictly greater than the posted one; supersession is success, not failure.
	async def commit(_request: web.Request) -> web.Response:
		return web.json_response({"status": "stale", "generation": 8}, status=409)

	runner, port = await start_http_server(commit)
	supervisor = object.__new__(GenerationSupervisor)
	supervisor.vite_port = port
	supervisor.vite_secret = "test-secret"
	try:
		assert await supervisor._retry_vite(  # pyright: ignore[reportPrivateUsage]
			"POST", "/__pulse/commit", 7
		)
	finally:
		await runner.cleanup()


@pytest.mark.asyncio
async def test_vite_health_without_plugin_fails_fast_with_instructions(
	capsys: pytest.CaptureFixture[str],
) -> None:
	attempts = 0

	async def spa_fallback(_request: web.Request) -> web.Response:
		nonlocal attempts
		attempts += 1
		return web.Response(
			text="<!doctype html><html></html>", content_type="text/html"
		)

	runner, port = await start_http_server(spa_fallback)
	supervisor = object.__new__(GenerationSupervisor)
	supervisor.vite_port = port
	supervisor.vite_secret = "test-secret"
	try:
		# Bounded well below VITE_DEADLINE: a missing plugin must not retry.
		assert not await asyncio.wait_for(
			supervisor._retry_vite(  # pyright: ignore[reportPrivateUsage]
				"GET", "/__pulse/health", 1
			),
			timeout=2,
		)
	finally:
		await runner.cleanup()

	assert attempts == 1
	assert "pulseVitePlugin" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_vite_request_hang_is_bounded(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def hang(_request: web.Request) -> web.Response:
		await asyncio.sleep(0.2)
		return web.json_response({"status": "ready"})

	runner, port = await start_http_server(hang)
	supervisor = object.__new__(GenerationSupervisor)
	supervisor.vite_port = port
	supervisor.vite_secret = "test-secret"
	monkeypatch.setattr(reload_mod, "VITE_DEADLINE", 0.08)
	monkeypatch.setattr(reload_mod, "VITE_REQUEST_TIMEOUT", 0.02)
	monkeypatch.setattr(reload_mod, "VITE_RETRY_DELAY", 0.01)
	try:
		assert not await asyncio.wait_for(
			supervisor._retry_vite(  # pyright: ignore[reportPrivateUsage]
				"GET", "/__pulse/health", 1
			),
			timeout=0.15,
		)
	finally:
		await runner.cleanup()


def test_worker_uvicorn_config_disables_reload_and_bounds_drain(
	tmp_path: Path,
) -> None:
	async def app(scope: Scope, receive: Receive, send: Send) -> None:
		return None

	config = build_server_config(
		app,
		WorkerConfig(
			target="demo:app",
			generation=1,
			stage_path=tmp_path,
			host="127.0.0.1",
			port=8000,
			plain=True,
			verbose=True,
		),
	)

	assert config.reload is False
	assert config.workers == 1
	assert config.timeout_graceful_shutdown == DEVELOPMENT_GRACEFUL_TIMEOUT


@pytest.mark.asyncio
async def test_app_begin_drain_quiesces_proxy_early() -> None:
	app = App()
	proxy = AsyncMock()
	app._proxy = proxy  # pyright: ignore[reportPrivateUsage]

	await app.begin_drain()
	await app.begin_drain()

	assert proxy.close.await_count == 2


@pytest.mark.asyncio
async def test_uvicorn_worker_bounds_unfinished_http_response() -> None:
	request_started = asyncio.Event()
	request_cancelled = asyncio.Event()
	wait_forever = asyncio.Event()

	async def blocked_app(scope: Scope, receive: Receive, send: Send) -> None:
		await send({"type": "http.response.start", "status": 200, "headers": []})
		await send(
			{"type": "http.response.body", "body": b"partial", "more_body": True}
		)
		request_started.set()
		try:
			await wait_forever.wait()
		except asyncio.CancelledError:
			request_cancelled.set()
			raise

	listen_socket = socket.socket()
	listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	listen_socket.bind(("127.0.0.1", 0))
	listen_socket.listen()
	port = listen_socket.getsockname()[1]
	config = uvicorn.Config(
		blocked_app,
		host="127.0.0.1",
		port=port,
		reload=False,
		timeout_graceful_shutdown=DEVELOPMENT_GRACEFUL_TIMEOUT,
		lifespan="off",
		log_config=None,
	)
	server = uvicorn.Server(config)
	server_task = asyncio.create_task(server.serve(sockets=[listen_socket]))
	while not server.started:
		await asyncio.sleep(0.01)
	_reader, writer = await asyncio.open_connection("127.0.0.1", port)
	writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
	await writer.drain()
	await asyncio.wait_for(request_started.wait(), timeout=1)

	server.should_exit = True
	await asyncio.wait_for(server_task, timeout=DEVELOPMENT_GRACEFUL_TIMEOUT + 2)

	assert request_cancelled.is_set()
	writer.close()
	await writer.wait_closed()


@pytest.mark.asyncio
async def test_supervisor_supersedes_rapid_initial_edit_and_commits_generation_two(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	supervisor = supervisor_shell(tmp_path)
	workers: dict[int, GenerationWorker] = {}
	order: list[str] = []

	async def watch(_self: GenerationSupervisor) -> None:
		await asyncio.Event().wait()

	def spawn(self: GenerationSupervisor, generation: int) -> GenerationWorker:
		stage = self._stage_root / f"generation-{generation}"  # pyright: ignore[reportPrivateUsage]
		stage.mkdir()
		(stage / "routes.ts").write_text(f"generation {generation}")
		worker = fake_worker(generation, stage)
		workers[generation] = worker
		order.append(f"spawn:{generation}")
		return worker

	async def wait_for(
		self: GenerationSupervisor,
		worker: GenerationWorker,
		expected: set[str],
	) -> dict[str, Any]:
		if "prepared" in expected:
			if worker.generation == 1:
				self.desired += 1
				self.changed.set()
				return {"type": "stale", "generation": 1}
			order.append("prepared:2")
			return {"type": "prepared", "generation": 2, "sources": []}
		order.append("ready:2")
		return {"type": "ready", "generation": 2}

	async def preflight(_self: GenerationSupervisor, worker: GenerationWorker) -> bool:
		order.append(f"preflight:{worker.generation}")
		return True

	async def notify(
		self: GenerationSupervisor,
		worker: GenerationWorker,
		published_files: list[Path],
	) -> bool:
		order.append(f"commit:{worker.generation}")
		assert (self.live_path / "routes.ts").read_text() == "generation 2"
		assert published_files == [self.live_path / "routes.ts"]
		return True

	monkeypatch.setattr(GenerationSupervisor, "_watch", watch)
	monkeypatch.setattr(GenerationSupervisor, "_spawn", spawn)
	monkeypatch.setattr(GenerationSupervisor, "_wait_for", wait_for)
	monkeypatch.setattr(GenerationSupervisor, "_preflight_vite", preflight)
	monkeypatch.setattr(GenerationSupervisor, "_notify_vite", notify)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: 2 in workers and supervisor.active is workers[2])
	run_task.cancel()
	assert await run_task == 130

	assert order == [
		"spawn:1",
		"spawn:2",
		"prepared:2",
		"preflight:2",
		"ready:2",
		"commit:2",
	]
	assert workers[1].process.terminated
	assert workers[1].control.closed
	assert workers[2].control.sent == [
		{"type": "serve", "generation": 2},
		{"type": "drain", "generation": 2},
	]
	assert capsys.readouterr().out == "Pulse reload ready\n"
	assert not supervisor._stage_parent.exists()  # pyright: ignore[reportPrivateUsage]


def _install_happy_path(
	monkeypatch: pytest.MonkeyPatch,
	workers: dict[int, GenerationWorker],
	*,
	preflight_ok: Callable[[int], bool] = lambda generation: True,
	notify_ok: Callable[[int], bool] = lambda generation: True,
) -> None:
	"""Stub worker phases so every generation prepares, serves, and publishes."""

	async def watch(_self: GenerationSupervisor) -> None:
		await asyncio.Event().wait()

	def spawn(self: GenerationSupervisor, generation: int) -> GenerationWorker:
		stage = self._stage_root / f"generation-{generation}"  # pyright: ignore[reportPrivateUsage]
		stage.mkdir()
		(stage / "routes.ts").write_text(f"generation {generation}")
		worker = fake_worker(generation, stage)
		workers[generation] = worker
		return worker

	async def wait_for(
		_self: GenerationSupervisor,
		worker: GenerationWorker,
		expected: set[str],
	) -> dict[str, Any]:
		kind = "prepared" if "prepared" in expected else "ready"
		message: dict[str, Any] = {"type": kind, "generation": worker.generation}
		if kind == "prepared":
			message["sources"] = []
		return message

	async def preflight(_self: GenerationSupervisor, worker: GenerationWorker) -> bool:
		return preflight_ok(worker.generation)

	async def notify(
		_self: GenerationSupervisor,
		worker: GenerationWorker,
		_published_files: list[Path],
	) -> bool:
		return notify_ok(worker.generation)

	monkeypatch.setattr(GenerationSupervisor, "_watch", watch)
	monkeypatch.setattr(GenerationSupervisor, "_spawn", spawn)
	monkeypatch.setattr(GenerationSupervisor, "_wait_for", wait_for)
	monkeypatch.setattr(GenerationSupervisor, "_preflight_vite", preflight)
	monkeypatch.setattr(GenerationSupervisor, "_notify_vite", notify)


@pytest.mark.asyncio
async def test_supervisor_survives_worker_crash_and_restarts_on_next_change(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	supervisor = supervisor_shell(tmp_path)
	workers: dict[int, GenerationWorker] = {}
	_install_happy_path(monkeypatch, workers)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: 1 in workers and supervisor.active is workers[1])

	workers[1].process.exit(7)
	await wait_until(lambda: supervisor.active is None)
	assert not run_task.done()

	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: 2 in workers and supervisor.active is workers[2])

	run_task.cancel()
	assert await run_task == 130
	output = capsys.readouterr().out
	assert "server exited with code 7" in output


@pytest.mark.asyncio
async def test_supervisor_keeps_serving_when_vite_commit_fails(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	supervisor = supervisor_shell(tmp_path)
	supervisor.vite_port = 5199
	supervisor.vite_secret = "test-secret"
	workers: dict[int, GenerationWorker] = {}
	_install_happy_path(monkeypatch, workers, notify_ok=lambda _generation: False)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: 1 in workers and supervisor.active is workers[1])

	run_task.cancel()
	assert await run_task == 130
	output = capsys.readouterr().out
	assert "Vite did not acknowledge generation 1" in output
	assert "Pulse reload ready" in output


@pytest.mark.asyncio
async def test_supervisor_waits_for_changes_when_vite_preflight_fails(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	supervisor = supervisor_shell(tmp_path)
	workers: dict[int, GenerationWorker] = {}
	preflight_results = {1: False, 2: True}
	_install_happy_path(
		monkeypatch,
		workers,
		preflight_ok=lambda generation: preflight_results[generation],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: workers.get(1) is not None and workers[1].control.closed)
	assert not run_task.done()
	assert supervisor.active is None

	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: 2 in workers and supervisor.active is workers[2])

	run_task.cancel()
	assert await run_task == 130
	output = capsys.readouterr().out
	assert "Vite is not ready" in output


@pytest.mark.asyncio
async def test_supervisor_cleans_candidate_when_cancelled(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	worker: GenerationWorker | None = None
	waiting = asyncio.Event()

	async def watch(_self: GenerationSupervisor) -> None:
		await asyncio.Event().wait()

	def spawn(self: GenerationSupervisor, generation: int) -> GenerationWorker:
		nonlocal worker
		stage = self._stage_root / f"generation-{generation}"  # pyright: ignore[reportPrivateUsage]
		stage.mkdir()
		worker = fake_worker(generation, stage)
		return worker

	async def wait_for(
		_self: GenerationSupervisor,
		_worker: GenerationWorker,
		_expected: set[str],
	) -> dict[str, Any]:
		waiting.set()
		await asyncio.Event().wait()
		raise AssertionError("unreachable")

	monkeypatch.setattr(GenerationSupervisor, "_watch", watch)
	monkeypatch.setattr(GenerationSupervisor, "_spawn", spawn)
	monkeypatch.setattr(GenerationSupervisor, "_wait_for", wait_for)

	run_task = asyncio.create_task(supervisor.run())
	await asyncio.wait_for(waiting.wait(), timeout=1)
	run_task.cancel()

	assert await run_task == 130
	assert worker is not None
	assert worker.process.terminated
	assert worker.control.closed
	assert not supervisor._stage_parent.exists()  # pyright: ignore[reportPrivateUsage]
