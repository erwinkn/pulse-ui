"""
Proxy handler for forwarding requests to React Router server in single-server mode.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any, cast

import httpx
import websockets
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import Message, Receive, Scope, Send
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.typing import Subprotocol

from pulse.context import PulseContext
from pulse.cookies import parse_cookie_header

logger = logging.getLogger(__name__)
_DISCONNECT_POLL_INTERVAL = 0.1


class _ReactProxyBase:
	"""
	Shared React proxy helpers and WebSocket forwarding.
	"""

	react_server_address: str
	server_address: str
	_client: httpx.AsyncClient | None
	_active_responses: set[httpx.Response]
	_active_websockets: set[Any]
	_closing: asyncio.Event

	def __init__(self, react_server_address: str, server_address: str):
		"""
		Args:
		    react_server_address: Internal React Router server URL (e.g., http://localhost:5173)
		    server_address: External server URL exposed to clients (e.g., http://localhost:8000)
		"""
		self.react_server_address = react_server_address
		self.server_address = server_address
		self._client = None
		self._active_responses = set()
		self._active_websockets = set()
		self._closing = asyncio.Event()

	def rewrite_url(self, url: str) -> str:
		"""Rewrite internal React server URLs to external server address."""
		if self.react_server_address in url:
			return url.replace(self.react_server_address, self.server_address)
		return url

	@property
	def client(self) -> httpx.AsyncClient:
		"""Lazy initialization of HTTP client."""
		if self._client is None:
			self._client = httpx.AsyncClient(
				timeout=httpx.Timeout(30.0),
				follow_redirects=False,
			)
		return self._client

	def _is_websocket_upgrade(self, request: Request) -> bool:
		"""Check if request is a WebSocket upgrade."""
		upgrade = request.headers.get("upgrade", "").lower()
		connection = request.headers.get("connection", "").lower()
		return upgrade == "websocket" and "upgrade" in connection

	def _http_to_ws_url(self, http_url: str) -> str:
		"""Convert HTTP URL to WebSocket URL."""
		if http_url.startswith("https://"):
			return http_url.replace("https://", "wss://", 1)
		elif http_url.startswith("http://"):
			return http_url.replace("http://", "ws://", 1)
		return http_url

	async def proxy_websocket(self, websocket: WebSocket) -> None:
		"""
		Proxy WebSocket connection to React Router server.
		Only allowed in dev mode and on root path "/".
		"""

		# Build target WebSocket URL
		ws_url = self._http_to_ws_url(self.react_server_address)
		target_url = ws_url.rstrip("/") + websocket.url.path
		if websocket.url.query:
			target_url += "?" + websocket.url.query

		# Extract subprotocols from client request
		subprotocol_header = websocket.headers.get("sec-websocket-protocol")
		subprotocols: list[Subprotocol] | None = None
		if subprotocol_header:
			# Parse comma-separated list of subprotocols
			# Subprotocol is a NewType (just a type annotation), so cast strings to it
			subprotocols = cast(
				list[Subprotocol], [p.strip() for p in subprotocol_header.split(",")]
			)

		# Extract headers for WebSocket connection (excluding WebSocket-specific headers)
		headers = {
			k: v
			for k, v in websocket.headers.items()
			if k.lower()
			not in (
				"host",
				"upgrade",
				"connection",
				"sec-websocket-key",
				"sec-websocket-version",
				"sec-websocket-protocol",
			)
		}

		# Connect to target WebSocket server first to negotiate subprotocol
		try:
			async with websockets.connect(
				target_url,
				additional_headers=headers,
				subprotocols=subprotocols,
				ping_interval=None,  # Let the target server handle ping/pong
			) as target_ws:
				self._active_websockets.add(target_ws)
				try:
					# Accept client connection with the negotiated subprotocol
					await websocket.accept(subprotocol=target_ws.subprotocol)

					# Forward messages bidirectionally
					async def forward_client_to_target():
						try:
							async for message in websocket.iter_text():
								await target_ws.send(message)
						except (WebSocketDisconnect, websockets.ConnectionClosed):
							# Client disconnected, close target connection
							logger.debug(
								"Client disconnected, closing target connection"
							)
							try:
								await target_ws.close()
							except Exception:
								pass
						except Exception as e:
							logger.error(f"Error forwarding client message: {e}")
							raise

					async def forward_target_to_client():
						try:
							async for message in target_ws:
								if isinstance(message, str):
									await websocket.send_text(message)
								else:
									await websocket.send_bytes(message)
						except (WebSocketDisconnect, websockets.ConnectionClosed) as e:
							# Client or target disconnected, stop forwarding
							logger.debug(
								"Connection closed, stopping forward_target_to_client"
							)
							# If target disconnected, close client connection
							if isinstance(e, websockets.ConnectionClosed):
								try:
									await websocket.close()
								except Exception:
									pass
						except Exception as e:
							logger.error(f"Error forwarding target message: {e}")
							raise

					# Run both forwarding tasks concurrently
					# If one side closes, the other will detect it and stop gracefully
					await asyncio.gather(
						forward_client_to_target(),
						forward_target_to_client(),
						return_exceptions=True,
					)
				finally:
					self._active_websockets.discard(target_ws)

		except (websockets.WebSocketException, websockets.ConnectionClosedError) as e:
			logger.error(f"WebSocket proxy connection failed: {e}")
			await websocket.close(
				code=1014,  # Bad Gateway
				reason="Bad Gateway: Could not connect to React Router server",
			)
		except Exception as e:
			logger.error(f"WebSocket proxy error: {e}")
			await websocket.close(
				code=1011,  # Internal Server Error
				reason="Bad Gateway: Proxy error",
			)

	async def close(self):
		"""Close the HTTP client."""
		self._closing.set()
		for response in list(self._active_responses):
			self._active_responses.discard(response)
			with suppress(Exception):
				await response.aclose()
		for websocket in list(self._active_websockets):
			self._active_websockets.discard(websocket)
			with suppress(Exception):
				await websocket.close()
		if self._client is not None:
			await self._client.aclose()


class ReactProxy(_ReactProxyBase):
	"""
	Handles proxying HTTP requests and WebSocket connections to React Router server.

	In single-server mode, the Python server proxies unmatched routes to the React
	dev server. This proxy rewrites URLs in responses to use the external server
	address instead of the internal React server address.
	"""

	async def __call__(self, request: Request) -> Response:
		"""
		Forward HTTP request to React Router server and stream response back.
		"""
		# Build target URL
		url = self.react_server_address.rstrip("/") + request.url.path
		if request.url.query:
			url += "?" + request.url.query

		# Extract headers, skip host header (will be set by httpx)
		headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
		ctx = PulseContext.get()
		session = ctx.session
		if session is not None:
			session_cookie = session.get_cookie_value(ctx.app.cookie.name)
			if session_cookie:
				existing = parse_cookie_header(headers.get("cookie"))
				if existing.get(ctx.app.cookie.name) != session_cookie:
					existing[ctx.app.cookie.name] = session_cookie
					headers["cookie"] = "; ".join(
						f"{key}={value}" for key, value in existing.items()
					)

		try:
			# Build request
			req = self.client.build_request(
				method=request.method,
				url=url,
				headers=headers,
				content=request.stream(),
			)

			# Send request with streaming
			r = await self.client.send(req, stream=True)
			self._active_responses.add(r)

			# Rewrite headers that may contain internal React server URLs
			response_headers: dict[str, str] = {}
			for k, v in r.headers.items():
				if k.lower() in ("location", "content-location"):
					v = self.rewrite_url(v)
				response_headers[k] = v

			async def _wait_disconnect() -> None:
				while True:
					if self._closing.is_set():
						return
					if await request.is_disconnected():
						return
					await asyncio.sleep(_DISCONNECT_POLL_INTERVAL)

			async def _iter() -> AsyncGenerator[bytes, None]:
				disconnect_task: asyncio.Task[None] = asyncio.create_task(
					_wait_disconnect()
				)
				aiter = r.aiter_raw().__aiter__()
				closed = False

				async def _next_chunk() -> bytes:
					return await aiter.__anext__()

				try:
					while True:
						next_chunk_task: asyncio.Task[bytes] = asyncio.create_task(
							_next_chunk()
						)
						done, _ = await asyncio.wait(
							{next_chunk_task, disconnect_task},
							return_when=asyncio.FIRST_COMPLETED,
						)
						if disconnect_task in done:
							if next_chunk_task.done():
								with suppress(
									StopAsyncIteration,
									asyncio.CancelledError,
									Exception,
								):
									next_chunk_task.result()
							else:
								next_chunk_task.cancel()
								with suppress(asyncio.CancelledError):
									await next_chunk_task
							await r.aclose()
							closed = True
							break
						try:
							chunk = next_chunk_task.result()
						except StopAsyncIteration:
							break
						if disconnect_task.done():
							break
						yield chunk
						if await request.is_disconnected():
							await r.aclose()
							closed = True
							break
				finally:
					disconnect_task.cancel()
					with suppress(asyncio.CancelledError):
						await disconnect_task
					if not closed:
						await r.aclose()
					self._active_responses.discard(r)

			return StreamingResponse(
				_iter(),
				status_code=r.status_code,
				headers=response_headers,
			)

		except httpx.RequestError as e:
			logger.error(f"Proxy request failed: {e}")
		return PlainTextResponse(
			"Bad Gateway: Could not reach React Router server", status_code=502
		)


class ReactAsgiProxy(_ReactProxyBase):
	"""
	ASGI-level proxy for React Router requests.
	"""

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			return

		path = scope.get("path", "")
		query_string = scope.get("query_string", b"")
		url = self.react_server_address.rstrip("/") + path
		if query_string:
			url += "?" + query_string.decode("latin-1")

		headers: list[tuple[str, str]] = []
		cookie_header: str | None = None
		raw_headers = cast(list[tuple[bytes, bytes]], scope.get("headers") or [])
		for key, value in raw_headers:
			key_str = key.decode("latin-1")
			if key_str.lower() == "host":
				continue
			value_str = value.decode("latin-1")
			if key_str.lower() == "cookie":
				cookie_header = value_str
				continue
			headers.append((key_str, value_str))

		ctx = PulseContext.get()
		session = ctx.session
		if session is not None:
			session_cookie = session.get_cookie_value(ctx.app.cookie.name)
			if session_cookie:
				existing = parse_cookie_header(cookie_header)
				if existing.get(ctx.app.cookie.name) != session_cookie:
					existing[ctx.app.cookie.name] = session_cookie
				cookie_header = "; ".join(
					f"{key}={value}" for key, value in existing.items()
				)
		if cookie_header:
			headers.append(("cookie", cookie_header))

		receive_queue: asyncio.Queue[Message] = asyncio.Queue()
		disconnect_event = asyncio.Event()

		async def _pump_receive() -> None:
			while True:
				message = await receive()
				await receive_queue.put(message)
				if message["type"] == "http.disconnect":
					disconnect_event.set()
					return

		receive_task = asyncio.create_task(_pump_receive())

		async def _body() -> AsyncGenerator[bytes, None]:
			while True:
				message = await receive_queue.get()
				if message["type"] == "http.disconnect":
					disconnect_event.set()
					return
				if message["type"] != "http.request":
					continue
				body = message.get("body", b"")
				if body:
					yield body
				if not message.get("more_body", False):
					return

		try:
			req = self.client.build_request(
				method=scope["method"],
				url=url,
				headers=headers,
				content=_body(),
			)
			r = await self.client.send(req, stream=True)
		except httpx.RequestError as e:
			logger.error(f"Proxy request failed: {e}")
			await send(
				{
					"type": "http.response.start",
					"status": 502,
					"headers": [(b"content-type", b"text/plain; charset=utf-8")],
				}
			)
			await send(
				{
					"type": "http.response.body",
					"body": b"Bad Gateway: Could not reach React Router server",
					"more_body": False,
				}
			)
			receive_task.cancel()
			with suppress(asyncio.CancelledError):
				await receive_task
			return

		self._active_responses.add(r)

		response_headers: list[tuple[bytes, bytes]] = []
		for key, value in r.headers.multi_items():
			if key.lower() in ("location", "content-location"):
				value = self.rewrite_url(value)
			response_headers.append((key.encode("latin-1"), value.encode("latin-1")))

		try:
			await send(
				{
					"type": "http.response.start",
					"status": r.status_code,
					"headers": response_headers,
				}
			)
		except Exception:
			await r.aclose()
			self._active_responses.discard(r)
			receive_task.cancel()
			with suppress(asyncio.CancelledError):
				await receive_task
			return

		disconnect_task = asyncio.create_task(disconnect_event.wait())
		aiter = r.aiter_raw().__aiter__()

		async def _next_chunk() -> bytes:
			return await aiter.__anext__()

		try:
			while True:
				next_chunk_task: asyncio.Task[bytes] = asyncio.create_task(
					_next_chunk()
				)
				done, _ = await asyncio.wait(
					{next_chunk_task, disconnect_task},
					return_when=asyncio.FIRST_COMPLETED,
				)
				if disconnect_task in done:
					if not next_chunk_task.done():
						next_chunk_task.cancel()
						with suppress(asyncio.CancelledError):
							await next_chunk_task
					break
				try:
					chunk = next_chunk_task.result()
				except StopAsyncIteration:
					break
				if disconnect_event.is_set():
					break
				await send(
					{
						"type": "http.response.body",
						"body": chunk,
						"more_body": True,
					}
				)
			if not disconnect_event.is_set():
				await send(
					{
						"type": "http.response.body",
						"body": b"",
						"more_body": False,
					}
				)
		finally:
			disconnect_task.cancel()
			with suppress(asyncio.CancelledError):
				await disconnect_task
			receive_task.cancel()
			with suppress(asyncio.CancelledError):
				await receive_task
			await r.aclose()
			self._active_responses.discard(r)
