import asyncio
import io
import os
import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast, final

import pulse.cli.reload as reload_mod
import pytest
import uvicorn
from aiohttp import ClientSession
from pulse.cli.dev_worker import (
	DEVELOPMENT_GRACEFUL_TIMEOUT,
	WorkerConfig,
	_watch_supervisor,  # pyright: ignore[reportPrivateUsage]
	build_server_config,
)
from pulse.cli.models import CommandSpec
from pulse.cli.processes import ManagedProcess
from pulse.cli.reload import DevSupervisor, PulseWatchFilter
from pulse.env import (
	ENV_PULSE_BACKEND_INSTANCE,
	ENV_PULSE_BACKEND_LIFECYCLE_SECRET,
	ENV_PULSE_BACKEND_LIFECYCLE_URL,
	ENV_PULSE_REACT_SERVER_ADDRESS,
	ENV_PULSE_VITE_INSTANCE,
	ENV_PULSE_VITE_LIFECYCLE_SECRET,
	ENV_PULSE_VITE_LIFECYCLE_URL,
)
from starlette.types import Receive, Scope, Send
from watchfiles import Change


@final
class FakeProcess:
	def __init__(self, name: str, events: list[str], *, hangs: bool = False) -> None:
		self.name = name
		self.events = events
		self.hangs = hangs
		self.alive = True
		self.code: int | None = None
		self.on_send: Callable[[], None] | None = None
		self.on_exit: Callable[[int], None] | None = None

	@property
	def returncode(self) -> int | None:
		return self.code

	def is_alive(self) -> bool:
		return self.alive

	def request_stop(self) -> None:
		self.events.append(f"{self.name}:stop")
		if not self.hangs:
			self.exit(0)

	def send_line(self, line: str) -> None:
		self.events.append(f"{self.name}:{line}")
		if self.on_send is not None:
			self.on_send()

	def kill_tree(self) -> None:
		self.events.append(f"{self.name}:kill")
		self.exit(-9)

	def exit(self, code: int) -> None:
		if not self.alive:
			return
		self.alive = False
		self.code = code
		self.events.append(f"{self.name}:exit")
		if self.on_exit is not None:
			self.on_exit(code)

	def close(self) -> None:
		self.events.append(f"{self.name}:close")


def command(name: str, tmp_path: Path, ready_pattern: str | None = None) -> CommandSpec:
	return CommandSpec(
		name=name,
		args=[name],
		cwd=tmp_path,
		env={},
		ready_pattern=ready_pattern,
	)


def supervisor_shell(tmp_path: Path) -> DevSupervisor:
	return DevSupervisor(
		backend=command("server", tmp_path),
		web=command("web", tmp_path, "web ready"),
		watch_roots=(tmp_path,),
		ignored_roots=(tmp_path / "web" / "app" / "pulse",),
		registered_sources=set(),
		tag_mode="plain",
	)


async def wait_until(predicate: Any) -> None:
	async with asyncio.timeout(2):
		while not predicate():
			await asyncio.sleep(0.01)


