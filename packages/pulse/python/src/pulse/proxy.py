"""
ASGI proxy for forwarding requests to the React Router server in single-server mode.

Design goals:
- ASGI-only surface area.
- Avoid upstream cookie persistence and connection/stream leaks.
- Shut down cleanly even with open dev connections.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Iterable
from contextlib import suppress
from typing import Any, cast

import aiohttp
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocket, WebSocketDisconnect

from pulse.context import PulseContext
from pulse.cookies import parse_cookie_header

logger = logging.getLogger(__name__)

# Streaming/concurrency defaults, informed by asgiproxy.
_INCOMING_STREAMING_THRESHOLD = 512 * 1024
_OUTGOING_STREAMING_THRESHOLD = 5 * 1024 * 1024
_STREAM_CHUNK_SIZE = 512 * 1024
_MAX_CONCURRENCY_DEFAULT = 20

# Hop-by-hop headers should not be proxied per RFC 7230.
_HOP_BY_HOP_HEADERS = {
	"connection",
	"keep-alive",
	"proxy-authenticate",
	"proxy-authorization",
	"te",
	"trailers",
	"transfer-encoding",
	"upgrade",
}

# WebSocket-specific headers to drop when dialing upstream.
_WEBSOCKET_EXCLUDED_HEADERS = {
	"host",
	"upgrade",
	"connection",
	"sec-websocket-key",
	"sec-websocket-version",
	"sec-websocket-protocol",
	"sec-websocket-extensions",
}

_URL_REWRITE_HEADERS = {"location", "content-location"}


def _http_to_ws_url(http_url: str) -> str:
	if http_url.startswith("https://"):
		return http_url.replace("https://", "wss://", 1)
	if http_url.startswith("http://"):
		return http_url.replace("http://", "ws://", 1)
	return http_url


def _decode_header(value: bytes) -> str:
	return value.decode("latin-1")


def _encode_header(value: str) -> bytes:
	return value.encode("latin-1")


class _ReactProxyBase:
	"""Shared proxy helpers, lifecycle, and WebSocket forwarding."""

	react_server_address: str
	server_address: str
	max_concurrency: int
	_session: aiohttp.ClientSession | None
	_active_responses: set[aiohttp.ClientResponse]
	_active_websockets: set[aiohttp.ClientWebSocketResponse]
	_tasks: set[asyncio.Task[Any]]
	_closing: asyncio.Event

	def __init__(
		self,
		react_server_address: str,
		server_address: str,
		*,
		max_concurrency: int = _MAX_CONCURRENCY_DEFAULT,
	) -> None:
		"""
		Args:
		    react_server_address: Internal React Router server URL (e.g., http://localhost:5173)
		    server_address: External server URL exposed to clients (e.g., http://localhost:8000)
		    max_concurrency: Guard against upstream overload and runaway tasks.
		"""
		self.react_server_address = react_server_address
		self.server_address = server_address
		self.max_concurrency = max_concurrency
		self._session = None
		self._active_responses = set()
		self._active_websockets = set()
		self._tasks = set()
		self._closing = asyncio.Event()

	def _track_task(self, task: asyncio.Task[Any]) -> None:
		self._tasks.add(task)
		task.add_done_callback(self._tasks.discard)

	def rewrite_url(self, url: str) -> str:
		"""Rewrite internal React server URLs to external server address."""
		if self.react_server_address in url:
			return url.replace(self.react_server_address, self.server_address)
		return url

	@property
	def session(self) -> aiohttp.ClientSession:
		"""Lazy initialization of upstream HTTP/WebSocket client session."""
		if self._session is None:
			# Keep connect timeouts; avoid total/read timeouts for long streams.
			timeout = aiohttp.ClientTimeout(total=None, sock_connect=30)
			connector = aiohttp.TCPConnector(
				limit=self.max_concurrency,
				limit_per_host=self.max_concurrency,
			)
			self._session = aiohttp.ClientSession(
				connector=connector,
				cookie_jar=aiohttp.DummyCookieJar(),
				auto_decompress=False,
				timeout=timeout,
			)
		return self._session

	def _determine_incoming_streaming(
		self, method: str, content_length: int | None
	) -> bool:
		if method in ("GET", "HEAD"):
			return False
		if content_length is None:
			return True
		return content_length > _INCOMING_STREAMING_THRESHOLD

	def _determine_outgoing_streaming(self, response: aiohttp.ClientResponse) -> bool:
		if response.status != 200:
			return False
		content_length = response.headers.get("content-length")
		if not content_length:
			return True
		try:
			return int(content_length) > _OUTGOING_STREAMING_THRESHOLD
		except Exception:
			return True

	def _rewrite_raw_headers(
		self, raw_headers: Iterable[tuple[bytes, bytes]]
	) -> list[tuple[bytes, bytes]]:
		result: list[tuple[bytes, bytes]] = []
		for key_bytes, value_bytes in raw_headers:
			key = _decode_header(key_bytes)
			key_lower = key.lower()
			if key_lower in _HOP_BY_HOP_HEADERS:
				continue
			value = _decode_header(value_bytes)
			if key_lower in _URL_REWRITE_HEADERS:
				value = self.rewrite_url(value)
			result.append((key_bytes, _encode_header(value)))
		return result

	def _merge_session_cookie(
		self, cookie_header: str | None, cookie_name: str, cookie_value: str | None
	) -> str | None:
		if not cookie_value:
			return cookie_header
		existing = parse_cookie_header(cookie_header)
		if existing.get(cookie_name) == cookie_value:
			return cookie_header
		existing[cookie_name] = cookie_value
		return "; ".join(f"{key}={value}" for key, value in existing.items())

	async def proxy_websocket(self, websocket: WebSocket) -> None:
		"""Proxy a WebSocket connection to the React Router dev server."""
		if self._closing.is_set():
			await websocket.close(code=1012, reason="Proxy shutting down")
			return

		ws_url = _http_to_ws_url(self.react_server_address)
		target_url = ws_url.rstrip("/") + websocket.url.path
		if websocket.url.query:
			target_url += "?" + websocket.url.query

		# Prefer negotiated subprotocols from ASGI scope.
		scope_subprotocols = cast(list[str] | None, websocket.scope.get("subprotocols"))
		subprotocols = list(scope_subprotocols or [])
		if not subprotocols:
			subprotocol_header = websocket.headers.get("sec-websocket-protocol")
			if subprotocol_header:
				subprotocols = [
					p.strip() for p in subprotocol_header.split(",") if p.strip()
				]

		headers: list[tuple[str, str]] = []
		cookie_header: str | None = None
		for key, value in websocket.headers.items():
			key_lower = key.lower()
			if key_lower in _WEBSOCKET_EXCLUDED_HEADERS:
				continue
			if key_lower in _HOP_BY_HOP_HEADERS:
				continue
			if key_lower == "cookie":
				cookie_header = value
				continue
			headers.append((key, value))

		ctx = PulseContext.get()
		session = ctx.session
		if session is not None:
			session_cookie = session.get_cookie_value(ctx.app.cookie.name)
			cookie_header = self._merge_session_cookie(
				cookie_header,
				ctx.app.cookie.name,
				session_cookie,
			)
		if cookie_header:
			headers.append(("cookie", cookie_header))

		upstream_ws: aiohttp.ClientWebSocketResponse | None = None
		client_to_upstream_task: asyncio.Task[Any] | None = None
		upstream_to_client_task: asyncio.Task[Any] | None = None

		try:
			upstream_ws = await self.session.ws_connect(
				target_url,
				headers=headers,
				protocols=subprotocols,
			)
			self._active_websockets.add(upstream_ws)

			await websocket.accept(subprotocol=upstream_ws.protocol)

			async def _client_to_upstream() -> None:
				assert upstream_ws is not None
				while not self._closing.is_set():
					try:
						message = await websocket.receive()
					except WebSocketDisconnect:
						return
					message_type = message.get("type")
					if message_type == "websocket.disconnect":
						return
					if message_type != "websocket.receive":
						continue
					text = message.get("text")
					if text is not None:
						await upstream_ws.send_str(text)
						continue
					data = message.get("bytes")
					if data is not None:
						await upstream_ws.send_bytes(data)

			async def _upstream_to_client() -> None:
				assert upstream_ws is not None
				while not self._closing.is_set():
					msg = await upstream_ws.receive()
					msg_type = msg.type
					if msg_type == aiohttp.WSMsgType.TEXT:
						await websocket.send_text(msg.data)
						continue
					if msg_type == aiohttp.WSMsgType.BINARY:
						await websocket.send_bytes(msg.data)
						continue
					if msg_type in (
						aiohttp.WSMsgType.CLOSE,
						aiohttp.WSMsgType.CLOSED,
						aiohttp.WSMsgType.CLOSING,
					):
						return
					if msg_type == aiohttp.WSMsgType.ERROR:
						exc = upstream_ws.exception()
						if exc:
							logger.debug("Upstream websocket error", exc_info=exc)
						return

			client_to_upstream_task = asyncio.create_task(_client_to_upstream())
			upstream_to_client_task = asyncio.create_task(_upstream_to_client())
			self._track_task(client_to_upstream_task)
			self._track_task(upstream_to_client_task)

			done, pending = await asyncio.wait(
				{client_to_upstream_task, upstream_to_client_task},
				return_when=asyncio.FIRST_COMPLETED,
			)
			for task in pending:
				task.cancel()
			with suppress(Exception):
				await asyncio.gather(*pending, return_exceptions=True)
			# Surface unexpected errors from the completed task.
			for task in done:
				exc = task.exception()
				if exc and not isinstance(exc, asyncio.CancelledError):
					raise exc

		except aiohttp.ClientError as exc:
			logger.error("WebSocket proxy connection failed: %s", exc)
			with suppress(asyncio.CancelledError, Exception):
				await websocket.close(
					code=1014,
					reason="Bad Gateway: Could not connect to React Router server",
				)
		except Exception as exc:
			logger.error("WebSocket proxy error: %s", exc)
			with suppress(asyncio.CancelledError, Exception):
				await websocket.close(code=1011, reason="Bad Gateway: Proxy error")
		finally:
			if client_to_upstream_task is not None:
				client_to_upstream_task.cancel()
				with suppress(asyncio.CancelledError, Exception):
					await client_to_upstream_task
			if upstream_to_client_task is not None:
				upstream_to_client_task.cancel()
				with suppress(asyncio.CancelledError, Exception):
					await upstream_to_client_task
			if upstream_ws is not None:
				self._active_websockets.discard(upstream_ws)
				with suppress(asyncio.CancelledError, Exception):
					await upstream_ws.close()
			with suppress(asyncio.CancelledError, Exception):
				await websocket.close()

	async def close(self) -> None:
		"""Stop accepting work, cancel tasks, and close upstream resources."""
		self._closing.set()

		tasks = list(self._tasks)
		for task in tasks:
			task.cancel()
		if tasks:
			with suppress(Exception):
				await asyncio.gather(*tasks, return_exceptions=True)
		self._tasks.clear()

		for response in list(self._active_responses):
			self._active_responses.discard(response)
			with suppress(Exception):
				response.close()

		for websocket in list(self._active_websockets):
			self._active_websockets.discard(websocket)
			with suppress(Exception):
				await websocket.close()

		if self._session is not None:
			with suppress(Exception):
				await self._session.close()
			self._session = None


class ReactProxy(_ReactProxyBase):
	"""ASGI-level proxy for React Router HTTP requests."""

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			return
		if self._closing.is_set():
			await send(
				{
					"type": "http.response.start",
					"status": 503,
					"headers": [(b"content-type", b"text/plain; charset=utf-8")],
				}
			)
			await send(
				{
					"type": "http.response.body",
					"body": b"Service Unavailable: Proxy shutting down",
					"more_body": False,
				}
			)
			return

		path = scope.get("path", "")
		query_string = scope.get("query_string", b"")
		url = self.react_server_address.rstrip("/") + path
		if query_string:
			url += "?" + query_string.decode("latin-1")

		raw_headers = cast(list[tuple[bytes, bytes]], scope.get("headers") or [])
		headers: list[tuple[str, str]] = []
		cookie_header: str | None = None
		content_length: int | None = None
		for key_bytes, value_bytes in raw_headers:
			key = _decode_header(key_bytes)
			key_lower = key.lower()
			if key_lower == "host":
				continue
			if key_lower in _HOP_BY_HOP_HEADERS:
				continue
			value = _decode_header(value_bytes)
			if key_lower == "cookie":
				cookie_header = value
				continue
			if key_lower == "content-length":
				try:
					content_length = int(value)
				except Exception:
					content_length = None
			headers.append((key, value))

		ctx = PulseContext.get()
		session = ctx.session
		if session is not None:
			session_cookie = session.get_cookie_value(ctx.app.cookie.name)
			cookie_header = self._merge_session_cookie(
				cookie_header,
				ctx.app.cookie.name,
				session_cookie,
			)
		if cookie_header:
			headers.append(("cookie", cookie_header))

		disconnect_event = asyncio.Event()
		body_complete = asyncio.Event()

		async def _stream_body() -> AsyncGenerator[bytes, None]:
			try:
				while not self._closing.is_set():
					message = await receive()
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
			finally:
				body_complete.set()

		async def _read_full_body() -> bytes:
			parts: list[bytes] = []
			try:
				while not self._closing.is_set():
					message = await receive()
					if message["type"] == "http.disconnect":
						disconnect_event.set()
						return b""
					if message["type"] != "http.request":
						continue
					body = message.get("body", b"")
					if body:
						parts.append(body)
					if not message.get("more_body", False):
						break
				return b"".join(parts)
			finally:
				body_complete.set()

		async def _watch_disconnect() -> None:
			await body_complete.wait()
			if disconnect_event.is_set() or self._closing.is_set():
				return
			while not self._closing.is_set():
				message = await receive()
				if message["type"] == "http.disconnect":
					disconnect_event.set()
					return
				if message["type"] != "http.request":
					continue
				if not message.get("more_body", False):
					continue

		watch_task = asyncio.create_task(_watch_disconnect())
		self._track_task(watch_task)

		should_stream_incoming = self._determine_incoming_streaming(
			scope["method"], content_length
		)
		if should_stream_incoming:
			headers = [
				(key, value)
				for key, value in headers
				if key.lower() != "content-length"
			]

		data: AsyncGenerator[bytes, None] | bytes | None = None
		if scope["method"] not in ("GET", "HEAD"):
			if should_stream_incoming:
				data = _stream_body()
			else:
				data = await _read_full_body()

			if disconnect_event.is_set() or self._closing.is_set():
				watch_task.cancel()
				with suppress(asyncio.CancelledError, Exception):
					await watch_task
				return
		else:
			body_complete.set()

		proxy_response: aiohttp.ClientResponse | None = None
		request_task = asyncio.create_task(
			self.session.request(
				method=scope["method"],
				url=url,
				headers=headers,
				data=data,
				allow_redirects=False,
			)
		)
		self._track_task(request_task)
		disconnect_task = asyncio.create_task(disconnect_event.wait())
		closing_task = asyncio.create_task(self._closing.wait())
		self._track_task(disconnect_task)
		self._track_task(closing_task)

		try:
			done, pending = await asyncio.wait(
				{request_task, disconnect_task, closing_task},
				return_when=asyncio.FIRST_COMPLETED,
			)
			if request_task not in done:
				request_task.cancel()
				with suppress(asyncio.CancelledError, Exception):
					await request_task
				for task in pending:
					task.cancel()
				for task in pending:
					with suppress(asyncio.CancelledError, Exception):
						await task
				watch_task.cancel()
				with suppress(asyncio.CancelledError, Exception):
					await watch_task
				return
			proxy_response = request_task.result()
		except asyncio.CancelledError:
			disconnect_task.cancel()
			closing_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await asyncio.gather(
					disconnect_task, closing_task, return_exceptions=True
				)
			watch_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await watch_task
			raise
		except aiohttp.ClientError as exc:
			logger.error("Proxy request failed: %s", exc)
			disconnect_task.cancel()
			closing_task.cancel()
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
			with suppress(asyncio.CancelledError, Exception):
				await asyncio.gather(
					disconnect_task, closing_task, return_exceptions=True
				)
			watch_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await watch_task
			return

		assert proxy_response is not None
		if disconnect_event.is_set() or self._closing.is_set():
			proxy_response.close()
			disconnect_task.cancel()
			closing_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await asyncio.gather(
					disconnect_task, closing_task, return_exceptions=True
				)
			watch_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await watch_task
			return
		self._active_responses.add(proxy_response)

		response_headers = self._rewrite_raw_headers(proxy_response.raw_headers)
		try:
			await send(
				{
					"type": "http.response.start",
					"status": proxy_response.status,
					"headers": response_headers,
				}
			)
		except Exception:
			proxy_response.close()
			self._active_responses.discard(proxy_response)
			disconnect_task.cancel()
			closing_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await asyncio.gather(
					disconnect_task, closing_task, return_exceptions=True
				)
			watch_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await watch_task
			return

		should_stream_outgoing = self._determine_outgoing_streaming(proxy_response)
		if not should_stream_outgoing:
			try:
				body = await proxy_response.read()
				await send(
					{
						"type": "http.response.body",
						"body": body,
						"more_body": False,
					}
				)
			finally:
				disconnect_task.cancel()
				closing_task.cancel()
				with suppress(asyncio.CancelledError, Exception):
					await asyncio.gather(
						disconnect_task, closing_task, return_exceptions=True
					)
				watch_task.cancel()
				with suppress(asyncio.CancelledError, Exception):
					await watch_task
				proxy_response.close()
				self._active_responses.discard(proxy_response)
			return

		aiter = proxy_response.content.iter_chunked(_STREAM_CHUNK_SIZE).__aiter__()

		async def _next_chunk() -> bytes:
			return await aiter.__anext__()

		try:
			while True:
				next_chunk_task = asyncio.create_task(_next_chunk())
				self._track_task(next_chunk_task)
				done, _ = await asyncio.wait(
					{next_chunk_task, disconnect_task, closing_task},
					return_when=asyncio.FIRST_COMPLETED,
				)
				if disconnect_task in done or closing_task in done:
					if not next_chunk_task.done():
						next_chunk_task.cancel()
						with suppress(asyncio.CancelledError, Exception):
							await next_chunk_task
					break
				try:
					chunk = next_chunk_task.result()
				except StopAsyncIteration:
					break
				if disconnect_event.is_set() or self._closing.is_set():
					break
				await send(
					{
						"type": "http.response.body",
						"body": chunk,
						"more_body": True,
					}
				)
			if not disconnect_event.is_set() and not self._closing.is_set():
				await send(
					{
						"type": "http.response.body",
						"body": b"",
						"more_body": False,
					}
				)
		finally:
			disconnect_task.cancel()
			closing_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await disconnect_task
			with suppress(asyncio.CancelledError, Exception):
				await closing_task
			watch_task.cancel()
			with suppress(asyncio.CancelledError, Exception):
				await watch_task
			proxy_response.close()
			self._active_responses.discard(proxy_response)


# Backwards-friendly alias inside the repo; ASGI-only implementation.
class ReactAsgiProxy(ReactProxy):
	pass
