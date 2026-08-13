from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import socket
import sys
import threading
import traceback
from dataclasses import dataclass
from typing import Any, override

import click
import uvicorn

from pulse.cli.helpers import load_app_from_target
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import ENV_PULSE_LISTEN_FDS, ENV_PULSE_READY_FD, env

DEVELOPMENT_GRACEFUL_TIMEOUT = 0


@dataclass(frozen=True, slots=True)
class WorkerConfig:
	target: str
	public_host: str
	public_port: int
	plain: bool
	verbose: bool


def build_server_config(app: Any, config: WorkerConfig) -> uvicorn.Config:
	return uvicorn.Config(
		app=app,
		host=config.public_host,
		port=config.public_port,
		reload=False,
		workers=1,
		timeout_graceful_shutdown=DEVELOPMENT_GRACEFUL_TIMEOUT,
		log_config=None if config.verbose else get_log_config(),
		use_colors=not config.plain,
	)


class DevServer(uvicorn.Server):
	@override
	async def startup(self, sockets: list[socket.socket] | None = None) -> None:
		await super().startup(sockets)
		if self.started:
			_notify_ready()


def inherit_listeners() -> list[socket.socket]:
	raw = os.environ.get(ENV_PULSE_LISTEN_FDS, "")
	if not raw.strip():
		raise RuntimeError(f"{ENV_PULSE_LISTEN_FDS} is not set")
	listeners: list[socket.socket] = []
	for part in raw.split(","):
		family_text, fd_text = part.split(":", 1)
		fd = int(fd_text)
		listener = socket.fromfd(fd, int(family_text), socket.SOCK_STREAM)
		os.close(fd)
		listeners.append(listener)
	return listeners


def _notify_ready() -> None:
	raw = os.environ.get(ENV_PULSE_READY_FD)
	if raw is None or raw.strip() == "":
		return
	fd = int(raw)
	with contextlib.suppress(OSError):
		os.write(fd, b"1")
		os.close(fd)


def prepare_worker(config: WorkerConfig) -> uvicorn.Config:
	env.pulse_host = config.public_host
	env.pulse_port = config.public_port
	app_ctx = load_app_from_target(config.target)
	asgi = app_ctx.app.asgi_factory()
	server_config = build_server_config(asgi, config)
	server_config.load()
	return server_config


def _watch_supervisor(server: uvicorn.Server) -> None:
	while sys.stdin.readline():
		pass
	server.should_exit = True
	server.force_exit = True


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument("--target", required=True)
	parser.add_argument("--host", required=True)
	parser.add_argument("--port", type=int, required=True)
	parser.add_argument("--plain", action="store_true")
	parser.add_argument("--verbose", action="store_true")
	return parser.parse_args()


def main() -> None:
	args = _parse_args()
	config = WorkerConfig(
		target=args.target,
		public_host=args.host,
		public_port=args.port,
		plain=args.plain,
		verbose=args.verbose,
	)
	try:
		listeners = inherit_listeners()
		server_config = prepare_worker(config)
		server = DevServer(server_config)
		threading.Thread(
			target=_watch_supervisor,
			args=(server,),
			name="pulse-supervisor-watchdog",
			daemon=True,
		).start()
		asyncio.run(server.serve(sockets=listeners))
		raise SystemExit(0)
	except click.exceptions.Exit as exc:
		raise SystemExit(exc.exit_code) from None
	except KeyboardInterrupt:
		raise SystemExit(130) from None
	except SystemExit:
		raise
	except BaseException:
		print(traceback.format_exc(), flush=True)
		raise SystemExit(1) from None


if __name__ == "__main__":
	main()