def install_process_script(
	monkeypatch: pytest.MonkeyPatch,
	events: list[str],
	plans: list[tuple[str, str]],
) -> list[FakeProcess]:
	processes: list[FakeProcess] = []

	async def report_vite(spec: CommandSpec, name: str, *, listening: bool) -> None:
		url = spec.env[ENV_PULSE_VITE_LIFECYCLE_URL]
		headers = {
			"Authorization": "Bearer " + spec.env[ENV_PULSE_VITE_LIFECYCLE_SECRET]
		}
		async with ClientSession() as session:
			response = await session.post(
				url,
				headers=headers,
				json={
					"event": "configured",
					"instance": spec.env[ENV_PULSE_VITE_INSTANCE],
					"sequence": 1,
				},
			)
			assert response.status == 204
			events.append(f"{name}:configured")
			if not listening:
				return
			response = await session.post(
				url,
				headers=headers,
				json={
					"event": "listening",
					"instance": spec.env[ENV_PULSE_VITE_INSTANCE],
					"sequence": 2,
					"port": 5173,
				},
			)
			assert response.status == 204
			events.append(f"{name}:ready")

	def start(
		_cls: type[ManagedProcess],
		spec: CommandSpec,
		on_output: Callable[[str], None],
		on_exit: Callable[[int], None],
	) -> FakeProcess:
		expected_name, outcome = plans.pop(0)
		assert spec.name == expected_name
		instance = 1 + sum(process.name.startswith(spec.name) for process in processes)
		name = f"{spec.name}{instance}"
		process = FakeProcess(name, events, hangs=outcome == "hang")
		process.on_exit = on_exit
		processes.append(process)
		events.append(f"{name}:start")

		async def report_backend(event: str, sources: list[str] | None = None) -> None:
			body: dict[str, object] = {
				"event": event,
				"instance": spec.env[ENV_PULSE_BACKEND_INSTANCE],
			}
			if sources is not None:
				body["sources"] = sources
			if event == "ready":
				body["port"] = 9000 + instance
			async with ClientSession() as session:
				response = await session.post(
					spec.env[ENV_PULSE_BACKEND_LIFECYCLE_URL],
					headers={
						"Authorization": "Bearer "
						+ spec.env[ENV_PULSE_BACKEND_LIFECYCLE_SECRET]
					},
					json=body,
				)
				assert response.status == 204
				events.append(f"{name}:{event}")

		if outcome in ("ready", "serve_fail", "serve_broken_pipe"):
			if spec.name == "server":
				asyncio.create_task(report_backend("prepared", []))

				def mark_ready() -> None:
					if outcome == "serve_fail":
						process.exit(3)
					elif outcome == "serve_broken_pipe":
						process.exit(1)
						raise BrokenPipeError
					else:
						asyncio.create_task(report_backend("ready"))

				process.on_send = mark_ready
			else:
				asyncio.create_task(report_vite(spec, name, listening=True))
		elif outcome == "configured" and spec.name == "web":
			asyncio.create_task(report_vite(spec, name, listening=False))
		elif outcome == "malformed":

			async def report_malformed() -> None:
				async with ClientSession() as session:
					response = await session.post(
						spec.env[ENV_PULSE_BACKEND_LIFECYCLE_URL],
						headers={
							"Authorization": "Bearer "
							+ spec.env[ENV_PULSE_BACKEND_LIFECYCLE_SECRET]
						},
						json={
							"event": "prepared",
							"instance": spec.env[ENV_PULSE_BACKEND_INSTANCE],
							"sources": "invalid",
						},
					)
					assert response.status == 400
					events.append(f"{name}:malformed")

			asyncio.create_task(report_malformed())
		elif outcome == "fail":
			process.exit(1)
		return process

	async def watch(_self: DevSupervisor) -> None:
		await asyncio.Event().wait()

	monkeypatch.setattr(ManagedProcess, "start", classmethod(start))
	monkeypatch.setattr(DevSupervisor, "_watch", watch)
	return processes


