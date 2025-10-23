"""
Proxy ASGI app for forwarding requests to React Router server in single-server mode.
"""

import logging
from collections.abc import Iterable
from typing import Callable, cast

import httpx
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class PulseProxy:
	"""
	ASGI app that proxies non-API requests to React Router server.

	In single-server mode, Python FastAPI handles /_pulse/* routes and
	proxies everything else to the React Router server running on an internal port.
	"""

	def __init__(
		self,
		app: ASGIApp,
		get_web_port: Callable[[], int | None],
		api_prefix: str = "/_pulse",
	):
		"""
		Initialize proxy ASGI app.

		Args:
		    app: The ASGI application to wrap (socketio.ASGIApp)
		    get_web_port: Callable that returns the React Router port (or None if not started)
		    api_prefix: Prefix for API routes that should NOT be proxied (default: "/_pulse")
		"""
		self.app: ASGIApp = app
		self.get_web_port: Callable[[], int | None] = get_web_port
		self.api_prefix: str = api_prefix
		self._client: httpx.AsyncClient | None = None

	@property
	def client(self) -> httpx.AsyncClient:
		"""Lazy initialization of HTTP client."""
		if self._client is None:
			self._client = httpx.AsyncClient(
				timeout=httpx.Timeout(30.0),
				follow_redirects=False,
			)
		return self._client

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		"""
		ASGI application handler.

		Routes starting with api_prefix or WebSocket connections go to FastAPI.
		Everything else is proxied to React Router.
		"""
		if scope["type"] != "http":
			# Pass through non-HTTP requests (WebSocket, lifespan, etc.)
			await self.app(scope, receive, send)
			return

		path = scope["path"]

		# Check if path starts with API prefix or is a WebSocket upgrade
		if path.startswith(self.api_prefix):
			# This is an API route, pass through to FastAPI
			await self.app(scope, receive, send)
			return

		# Check if this is a WebSocket upgrade request (even if not prefixed)
		headers = Headers(scope=scope)
		if headers.get("upgrade", "").lower() == "websocket":
			# WebSocket request, pass through to FastAPI
			await self.app(scope, receive, send)
			return

		# Proxy to React Router server
		await self._proxy_request(scope, receive, send)

	async def _proxy_request(self, scope: Scope, receive: Receive, send: Send) -> None:
		"""
		Forward HTTP request to React Router server and stream response back.
		"""
		# Get the web server port
		port = self.get_web_port()
		if port is None:
			# Web server not started yet, return error
			await send(
				{
					"type": "http.response.start",
					"status": 503,
					"headers": [(b"content-type", b"text/plain")],
				}
			)
			await send(
				{
					"type": "http.response.body",
					"body": b"Service Unavailable: Web server not ready",
				}
			)
			return

		# Build target URL
		path = scope["path"]
		query_string = scope.get("query_string", b"").decode("utf-8")
		target_url = f"http://localhost:{port}"
		target_path = f"{target_url}{path}"
		if query_string:
			target_path += f"?{query_string}"

		# Extract headers
		headers: dict[str, str] = {}
		for name, value in cast(Iterable[tuple[bytes, bytes]], scope["headers"]):
			name = name.decode("latin1")
			value = value.decode("latin1")

			# Skip host header (will be set by httpx)
			if name.lower() == "host":
				continue

			# Collect headers (handle multiple values)
			existing = headers.get(name)
			if existing:
				headers[name] = f"{existing},{value}"
			else:
				headers[name] = value

		# Read request body
		body_parts: list[bytes] = []
		while True:
			message = await receive()
			if message["type"] == "http.request":
				body_parts.append(message.get("body", b""))
				if not message.get("more_body", False):
					break
		body = b"".join(body_parts)

		try:
			# Forward request to React Router
			method = scope["method"]
			response = await self.client.request(
				method=method,
				url=target_path,
				headers=headers,
				content=body,
			)

			# Send response status
			await send(
				{
					"type": "http.response.start",
					"status": response.status_code,
					"headers": [
						(name.encode("latin1"), value.encode("latin1"))
						for name, value in response.headers.items()
					],
				}
			)

			# Stream response body
			await send(
				{
					"type": "http.response.body",
					"body": response.content,
				}
			)

		except httpx.RequestError as e:
			logger.error(f"Proxy request failed: {e}")

			# Send error response
			await send(
				{
					"type": "http.response.start",
					"status": 502,
					"headers": [(b"content-type", b"text/plain")],
				}
			)
			await send(
				{
					"type": "http.response.body",
					"body": b"Bad Gateway: Could not reach React Router server",
				}
			)

	async def close(self):
		"""Close the HTTP client."""
		if self._client is not None:
			await self._client.aclose()
