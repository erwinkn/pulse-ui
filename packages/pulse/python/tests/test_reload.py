import asyncio
import contextlib
import io
import os
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast, final

import pulse.cli.reload as reload_mod
import pytest
import uvicorn
from pulse.cli.dev_worker import (
	DEVELOPMENT_GRACEFUL_TIMEOUT,
	WorkerConfig,
	_watch_supervisor,  # pyright: ignore[reportPrivateUsage]
	build_server_config,
	inherit_listeners,
)
from pulse.cli.models import CommandSpec
from pulse.cli.ports import reserve_port
from pulse.cli.processes import ManagedProcess
from pulse.cli.reload import DevSupervisor, PulseWatchFilter
from pulse.env import ENV_PULSE_LISTEN_FDS, ENV_PULSE_READY_FD
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
		self.on_exit: Callable[[int], None] | None = None
		self.pass_fds: tuple[int, ...] = ()
		self.ready_w: int | None = None

	@property
	def returncode(self) -> int | None:
		return self.code

	def is_alive(self) -> bool:
		return self.alive

	def request_stop(self) -> None:
		self.events.append(f"{self.name}:stop")
		if not self.hangs:
			self.exit(0)

	def kill_tree(self) -> None:
		self.events.append(f"{self.name}:kill")
		self.exit(-9)

	def exit(self, code: int) -> None:
		if self.ready_w is not None:
			with contextlib.suppress(OSError):
				os.close(self.ready_w)
			self.ready_w = None
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