@pytest.mark.parametrize("plain", [True, False])
@pytest.mark.asyncio
async def test_watch_announces_reload_with_semantic_formatting(
	plain: bool,
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	async def one_change(*_args: object, **_kwargs: object):
		yield {(Change.modified, str(tmp_path / "main.py"))}

	monkeypatch.setattr(reload_mod, "awatch", one_change)
	supervisor = supervisor_shell(tmp_path)
	supervisor.tag_mode = "plain" if plain else "colored"

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
	filter_ = PulseWatchFilter((app_root,), (generated,), {external})

	assert filter_(Change.modified, str(app_root / "main.py"))
	assert filter_(Change.modified, str(external))
	assert not filter_(Change.modified, str(external.with_name("other.css")))
	assert not filter_(Change.modified, str(generated / "route.py"))
	assert not filter_(Change.modified, str(app_root / "web" / "app.tsx"))
	assert not filter_(Change.modified, str(app_root / "node_modules" / "tool.py"))


def test_watch_filter_ignores_junk_names_only_below_watch_roots(
	tmp_path: Path,
) -> None:
	app_root = tmp_path / "build" / "myapp"
	filter_ = PulseWatchFilter((app_root,), (), set())

	# An ancestor named "build" must not suppress reloads for the app inside it.
	assert filter_(Change.modified, str(app_root / "main.py"))
	assert not filter_(Change.modified, str(app_root / "build" / "artifact.py"))
	assert not filter_(Change.modified, str(app_root / "venv" / "lib" / "pkg.py"))


def test_new_external_asset_adds_its_parent_watch_root(tmp_path: Path) -> None:
	app_root = tmp_path / "app"
	external = tmp_path / "shared" / "theme.css"
	supervisor = DevSupervisor(
		backend=command("server", tmp_path),
		web=None,
		watch_roots=(app_root,),
		ignored_roots=(),
		registered_sources={external},
		tag_mode="plain",
	)

	assert external.parent.resolve() in supervisor.watch_roots
	assert supervisor.filter(Change.modified, str(external))
	assert not supervisor._add_watch_sources([str(external)])  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_reload_starts_new_stack_before_stopping_old(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	ready_count = 0

	def backend_ready() -> None:
		nonlocal ready_count
		ready_count += 1
		events.append(f"server{ready_count}:accepted")

	supervisor.backend_spec.on_ready = backend_ready
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready"), ("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:ready" in events)
	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "web2:ready" in events)
	supervisor.shutdown.set()
	assert await run_task == 130

	assert events.index("server2:start") < events.index("server1:stop")
	assert events.index("web2:start") < events.index("server1:stop")
	assert events.index("web2:configured") < events.index("server1:stop")
	assert events.index("web1:stop") < events.index("server1:stop")
	assert events.index("server2:accepted") < events.index("web2:start")


@pytest.mark.asyncio
async def test_failed_reload_keeps_the_previous_stack(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	processes = install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready"), ("server", "fail")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:ready" in events)
	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "server2:close" in events)
	await asyncio.sleep(0)
	assert processes[0].is_alive()
	assert processes[1].is_alive()
	assert not any(event.startswith("web2") for event in events)
	assert not run_task.done()
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_single_server_starts_vite_after_prepare_and_before_uvicorn(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	supervisor.web_first = True
	events: list[str] = []
	assert supervisor.web_spec is not None
	supervisor.web_spec.on_ready = lambda: events.append("web1:accepted")

	def record_backend_event(event: reload_mod._BackendLifecycleEvent) -> None:  # pyright: ignore[reportPrivateUsage]
		events.append(f"server1:{event.event}-accepted")
		supervisor._notify_backend_lifecycle(event)  # pyright: ignore[reportPrivateUsage]

	supervisor._lifecycle._on_backend_event = record_backend_event  # pyright: ignore[reportPrivateUsage]
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:ready" in events)
	supervisor.shutdown.set()
	assert await run_task == 130

	assert events.index("server1:prepared-accepted") < events.index("web1:start")
	assert events.index("web1:accepted") < events.index("server1:serve")
	assert events.index("server1:serve") < events.index("server1:ready")
	assert events.index("server1:stop") < events.index("web1:stop")
	assert events.index("server1:exit") < events.index("web1:stop")


@pytest.mark.asyncio
async def test_backend_failure_keeps_vite_down_until_next_edit(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "fail"), ("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:close" in events)
	assert not any(event.startswith("web") for event in events)

	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "web1:ready" in events)
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_rapid_edit_discards_starting_backend_without_starting_vite(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "stall"), ("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:start" in events)
	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "web1:ready" in events)
	supervisor.shutdown.set()
	assert await run_task == 130
	assert not any(
		event.startswith("web") for event in events[: events.index("server1:close")]
	)
	assert events.index("server1:close") < events.index("server2:start")


