from __future__ import annotations

import asyncio
import contextlib
import socket
import traceback
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import click
import uvicorn

from pulse.cli.helpers import load_app_from_target
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import env
from pulse.transpiler.assets import get_registered_assets

DEVELOPMENT_GRACEFUL_TIMEOUT = 2


@dataclass(frozen=True, slots=True)
class WorkerConfig:
	target: str
	generation: int
	stage_path: Path
	host: str
	port: int
	plain: bool
	verbose: bool


def build_server_config(app: Any, config: WorkerConfig) -> uvicorn.Config:
	return uvicorn.Config(
		app=app,
		host=config.host,
		port=config.port,
		reload=False,
		workers=1,
		timeout_graceful_shutdown=DEVELOPMENT_GRACEFUL_TIMEOUT,
		log_config=None if config.verbose else get_log_config(),
		use_colors=not config.plain,
	)


def run_generation_worker(
	config: WorkerConfig,
	control: Connection,
	listen_socket: socket.socket,
) -> None:
	try:
		asyncio.run(_run_generation_worker(config, control, listen_socket))
	except KeyboardInterrupt:
		pass
	finally:
		with contextlib.suppress(OSError):
			control.close()
		listen_socket.close()


async def _run_generation_worker(
	config: WorkerConfig,
	control: Connection,
	listen_socket: socket.socket,
) -> None:
	env.codegen_output = str(config.stage_path)
	env.pulse_host = config.host
	env.pulse_port = config.port

	try:
		app_ctx = load_app_from_target(config.target)
		asgi = app_ctx.app.asgi_factory()
		server_config = build_server_config(asgi, config)
		server_config.load()
		if not _send(
			control,
			{
				"type": "prepared",
				"generation": config.generation,
				"sources": [
					str(asset.source_path.resolve())
					for asset in get_registered_assets()
				],
			},
		):
			return
	except BaseException as exc:
		if isinstance(exc, click.exceptions.Exit):
			# load_app_from_target already printed the real error and traceback;
			# str(typer.Exit(1)) is just "1" and its traceback is noise.
			failure = {"error": "application failed to load (see output above)"}
		else:
			failure = {"error": str(exc), "traceback": traceback.format_exc()}
		_send(
			control,
			{
				"type": "failed",
				"generation": config.generation,
				"phase": "prepare",
				**failure,
			},
		)
		return

	command = await _receive(control)
	if command != {"type": "serve", "generation": config.generation}:
		return

	server = uvicorn.Server(server_config)
	serve_task = asyncio.create_task(server.serve(sockets=[listen_socket]))
	while not server.started:
		if serve_task.done():
			exception = serve_task.exception()
			_send(
				control,
				{
					"type": "failed",
					"generation": config.generation,
					"phase": "startup",
					"error": str(exception or "Uvicorn exited before readiness"),
				},
			)
			return
		await asyncio.sleep(0.01)

	if not _send(control, {"type": "ready", "generation": config.generation}):
		server.force_exit = True
		server.should_exit = True
		await serve_task
		return

	while not serve_task.done():
		command_task = asyncio.create_task(_receive(control))
		done, _ = await asyncio.wait(
			{serve_task, command_task}, return_when=asyncio.FIRST_COMPLETED
		)
		if serve_task in done:
			command_task.cancel()
			with contextlib.suppress(asyncio.CancelledError):
				await command_task
			break
		command = command_task.result()
		if command.get("type") == "stop" and "generation" not in command:
			server.force_exit = True
			server.should_exit = True
			continue
		if command.get("generation") != config.generation:
			continue
		if command.get("type") == "drain":
			await app_ctx.app.begin_drain()
			server.should_exit = True

	try:
		await serve_task
	except asyncio.CancelledError:
		raise
	except Exception as exc:
		_send(
			control,
			{
				"type": "failed",
				"generation": config.generation,
				"phase": "serve",
				"error": str(exc),
				"traceback": traceback.format_exc(),
			},
		)


async def wait_readable(fd: int) -> None:
	"""Suspend until fd is readable, without polling."""
	loop = asyncio.get_running_loop()
	readable: asyncio.Future[None] = loop.create_future()

	def _mark_readable() -> None:
		if not readable.done():
			readable.set_result(None)

	loop.add_reader(fd, _mark_readable)
	try:
		await readable
	finally:
		loop.remove_reader(fd)


async def _receive(control: Connection) -> dict[str, Any]:
	try:
		while not control.poll():
			await wait_readable(control.fileno())
		return control.recv()
	except (EOFError, OSError):
		return {"type": "stop"}


def _send(control: Connection, message: dict[str, Any]) -> bool:
	try:
		control.send(message)
	except (BrokenPipeError, EOFError, OSError):
		return False
	return True
