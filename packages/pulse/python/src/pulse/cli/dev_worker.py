from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import socket
import sys
import threading
import traceback
from typing import Any, override

import click
import uvicorn

from pulse.cli.helpers import load_app_from_target
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import ENV_PULSE_LISTEN_FDS, ENV_PULSE_READY_FD, env

DEVELOPMENT_GRACEFUL_TIMEOUT = 0


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


def worker_uvicorn_config(
	app: Any, *, host: str, port: int, plain: bool, verbose: bool
) -> uvicorn.Config:
	return uvicorn.Config(
		app=app,
		host=host,
		port=port,
		reload=False,
		workers=1,
		timeout_graceful_shutdown=DEVELOPMENT_GRACEFUL_TIMEOUT,
		log_config=None if verbose else get_log_config(),
		use_colors=not plain,
	)


def _notify_ready() -> None:
	raw = os.environ.get(ENV_PULSE_READY_FD)
	if raw is None or raw.strip() == "":
		return
	fd = int(raw)
	with contextlib.suppress(OSError):
		os.write(fd, b"1")
		os.close(fd)


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
	env.pulse_host = args.host
	env.pulse_port = args.port
	try:
		listeners = inherit_listeners()
		app_ctx = load_app_from_target(args.target)
		config = worker_uvicorn_config(
			app_ctx.app.asgi_factory(),
			host=args.host,
			port=args.port,
			plain=args.plain,
			verbose=args.verbose,
		)
		server = DevServer(config)
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