@pytest.mark.asyncio
async def test_shutdown_kills_hung_process_trees(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "hang")],
	)
	monkeypatch.setattr(reload_mod, "STOP_TIMEOUT", 0.01)
	monkeypatch.setattr(reload_mod, "KILL_TIMEOUT", 0.01)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:start" in events)
	supervisor.shutdown.set()
	assert await run_task == 130
	assert "web1:kill" in events


@pytest.mark.asyncio
async def test_running_backend_crash_stops_vite_and_waits_for_edit(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	processes = install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:ready" in events)
	processes[0].exit(7)
	await wait_until(lambda: "web1:close" in events)

	assert not run_task.done()
	assert events.count("server1:start") == 1
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_backend_death_during_serve_handshake_is_a_backend_failure(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "serve_broken_pipe"), ("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:close" in events)

	# The broken pipe must not crash the supervisor; it waits for the next edit.
	assert not run_task.done()
	assert not any(event.startswith("web") for event in events)

	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "web1:ready" in events)
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_backend_exit_while_vite_starts_is_not_lost(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	processes = install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "stall")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:start" in events)
	processes[0].exit(7)
	await wait_until(lambda: "web1:close" in events)

	assert not run_task.done()
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_running_vite_crash_returns_its_exit_code(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	processes = install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:ready" in events)
	processes[1].exit(6)

	assert await run_task == 6
	assert "server1:close" in events


@pytest.mark.asyncio
async def test_vite_close_waits_for_process_exit_code(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	processes = install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:ready" in events)
	assert supervisor.web_spec is not None
	instance = supervisor.web_spec.env[ENV_PULSE_VITE_INSTANCE]
	supervisor._notify_vite_lifecycle(  # pyright: ignore[reportPrivateUsage]
		reload_mod._ViteLifecycleEvent(  # pyright: ignore[reportPrivateUsage]
			instance, "closed", 3, 5173
		)
	)
	await asyncio.sleep(0)
	assert not run_task.done()

	processes[1].exit(6)
	assert await run_task == 6


@pytest.mark.asyncio
async def test_vite_close_without_exit_waits_for_listen_or_shutdown(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:ready" in events)
	assert supervisor.web_spec is not None
	instance = supervisor.web_spec.env[ENV_PULSE_VITE_INSTANCE]
	supervisor._notify_vite_lifecycle(  # pyright: ignore[reportPrivateUsage]
		reload_mod._ViteLifecycleEvent(  # pyright: ignore[reportPrivateUsage]
			instance, "closed", 3, 5173
		)
	)
	await asyncio.sleep(0.05)
	assert not run_task.done()

	supervisor._notify_vite_lifecycle(  # pyright: ignore[reportPrivateUsage]
		reload_mod._ViteLifecycleEvent(  # pyright: ignore[reportPrivateUsage]
			instance, "listening", 4, 5173
		)
	)
	await asyncio.sleep(0.05)
	assert not run_task.done()

	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_vite_startup_failure_returns_its_exit_code(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "fail")],
	)

	assert await supervisor.run() == 1
	assert "server1:close" in events


@pytest.mark.asyncio
async def test_missing_vite_plugin_fails_with_actionable_error(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "stall")],
	)
	monkeypatch.setattr(reload_mod, "VITE_START_TIMEOUT", 0.02)

	assert await supervisor.run() == 1
	assert "Add pulseVitePlugin()" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_configured_vite_may_listen_slower_than_start_timeout(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "configured")],
	)
	monkeypatch.setattr(reload_mod, "VITE_START_TIMEOUT", 0.02)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:configured" in events)
	# Well past VITE_START_TIMEOUT: a configured Vite gets an unbounded,
	# interruptible wait to listen instead of a hard failure.
	await asyncio.sleep(0.1)
	assert not run_task.done()
	assert supervisor.web is not None

	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_vite_lifecycle_endpoint_authenticates_and_validates() -> None:
	events: list[reload_mod._ViteLifecycleEvent] = []  # pyright: ignore[reportPrivateUsage]
	server = reload_mod._LifecycleServer(  # pyright: ignore[reportPrivateUsage]
		events.append, lambda _event: None
	)
	environment: dict[str, str] = {}
	await server.start()
	try:
		instance = server.configure_vite(environment)
		url = environment[ENV_PULSE_VITE_LIFECYCLE_URL]
		headers = {
			"Authorization": "Bearer " + environment[ENV_PULSE_VITE_LIFECYCLE_SECRET]
		}
		async with ClientSession() as session:
			response = await session.post(url, json={})
			assert response.status == 401
			response = await session.post(
				url,
				headers=headers,
				json={
					"event": "listening",
					"instance": instance,
					"sequence": True,
					"port": 5173,
				},
			)
			assert response.status == 400
			response = await session.post(
				url,
				headers=headers,
				json={
					"event": "listening",
					"instance": instance,
					"sequence": 1,
					"port": 5173,
				},
			)
			assert response.status == 204
		assert events == [
			reload_mod._ViteLifecycleEvent(  # pyright: ignore[reportPrivateUsage]
				instance, "listening", 1, 5173
			)
		]
	finally:
		await server.close()


