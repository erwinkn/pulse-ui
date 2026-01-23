"""
Proxy handler for forwarding requests to React Router server in single-server mode.
"""

import asyncio
import logging
from typing import cast

import httpx
import websockets
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.typing import Subprotocol

from pulse.context import PulseContext
from pulse.cookies import parse_cookie_header

logger = logging.getLogger(__name__)


class ReactProxy:
	"""
	Handles proxying HTTP requests and WebSocket connections to React Router server.

	In single-server mode, the Python server proxies unmatched routes to the React
	dev server. This proxy rewrites URLs in responses to use the external server
	address instead of the internal React server address.
	"""

	react_server_address: str
	server_address: str
	_client: httpx.AsyncClient | None

	def __init__(self, react_server_address: str, server_address: str):
		"""
		Args:
		    react_server_address: Internal React Router server URL (e.g., http://localhost:5173)
		    server_address: External server URL exposed to clients (e.g., http://localhost:8000)
		"""
		self.react_server_address = react_server_address
		self.server_address = server_address
		self._client = None

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
				# Accept client connection with the negotiated subprotocol
				await websocket.accept(subprotocol=target_ws.subprotocol)

				# Forward messages bidirectionally
				async def forward_client_to_target():
					try:
						async for message in websocket.iter_text():
							await target_ws.send(message)
					except (WebSocketDisconnect, websockets.ConnectionClosed):
						# Client disconnected, close target connection
						logger.debug("Client disconnected, closing target connection")
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

			# Rewrite headers that may contain internal React server URLs
			response_headers: dict[str, str] = {}
			for k, v in r.headers.items():
				if k.lower() in ("location", "content-location"):
					v = self.rewrite_url(v)
				response_headers[k] = v

			async def _iter():
				try:
					async for chunk in r.aiter_raw():
						if await request.is_disconnected():
							break
						yield chunk
				finally:
					await r.aclose()

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

	async def close(self):
		"""Close the HTTP client."""
		if self._client is not None:
			await self._client.aclose()
