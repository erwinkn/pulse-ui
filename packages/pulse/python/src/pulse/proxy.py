"""
Proxy handler for forwarding requests to React Router server in single-server mode.
"""

import logging
from typing import Callable

import httpx
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

logger = logging.getLogger(__name__)


class ReactProxyHandler:
	"""
	Handles proxying HTTP requests to React Router server.
	"""

	get_react_server_address: Callable[[], str | None]
	_client: httpx.AsyncClient | None

	def __init__(self, get_react_server_address: Callable[[], str | None]):
		"""
		Args:
		    get_react_server_address: Callable that returns the React Router server full URL (or None if not started)
		"""
		self.get_react_server_address = get_react_server_address
		self._client = None

	@property
	def client(self) -> httpx.AsyncClient:
		"""Lazy initialization of HTTP client."""
		if self._client is None:
			self._client = httpx.AsyncClient(
				timeout=httpx.Timeout(30.0),
				follow_redirects=False,
			)
		return self._client

	async def __call__(self, request: Request) -> Response:
		"""
		Forward HTTP request to React Router server and stream response back.
		"""
		# Get the React server address
		react_server_address = self.get_react_server_address()
		if react_server_address is None:
			# React server not started yet, return error
			return PlainTextResponse(
				"Service Unavailable: React server not ready", status_code=503
			)

		# Build target URL
		url = react_server_address.rstrip("/") + request.url.path
		if request.url.query:
			url += "?" + request.url.query

		# Extract headers, skip host header (will be set by httpx)
		headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

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

			# Filter out headers that shouldn't be present in streaming responses
			response_headers = {
				k: v
				for k, v in r.headers.items()
				# if k.lower() not in ("content-length", "transfer-encoding")
			}

			return StreamingResponse(
				r.aiter_raw(),
				background=BackgroundTask(r.aclose),
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