@pytest.mark.asyncio
async def test_stale_lifecycle_events_cannot_retarget_relays(tmp_path: Path) -> None:
	class RelaySpy:
		def __init__(self) -> None:
			self.target: tuple[str, int] | None = None

		def set_target(self, host: str, port: int) -> None:
			self.target = (host, port)

	supervisor = supervisor_shell(tmp_path)
	vite_relay = RelaySpy()
	public_relay = RelaySpy()
	supervisor.vite_relay = vite_relay  # pyright: ignore[reportAttributeAccessIssue]
	supervisor.public_relay = public_relay  # pyright: ignore[reportAttributeAccessIssue]
	loop = asyncio.get_running_loop()
	supervisor._states["web"] = reload_mod._ProcessState(loop.create_future())  # pyright: ignore[reportPrivateUsage]
	supervisor._states["server"] = reload_mod._ProcessState(loop.create_future())  # pyright: ignore[reportPrivateUsage]
	supervisor._vite_instance = "vite-current"  # pyright: ignore[reportPrivateUsage]
	supervisor._backend_instance = "backend-current"  # pyright: ignore[reportPrivateUsage]

	supervisor._handle_event(  # pyright: ignore[reportPrivateUsage]
		reload_mod._ViteLifecycleEvent("vite-old", "listening", 1, 5100)  # pyright: ignore[reportPrivateUsage]
	)
	supervisor._handle_event(  # pyright: ignore[reportPrivateUsage]
		reload_mod._BackendLifecycleEvent("backend-old", "ready", [], 8100)  # pyright: ignore[reportPrivateUsage]
	)
	assert vite_relay.target is None
	assert public_relay.target is None

	supervisor._handle_event(  # pyright: ignore[reportPrivateUsage]
		reload_mod._ViteLifecycleEvent("vite-current", "listening", 2, 5200)  # pyright: ignore[reportPrivateUsage]
	)
	supervisor._handle_event(  # pyright: ignore[reportPrivateUsage]
		reload_mod._BackendLifecycleEvent("backend-current", "ready", [], 8200)  # pyright: ignore[reportPrivateUsage]
	)
	assert vite_relay.target == ("127.0.0.1", 5200)
	assert public_relay.target == ("127.0.0.1", 8200)

	supervisor._handle_event(  # pyright: ignore[reportPrivateUsage]
		reload_mod._ViteLifecycleEvent("vite-current", "listening", 1, 5300)  # pyright: ignore[reportPrivateUsage]
	)
	assert vite_relay.target == ("127.0.0.1", 5200)


