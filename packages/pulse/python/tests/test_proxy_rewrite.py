"""Tests for ReactProxy URL rewriting and get_client_address fallback."""

from typing import Any, override
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.responses import StreamingResponse
from pulse.helpers import get_client_address, get_client_address_socketio
from pulse.proxy import ReactProxy
from starlette.requests import Request


class _DisconnectRequest(Request):
	_disconnect_after: int | None
	_disconnect_checks: int

	def __init__(
		self, scope: dict[str, Any], *, disconnect_after: int | None = None
	) -> None:
		async def receive():
			return {"type": "http.request", "body": b"", "more_body": False}

		super().__init__(scope, receive)
		self._disconnect_after = disconnect_after
		self._disconnect_checks = 0

	@override
	async def is_disconnected(self) -> bool:
		if self._disconnect_after is None:
			return False
		self._disconnect_checks += 1
		return self._disconnect_checks > self._disconnect_after


def _make_disconnect_request(
	path: str = "/",
	query: str = "",
	headers: dict[str, str] | None = None,
	*,
	disconnect_after: int | None = None,
) -> _DisconnectRequest:
	scope = {
		"type": "http",
		"method": "GET",
		"path": path,
		"query_string": query.encode(),
		"headers": [
			(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
		],
		"server": ("localhost", 8000),
	}
	return _DisconnectRequest(scope, disconnect_after=disconnect_after)


class TestReactProxyUrlRewrite:
	"""Test ReactProxy._rewrite_url() method."""

	def test_rewrites_react_server_url(self):
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)
		assert (
			proxy.rewrite_url("http://localhost:5173/foo")
			== "http://localhost:8000/foo"
		)

	def test_rewrites_with_query_string(self):
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)
		assert (
			proxy.rewrite_url("http://localhost:5173/path?a=1")
			== "http://localhost:8000/path?a=1"
		)

	def test_does_not_rewrite_other_urls(self):
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)
		assert proxy.rewrite_url("http://example.com/foo") == "http://example.com/foo"

	def test_does_not_rewrite_relative_paths(self):
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)
		assert proxy.rewrite_url("/foo/bar") == "/foo/bar"


class TestGetClientAddressFallback:
	"""Test get_client_address() uses Host header as fallback."""

	def _make_request(self, headers: dict[str, str]) -> Request:
		"""Create a mock Request with given headers."""
		scope = {
			"type": "http",
			"method": "GET",
			"path": "/",
			"query_string": b"",
			"headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
			"server": ("localhost", 8000),
		}
		return Request(scope)

	def test_uses_origin_header_first(self):
		request = self._make_request(
			{"Origin": "http://localhost:8000", "Host": "localhost:9999"}
		)
		assert get_client_address(request) == "http://localhost:8000"

	def test_uses_referer_when_no_origin(self):
		request = self._make_request(
			{"Referer": "http://localhost:8000/page", "Host": "localhost:9999"}
		)
		assert get_client_address(request) == "http://localhost:8000"

	def test_falls_back_to_host_header(self):
		request = self._make_request({"Host": "localhost:8000"})
		result = get_client_address(request)
		assert result == "http://localhost:8000"

	def test_falls_back_to_host_header_with_https(self):
		scope = {
			"type": "http",
			"method": "GET",
			"path": "/",
			"query_string": b"",
			"headers": [(b"host", b"example.com")],
			"server": ("example.com", 443),
			"scheme": "https",
		}
		request = Request(scope)
		result = get_client_address(request)
		assert result == "https://example.com"

	def test_returns_none_when_no_headers(self):
		scope: dict[str, Any] = {
			"type": "http",
			"method": "GET",
			"path": "/",
			"query_string": b"",
			"headers": [],
			"server": ("localhost", 8000),
		}
		request = Request(scope)
		result = get_client_address(request)
		assert result is None


class TestGetClientAddressSocketioFallback:
	"""Test get_client_address_socketio() uses HTTP_HOST as fallback."""

	def test_uses_origin_first(self):
		environ = {
			"HTTP_ORIGIN": "http://localhost:8000",
			"HTTP_HOST": "localhost:9999",
		}
		assert get_client_address_socketio(environ) == "http://localhost:8000"

	def test_falls_back_to_http_host(self):
		environ = {"HTTP_HOST": "localhost:8000", "wsgi.url_scheme": "http"}
		assert get_client_address_socketio(environ) == "http://localhost:8000"

	def test_falls_back_to_http_host_with_https(self):
		environ = {"HTTP_HOST": "example.com", "wsgi.url_scheme": "https"}
		assert get_client_address_socketio(environ) == "https://example.com"

	def test_returns_none_when_no_host(self):
		environ = {"wsgi.url_scheme": "http"}
		assert get_client_address_socketio(environ) is None


