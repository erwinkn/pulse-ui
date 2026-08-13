from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import threading
import traceback
from dataclasses import dataclass
from http.client import HTTPConnection
from typing import Any, override
from urllib.parse import urlsplit

import click
import uvicorn

from pulse.cli.helpers import load_app_from_target
from pulse.cli.uvicorn_log_config import get_log_config
from pulse.env import (
	ENV_PULSE_BACKEND_INSTANCE,
	ENV_PULSE_BACKEND_LIFECYCLE_SECRET,
	ENV_PULSE_BACKEND_LIFECYCLE_URL,
	env,
)
from pulse.transpiler.assets import get_registered_assets

DEVELOPMENT_GRACEFUL_TIMEOUT = 2


@dataclass(frozen=True, slots=True)
class WorkerConfig:
	target: str
	public_host: str
	public_port: int
	bind_host: str
	bind_port: int
	plain: bool
	verbose: bool


def build_server_config(app: Any, config: WorkerConfig) -> uvicorn.Config:
	return uvicorn.Config(
		app=app,
		host=config.bind_host,
		port=config.bind_port,
		reload=False,
		workers=1,
		timeout_graceful_shutdown=DEVELOPMENT_GRACEFUL_TIMEOUT,
		log_config=None if config.verbose else get_log_config(),
		use_colors=not config.plain,
		# Every connection arrives through the supervisor's loopback relay, so
		# forwarded headers would be spoofable by any client; report the relay
		# peer (loopback) instead of trusting X-Forwarded-For.
		proxy_headers=False,
	)


class DevServer(uvicorn.Server):
	@override
	async def startup(self, sockets: list[socket.socket] | None = None) -> None:
		await super().startup(sockets)
		if self.started:
			server_sockets = self.servers[0].sockets
			if not server_sockets:
				raise RuntimeError("Uvicorn started without a listening socket")
			address = server_sockets[0].getsockname()
			if not isinstance(address, tuple):
				raise RuntimeError("Uvicorn did not start a TCP listener")
			port: object = address[1]
			if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
				raise RuntimeError("Uvicorn reported an invalid TCP port")
			await asyncio.to_thread(report_lifecycle, "ready", port=port)


def report_lifecycle(
	event: str,
	sources: list[str] | None = None,
	port: int | None = None,
) -> None:
	url = os.environ[ENV_PULSE_BACKEND_LIFECYCLE_URL]
	secret = os.environ[ENV_PULSE_BACKEND_LIFECYCLE_SECRET]
	instance = os.environ[ENV_PULSE_BACKEND_INSTANCE]
	body: dict[str, object] = {"event": event, "instance": instance}
	if sources is not None:
		body["sources"] = sources
	if port is not None:
		body["port"] = port
	callback = urlsplit(url)
	if callback.hostname is None or callback.port is None:
		raise RuntimeError("Invalid Pulse backend lifecycle URL")
	connection = HTTPConnection(callback.hostname, callback.port, timeout=2)
	try:
		connection.request(
			"POST",
			callback.path,
			body=json.dumps(body, separators=(",", ":")).encode(),
			headers={
				"Authorization": f"Bearer {secret}",
				"Content-Type": "application/json",
			},
		)
		response = connection.getresponse()
		response.read()
		if response.status != 204:
			raise RuntimeError(
				f"Pulse supervisor rejected backend {event}: HTTP {response.status}"
			)
	finally:
		connection.close()


def prepare_worker(config: WorkerConfig) -> uvicorn.Config:
	env.pulse_host = config.public_host
	env.pulse_port = config.public_port
	app_ctx = load_app_from_target(config.target)
	asgi = app_ctx.app.asgi_factory()
	server_config = build_server_config(asgi, config)
	server_config.load()
	report_lifecycle(
		"prepared",
		[str(asset.source_path.resolve()) for asset in get_registered_assets()],
	)
	return server_config


def _watch_supervisor(server: uvicorn.Server) -> None:
	while sys.stdin.readline():
		pass
	# EOF means the supervisor is gone; stop serving rather than run orphaned.
	server.should_exit = True


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument("--target", required=True)
	parser.add_argument("--host", required=True)
	parser.add_argument("--port", type=int, required=True)
	parser.add_argument("--bind-host", required=True)
	parser.add_argument("--bind-port", type=int, required=True)
	parser.add_argument("--plain", action="store_true")
	parser.add_argument("--verbose", action="store_true")
	return parser.parse_args()


def main() -> None:
	args = _parse_args()
	config = WorkerConfig(
		target=args.target,
		public_host=args.host,
		public_port=args.port,
		bind_host=args.bind_host,
		bind_port=args.bind_port,
		plain=args.plain,
		verbose=args.verbose,
	)
	try:
		server_config = prepare_worker(config)
		if sys.stdin.readline().strip() != "serve":
			raise SystemExit(0)
		server = DevServer(server_config)
		threading.Thread(
			target=_watch_supervisor,
			args=(server,),
			name="pulse-supervisor-watchdog",
			daemon=True,
		).start()
		asyncio.run(server.serve())
		raise SystemExit(0)
	except click.exceptions.Exit as exc:
		# load_app_from_target already printed the useful import error.
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