def supervisor_shell(
	tmp_path: Path, listeners: tuple[socket.socket, ...] = ()
) -> DevSupervisor:
	return DevSupervisor(
		backend=command("server", tmp_path),
		web=command("web", tmp_path, "web ready"),
		watch_roots=(tmp_path,),
		ignored_roots=(tmp_path / "web" / "app" / "pulse",),
		registered_sources=set(),
		tag_mode="plain",
		listeners=listeners,
		web_first=True,
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

	def start(
		_cls: type[ManagedProcess],
		spec: CommandSpec,
		on_output: Callable[[str], None],
		on_exit: Callable[[int], None],
		*,
		pass_fds: tuple[int, ...] = (),
	) -> FakeProcess:
		expected_name, outcome = plans.pop(0)
		assert spec.name == expected_name
		instance = 1 + sum(process.name.startswith(spec.name) for process in processes)
		name = f"{spec.name}{instance}"
		process = FakeProcess(name, events, hangs=outcome == "hang")
		process.on_exit = on_exit
		process.pass_fds = pass_fds
		processes.append(process)
		events.append(f"{name}:start")
		if spec.name == "server":
			ready_fd = int(spec.env[ENV_PULSE_READY_FD])
			child_w = os.dup(ready_fd)
			process.ready_w = child_w
			if outcome == "ready":
				os.write(child_w, b"1")
				os.close(child_w)
				process.ready_w = None
			elif outcome == "fail":
				os.close(child_w)
				process.ready_w = None
				process.exit(1)
		elif spec.name == "web":
			if outcome == "ready":
				on_output("web ready")
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

	assert filter_(Change.modified, str(app_root / "main.py"))
	assert not filter_(Change.modified, str(app_root / "build" / "artifact.py"))
	assert not filter_(Change.modified, str(app_root / "venv" / "lib" / "pkg.py"))


@pytest.mark.asyncio
async def test_reload_kills_backend_immediately_and_keeps_vite(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("web", "ready"), ("server", "ready"), ("server", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:start" in events)
	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "server2:start" in events)
	supervisor.shutdown.set()
	assert await run_task == 130

	assert events.index("web1:start") < events.index("server1:start")
	assert "server1:kill" in events
	assert "web2:start" not in events
	assert events.index("server1:kill") < events.index("server2:start")


@pytest.mark.asyncio
async def test_failed_backend_keeps_vite_and_waits_for_edit(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("web", "ready"), ("server", "fail"), ("server", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:close" in events)
	assert supervisor.web is not None
	assert supervisor.web.is_alive()

	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "server2:start" in events)
	supervisor.shutdown.set()
	assert await run_task == 130


@pytest.mark.asyncio
async def test_rapid_edit_kills_starting_backend(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("web", "ready"), ("server", "stall"), ("server", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:start" in events)
	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "server2:start" in events)
	supervisor.shutdown.set()
	assert await run_task == 130
	assert "server1:kill" in events
	assert events.index("server1:kill") < events.index("server2:start")


@pytest.mark.asyncio
async def test_reload_starts_backend_before_vite_when_not_web_first(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	supervisor.web_first = False
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("server", "ready"), ("web", "ready"), ("server", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:start" in events)
	supervisor.desired += 1
	supervisor.changed.set()
	await wait_until(lambda: "server2:start" in events)
	supervisor.shutdown.set()
	assert await run_task == 130

	assert events.index("server1:start") < events.index("web1:start")
	assert "web2:start" not in events


@pytest.mark.asyncio
async def test_vite_crash_returns_its_exit_code(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	processes = install_process_script(
		monkeypatch,
		events,
		[("web", "ready"), ("server", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "server1:start" in events)
	processes[0].exit(6)
	assert await run_task == 6
	assert "server1:kill" in events


@pytest.mark.asyncio
async def test_shutdown_kills_hung_process_trees(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	supervisor = supervisor_shell(tmp_path)
	events: list[str] = []
	install_process_script(
		monkeypatch,
		events,
		[("web", "hang"), ("server", "ready")],
	)

	run_task = asyncio.create_task(supervisor.run())
	await wait_until(lambda: "web1:start" in events)
	supervisor.shutdown.set()
	supervisor._handle_interrupt()  # pyright: ignore[reportPrivateUsage]
	assert await run_task == 130
	assert "web1:kill" in events


@pytest.mark.asyncio
async def test_worker_inherits_listen_sockets_across_reload(tmp_path: Path) -> None:
	reservation = reserve_port("127.0.0.1", 0, find_port=False)
	script = tmp_path / "worker.py"
	script.write_text(
		"\n".join(
			[
				"import os, socket, sys",
				"from http.server import BaseHTTPRequestHandler, HTTPServer",
				f"raw = os.environ[{ENV_PULSE_LISTEN_FDS!r}]",
				"family, fd = raw.split(':')",
				"sock = socket.fromfd(int(fd), int(family), socket.SOCK_STREAM)",
				"os.close(int(fd))",
				"class H(BaseHTTPRequestHandler):",
				"    def do_GET(self):",
				"        self.send_response(200)",
				"        self.end_headers()",
				"        self.wfile.write(b'ok')",
				"    def log_message(self, *_args):",
				"        return",
				"httpd = HTTPServer(('127.0.0.1', 0), H, bind_and_activate=False)",
				"httpd.socket = sock",
				f"os.write(int(os.environ[{ENV_PULSE_READY_FD!r}]), b'1')",
				"httpd.handle_request()",
			]
		)
	)

	async def once() -> None:
		ready_r, ready_w = os.pipe()
		os.set_inheritable(ready_w, True)
		process = ManagedProcess.start(
			CommandSpec(
				name="server",
				args=[sys.executable, str(script)],
				cwd=tmp_path,
				env={
					**os.environ,
					ENV_PULSE_LISTEN_FDS: (
						f"{reservation.sockets[0].family}:{reservation.sockets[0].fileno()}"
					),
					ENV_PULSE_READY_FD: str(ready_w),
				},
			),
			lambda _line: None,
			lambda _code: None,
			pass_fds=(reservation.sockets[0].fileno(), ready_w),
		)
		os.close(ready_w)
		assert await asyncio.to_thread(os.read, ready_r, 1) == b"1"
		os.close(ready_r)
		reader, writer = await asyncio.open_connection("127.0.0.1", reservation.port)
		writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
		await writer.drain()
		body = await reader.read()
		writer.close()
		await writer.wait_closed()
		assert b"ok" in body
		process.kill_tree()
		process.close()

	try:
		await once()
		await once()
	finally:
		reservation.close()


def test_inherit_listeners_rebuilds_sockets_from_env() -> None:
	reservation = reserve_port("127.0.0.1", 0, find_port=False)
	try:
		listener = reservation.sockets[0]
		dup = listener.dup()
		os.environ[ENV_PULSE_LISTEN_FDS] = f"{dup.family}:{dup.fileno()}"
		inherited = inherit_listeners()
		try:
			assert inherited[0].getsockname()[1] == reservation.port
		finally:
			for sock in inherited:
				sock.close()
	finally:
		reservation.close()
		os.environ.pop(ENV_PULSE_LISTEN_FDS, None)


def test_worker_uvicorn_config_disables_reload() -> None:
	async def app(scope: Scope, receive: Receive, send: Send) -> None:
		return None

	config = build_server_config(
		app,
		WorkerConfig(
			target="demo:app",
			public_host="localhost",
			public_port=8000,
			plain=True,
			verbose=True,
		),
	)

	assert config.reload is False
	assert config.workers == 1
	assert config.timeout_graceful_shutdown == DEVELOPMENT_GRACEFUL_TIMEOUT


def test_worker_watchdog_force_exits_on_supervisor_exit(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	server = SimpleNamespace(should_exit=False, force_exit=False)
	monkeypatch.setattr(sys, "stdin", io.StringIO("noise\n"))

	_watch_supervisor(cast(uvicorn.Server, cast(object, server)))

	assert server.should_exit is True
	assert server.force_exit is True