class TestReactProxyHeaderRewrite:
	"""Integration test for ReactProxy response header rewriting."""

	def _make_request(self, path: str = "/") -> Request:
		scope = {
			"type": "http",
			"method": "GET",
			"path": path,
			"query_string": b"",
			"headers": [(b"host", b"localhost:8000")],
			"server": ("localhost", 8000),
		}
		return Request(scope)

	@pytest.mark.asyncio
	async def test_rewrites_location_header_in_redirect(self):
		"""Test that Location header in redirect responses is rewritten."""
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)

		# Mock the httpx response with a redirect
		mock_response = MagicMock()
		mock_response.status_code = 302
		mock_response.headers = httpx.Headers(
			{
				"location": "http://localhost:5173/login",
				"content-type": "text/html",
			}
		)

		async def aiter_raw():
			yield b""

		mock_response.aiter_raw = aiter_raw
		mock_response.aclose = AsyncMock()

		# Create a mock client and inject it
		mock_client = MagicMock()
		mock_client.build_request = MagicMock()
		mock_client.send = AsyncMock(return_value=mock_response)
		proxy._client = mock_client  # pyright: ignore[reportPrivateUsage]

		request = self._make_request("/")
		response = await proxy(request)

		# The Location header should be rewritten to use external address
		assert response.headers["location"] == "http://localhost:8000/login"

	@pytest.mark.asyncio
	async def test_rewrites_content_location_header(self):
		"""Test that Content-Location header is rewritten."""
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.headers = httpx.Headers(
			{
				"content-location": "http://localhost:5173/resource",
				"content-type": "application/json",
			}
		)

		async def aiter_raw():
			yield b"{}"

		mock_response.aiter_raw = aiter_raw
		mock_response.aclose = AsyncMock()

		mock_client = MagicMock()
		mock_client.build_request = MagicMock()
		mock_client.send = AsyncMock(return_value=mock_response)
		proxy._client = mock_client  # pyright: ignore[reportPrivateUsage]

		request = self._make_request("/api")
		response = await proxy(request)

		assert response.headers["content-location"] == "http://localhost:8000/resource"

	@pytest.mark.asyncio
	async def test_preserves_other_headers(self):
		"""Test that non-URL headers are passed through unchanged."""
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.headers = httpx.Headers(
			{
				"content-type": "text/html; charset=utf-8",
				"x-custom-header": "some-value",
			}
		)

		async def aiter_raw():
			yield b"<html></html>"

		mock_response.aiter_raw = aiter_raw
		mock_response.aclose = AsyncMock()

		mock_client = MagicMock()
		mock_client.build_request = MagicMock()
		mock_client.send = AsyncMock(return_value=mock_response)
		proxy._client = mock_client  # pyright: ignore[reportPrivateUsage]

		request = self._make_request("/")
		response = await proxy(request)

		assert response.headers["content-type"] == "text/html; charset=utf-8"
		assert response.headers["x-custom-header"] == "some-value"


class TestReactProxyStreaming:
	"""Tests for ReactProxy streaming cleanup."""

	@pytest.mark.asyncio
	async def test_closes_upstream_on_stream_end(self):
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.headers = httpx.Headers({"content-type": "text/plain"})

		async def aiter_raw():
			yield b"one"
			yield b"two"

		mock_response.aiter_raw = aiter_raw
		mock_response.aclose = AsyncMock()

		mock_client = MagicMock()
		mock_client.build_request = MagicMock()
		mock_client.send = AsyncMock(return_value=mock_response)
		proxy._client = mock_client  # pyright: ignore[reportPrivateUsage]

		request = _make_disconnect_request("/")
		response = await proxy(request)
		assert isinstance(response, StreamingResponse)

		chunks = [chunk async for chunk in response.body_iterator]
		assert chunks == [b"one", b"two"]
		mock_response.aclose.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_closes_upstream_on_disconnect(self):
		proxy = ReactProxy(
			react_server_address="http://localhost:5173",
			server_address="http://localhost:8000",
		)

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.headers = httpx.Headers({"content-type": "text/plain"})

		async def aiter_raw():
			yield b"one"
			yield b"two"
			yield b"three"

		mock_response.aiter_raw = aiter_raw
		mock_response.aclose = AsyncMock()

		mock_client = MagicMock()
		mock_client.build_request = MagicMock()
		mock_client.send = AsyncMock(return_value=mock_response)
		proxy._client = mock_client  # pyright: ignore[reportPrivateUsage]

		request = _make_disconnect_request("/", disconnect_after=1)
		response = await proxy(request)
		assert isinstance(response, StreamingResponse)

		chunks = [chunk async for chunk in response.body_iterator]
		assert chunks == [b"one"]
		mock_response.aclose.assert_awaited_once()
