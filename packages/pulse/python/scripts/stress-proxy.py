#!/usr/bin/env python3
"""Heavy stress test for the Pulse proxy (ASGI or FastAPI mode)."""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from pulse.cli.helpers import load_app_from_target
from pulse.env import (
	ENV_PULSE_DISABLE_CODEGEN,
	ENV_PULSE_ENV,
	ENV_PULSE_HOST,
	ENV_PULSE_PORT,
	ENV_PULSE_PROXY_MODE,
	ENV_PULSE_REACT_SERVER_ADDRESS,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route


@dataclass
class Metrics:
	total: int = 0
	ok: int = 0
	errors: int = 0
	disconnects: int = 0
	bytes_read: int = 0
	in_flight: int = 0
	max_in_flight: int = 0


class UpstreamState:
	active_streams: int
	max_active: int
	_lock: asyncio.Lock

	def __init__(self) -> None:
		self.active_streams = 0
		self.max_active = 0
		self._lock = asyncio.Lock()

	async def open_stream(self) -> None:
		async with self._lock:
			self.active_streams += 1
			if self.active_streams > self.max_active:
				self.max_active = self.active_streams

	async def close_stream(self) -> None:
		async with self._lock:
			self.active_streams -= 1


def _make_upstream_app(
	state: UpstreamState,
	*,
	chunk_count: int,
	chunk_size: int,
	chunk_delay: float,
) -> Starlette:
	payload = b"x" * chunk_size

	async def fast(_: Request) -> Response:
		return PlainTextResponse("ok")

	async def echo(request: Request) -> Response:
		body = await request.body()
		return PlainTextResponse(str(len(body)))

	async def stream(_: Request) -> Response:
		async def _gen():
			await state.open_stream()
			try:
				for _ in range(chunk_count):
					yield payload
					if chunk_delay:
						await asyncio.sleep(chunk_delay)
			finally:
				await state.close_stream()

		return StreamingResponse(_gen(), media_type="application/octet-stream")

	return Starlette(
		routes=[
			Route("/fast", fast, methods=["GET"]),
			Route("/echo", echo, methods=["POST"]),
			Route("/stream", stream, methods=["GET"]),
		]
	)


async def _wait_for_port(host: str, port: int, timeout: float) -> None:
	start = time.monotonic()
	while time.monotonic() - start < timeout:
		try:
			reader, writer = await asyncio.open_connection(host, port)
			writer.close()
			await writer.wait_closed()
			return
		except OSError:
			await asyncio.sleep(0.05)
	raise RuntimeError(f"Timed out waiting for {host}:{port}")


async def _serve(
	app: Any, host: str, port: int, name: str
) -> tuple[uvicorn.Server, asyncio.Task[None]]:
	config = uvicorn.Config(
		app,
		host=host,
		port=port,
		log_level="warning",
		reload=False,
	)
	server = uvicorn.Server(config)
	task = asyncio.create_task(server.serve(), name=f"{name}-server")
	await _wait_for_port(host, port, timeout=10)
	return server, task


async def _run_load(
	base_url: str,
	metrics: Metrics,
	*,
	concurrency: int,
	total: int | None,
	duration: float | None,
	stream_ratio: float,
	post_ratio: float,
	disconnect_ratio: float,
	request_timeout: float,
) -> list[str]:
	lock = asyncio.Lock()
	semaphore = asyncio.Semaphore(concurrency)
	end_time = time.monotonic() + duration if duration else None
	error_samples: list[str] = []
	error_limit = 5

	limits = httpx.Limits(
		max_connections=concurrency * 2,
		max_keepalive_connections=concurrency,
	)
	disconnect_limits = httpx.Limits(
		max_connections=concurrency,
		max_keepalive_connections=0,
	)
	timeout = httpx.Timeout(request_timeout)
	async with (
		httpx.AsyncClient(base_url=base_url, limits=limits, timeout=timeout) as client,
		httpx.AsyncClient(
			base_url=base_url, limits=disconnect_limits, timeout=timeout
		) as disconnect_client,
	):

		async def _record_start() -> None:
			async with lock:
				metrics.in_flight += 1
				if metrics.in_flight > metrics.max_in_flight:
					metrics.max_in_flight = metrics.in_flight

		async def _record_end() -> None:
			async with lock:
				metrics.in_flight -= 1

		async def _record_error(message: str | None = None) -> None:
			async with lock:
				metrics.errors += 1
				if message and len(error_samples) < error_limit:
					error_samples.append(message)

		async def _run_one() -> None:
			await _record_start()
			request_label = "unknown"
			disconnecting = False
			try:
				r = random.random()
				if r < post_ratio:
					request_label = "POST /echo"
					body = os.urandom(1024)
					resp = await client.post("/echo", content=body)
					if resp.status_code == 200:
						metrics.ok += 1
					else:
						await _record_error(f"POST /echo status={resp.status_code}")
				elif r < post_ratio + stream_ratio:
					request_label = "GET /stream"
					disconnecting = random.random() < disconnect_ratio
					stream_client = disconnect_client if disconnecting else client
					try:
						async with stream_client.stream("GET", "/stream") as resp:
							if resp.status_code != 200:
								await _record_error(
									f"GET /stream status={resp.status_code}"
								)
								return
							async for chunk in resp.aiter_raw():
								metrics.bytes_read += len(chunk)
								if disconnecting:
									metrics.disconnects += 1
									await resp.aclose()
									break
							else:
								metrics.ok += 1
					except (httpx.ReadError, httpx.RemoteProtocolError) as exc:
						if disconnecting:
							metrics.disconnects += 1
						else:
							await _record_error(
								f"{request_label} {type(exc).__name__}: {exc}"
							)
				else:
					request_label = "GET /fast"
					resp = await client.get("/fast")
					if resp.status_code == 200:
						metrics.ok += 1
					else:
						await _record_error(f"GET /fast status={resp.status_code}")
			except Exception as exc:
				await _record_error(f"{request_label} {type(exc).__name__}: {exc}")
			finally:
				await _record_end()

		async def _worker() -> None:
			while True:
				if end_time is not None and time.monotonic() >= end_time:
					return
				async with lock:
					if total is not None and metrics.total >= total:
						return
					metrics.total += 1
				async with semaphore:
					await _run_one()

		await asyncio.gather(*(_worker() for _ in range(concurrency)))
	return error_samples


async def _run(args: argparse.Namespace) -> int:
	root = Path(__file__).resolve().parents[4]
	example_path = root / "examples" / "main.py"
	if not example_path.exists():
		raise RuntimeError(f"Example app not found at {example_path}")

	state = UpstreamState()
	upstream_app = _make_upstream_app(
		state,
		chunk_count=args.chunk_count,
		chunk_size=args.chunk_size,
		chunk_delay=args.chunk_delay,
	)
	upstream_host = "127.0.0.1"
	upstream_base = f"http://{upstream_host}:{args.upstream_port}"

	os.environ[ENV_PULSE_REACT_SERVER_ADDRESS] = upstream_base
	os.environ[ENV_PULSE_PROXY_MODE] = args.proxy_mode
	os.environ[ENV_PULSE_HOST] = args.host
	os.environ[ENV_PULSE_PORT] = str(args.port)
	os.environ[ENV_PULSE_ENV] = args.env
	if args.disable_codegen:
		os.environ[ENV_PULSE_DISABLE_CODEGEN] = "1"

	app_ctx = load_app_from_target(str(example_path))
	if args.env in ("prod", "ci") and not app_ctx.app.server_address:
		server_address = f"https://{args.host}:{args.port}"
		app_ctx.app.server_address = server_address
		if not app_ctx.app.internal_server_address:
			app_ctx.app.internal_server_address = server_address
	pulse_app = app_ctx.app.asgi_factory()

	upstream_server, upstream_task = await _serve(
		upstream_app, upstream_host, args.upstream_port, "upstream"
	)
	pulse_server, pulse_task = await _serve(pulse_app, args.host, args.port, "pulse")

	metrics = Metrics()
	start = time.monotonic()
	error_samples: list[str] = []
	try:
		error_samples = await _run_load(
			f"http://{args.host}:{args.port}",
			metrics,
			concurrency=args.concurrency,
			total=args.requests,
			duration=args.duration,
			stream_ratio=args.stream_ratio,
			post_ratio=args.post_ratio,
			disconnect_ratio=args.disconnect_ratio,
			request_timeout=args.timeout,
		)
	finally:
		pulse_server.should_exit = True
		upstream_server.should_exit = True
		results = await asyncio.gather(
			pulse_task, upstream_task, return_exceptions=True
		)
		for result in results:
			if isinstance(result, Exception):
				print(f"server task error: {result}", file=sys.stderr)
				metrics.errors += 1

	elapsed = time.monotonic() - start
	ok = metrics.ok
	errors = metrics.errors
	total = metrics.total
	rate = total / elapsed if elapsed else 0.0
	print(
		"proxy stress results",
		f"total={total}",
		f"ok={ok}",
		f"errors={errors}",
		f"disconnects={metrics.disconnects}",
		f"bytes={metrics.bytes_read}",
		f"in_flight_max={metrics.max_in_flight}",
		f"upstream_active={state.active_streams}",
		f"upstream_max={state.max_active}",
		f"elapsed={elapsed:.2f}s",
		f"rps={rate:.1f}",
		sep=" ",
	)
	if error_samples:
		print("error samples:", "; ".join(error_samples), file=sys.stderr)

	if state.active_streams != 0:
		print("error: upstream streams still active after stress run", file=sys.stderr)
		return 2
	if errors:
		return 1
	return 0


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=8010)
	parser.add_argument("--upstream-port", type=int, default=9010)
	parser.add_argument("--proxy-mode", choices=["asgi", "fastapi"], default="asgi")
	parser.add_argument("--env", choices=["dev", "ci", "prod"], default="prod")
	parser.add_argument("--disable-codegen", action="store_true", default=True)
	parser.add_argument("--requests", type=int, default=5000)
	parser.add_argument("--duration", type=float, default=None)
	parser.add_argument("--concurrency", type=int, default=200)
	parser.add_argument("--stream-ratio", type=float, default=0.7)
	parser.add_argument("--post-ratio", type=float, default=0.1)
	parser.add_argument("--disconnect-ratio", type=float, default=0.2)
	parser.add_argument("--chunk-count", type=int, default=50)
	parser.add_argument("--chunk-size", type=int, default=1024)
	parser.add_argument("--chunk-delay", type=float, default=0.0)
	parser.add_argument("--timeout", type=float, default=10.0)
	return parser.parse_args()


def main() -> int:
	args = _parse_args()
	try:
		return asyncio.run(_run(args))
	except KeyboardInterrupt:
		return 130


if __name__ == "__main__":
	raise SystemExit(main())