@pytest.mark.asyncio
async def test_backend_serve_failure_never_starts_vite(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "serve_fail")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:close" in events)
	assert not any(event.startswith("web") for event in events)
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_malformed_backend_protocol_does_not_start_vite(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "malformed")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:malformed" in events)
	await asyncio.sleep(0)
	assert not any(event.startswith("web") for event in events)
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_partial_application_stdout_cannot_corrupt_backend_lifecycle(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	app_file = tmp_path / "app.py"
	app_file.write_text(
		"\n".join(
			[
				'print("partial application log", end="", flush=True)',
				"import pulse as ps",
				"app = ps.App([])",
			]
		)
	)
	listen_socket = socket.socket()
	listen_socket.bind(("127.0.0.1", 0))
	port = listen_socket.getsockname()[1]
	listen_socket.close()
	ready = asyncio.Event()
	worker_env = os.environ.copy()
	worker_env[ENV_PULSE_REACT_SERVER_ADDRESS] = "http://127.0.0.1:5173"
	backend = CommandSpec(
		name="server",
		args=[
			sys.executable,
			"-m",
			"pulse.cli.dev_worker",
			"--target",
			f"{app_file}:app",
			"--host",
			"127.0.0.1",
			"--port",
			str(port),
			"--bind-host",
			"127.0.0.1",
			"--bind-port",
			"0",
			"--plain",
		],
		cwd=tmp_path,
		env=worker_env,
		on_ready=ready.set,
	)
	supervisor = DevSupervisor(
		backend=backend,
		web=None,
		watch_roots=(tmp_path,),
		ignored_roots=(),
		registered_sources=set(),
		tag_mode="plain",
	)

	async def watch(_self: DevSupervisor) -> None:
		await asyncio.Event().wait()

	monkeypatch.setattr(DevSupervisor, "_watch", watch)
	run_task = asyncio.create_task(supervisor.run())
	await asyncio.wait_for(ready.wait(), timeout=5)
	supervisor.shutdown.set()
	assert await asyncio.wait_for(run_task, timeout=5) == 130


def test_worker_uvicorn_config_disables_reload_and_bounds_drain() -> None:
	async def app(scope: Scope, receive: Receive, send: Send) -> None:
		return None

	config = build_server_config(
		app,
		WorkerConfig(
			target="demo:app",
			public_host="localhost",
			public_port=8000,
			bind_host="127.0.0.1",
			bind_port=0,
			plain=True,
			verbose=True,
		),
	)

	assert config.reload is False
	assert config.workers == 1
	assert config.timeout_graceful_shutdown == DEVELOPMENT_GRACEFUL_TIMEOUT
	# The relay makes every connection loopback, so forwarded headers must not
	# be trusted (any client could spoof them).
	assert config.proxy_headers is False


def test_worker_watchdog_stops_server_on_supervisor_exit(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	server = SimpleNamespace(should_exit=False)
	monkeypatch.setattr(sys, "stdin", io.StringIO("noise\n"))

	_watch_supervisor(cast(uvicorn.Server, cast(object, server)))

	assert server.should_exit is True


def test_managed_process_streams_output_accepts_input_and_reports_exit(
	tmp_path: Path,
) -> None:
	lines: list[str] = []
	exited = threading.Event()
	process = ManagedProcess.start(
		CommandSpec(
			name="worker",
			args=[
				sys.executable,
				"-c",
				"import sys; print(sys.stdin.readline().strip(), flush=True)",
			],
			cwd=tmp_path,
			env={},
		),
		lines.append,
		lambda _code: exited.set(),
	)

	process.send_line("serve")
	assert exited.wait(2)
	process.close()

	assert process.returncode == 0
	assert lines == ["serve"]


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
