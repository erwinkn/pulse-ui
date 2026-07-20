"""Tests for WebProxy URL rewriting, header handling, and cleanup."""

import asyncio
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from pulse.context import PULSE_CONTEXT, PulseContext
from pulse.proxy import WebProxy, WebProxyConfig
from starlette.datastructures import URL, Headers
from starlette.types import Message


def _make_asgi_scope(
	path: str = "/",
	query: str = "",
	headers: dict[str, str] | None = None,
	method: str = "GET",
	root_path: str = "",
) -> dict[str, Any]:
	return {
		"type": "http",
		"method": method,
		"path": path,
		"query_string": query.encode(),
		"root_path": root_path,
		"headers": [
			(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
		],
		"server": ("localhost", 8000),
		"scheme": "http",
	}


class _StubChunkStream:
	def __init__(
		self,
		chunks: list[bytes],
		*,
		blocker: asyncio.Event | None = None,
		block_after: int | None = None,
	) -> None:
		self._chunks: list[bytes] = chunks
		self._blocker: asyncio.Event | None = blocker
		self._block_after: int | None = block_after

	def iter_chunked(self, chunk_size: int):
		async def _gen():
			for idx, chunk in enumerate(self._chunks):
				if (
					self._blocker is not None
					and self._block_after is not None
					and idx >= self._block_after
				):
					await self._blocker.wait()
				yield chunk

		return _gen()


class _StubResponse:
	def __init__(
		self,
		*,
		status: int,
		raw_headers: list[tuple[bytes, bytes]],
		chunks: list[bytes] | None = None,
		read_body: bytes | None = None,
		content_length: int | None = None,
		blocker: asyncio.Event | None = None,
		block_after: int | None = None,
	) -> None:
		self.status: int = status
		self.raw_headers: list[tuple[bytes, bytes]] = raw_headers
		self.headers: dict[str, str] = {}
		if content_length is not None:
			self.headers["content-length"] = str(content_length)
		body_chunks = list(chunks or [])
		self.content: _StubChunkStream = _StubChunkStream(
			body_chunks,
			blocker=blocker,
			block_after=block_after,
		)
		self._read_body: bytes = (
			read_body if read_body is not None else b"".join(body_chunks)
		)
		self.close: MagicMock = MagicMock()

	async def read(self) -> bytes:
		return self._read_body


def _make_session(response: _StubResponse) -> MagicMock:
	session = MagicMock()
	session.request = AsyncMock(return_value=response)
	session.close = AsyncMock()
	return session


async def _run_proxy(
	proxy: WebProxy,
	scope: dict[str, Any],
	*,
	messages: list[Message] | None = None,
	disconnect_event: asyncio.Event | None = None,
	on_send: (Callable[[Message, asyncio.Event], None] | None) = None,
) -> list[Message]:
	pending_messages = list(
		messages or [{"type": "http.request", "body": b"", "more_body": False}]
	)
	disconnect_ready = disconnect_event or asyncio.Event()
	sent: list[Message] = []

	async def receive() -> Message:
		if pending_messages:
			return pending_messages.pop(0)
		await disconnect_ready.wait()
		return {"type": "http.disconnect"}

	async def send(message: Message) -> None:
		sent.append(message)
		if on_send is not None:
			on_send(message, disconnect_ready)

	await proxy(scope, receive, send)
	return sent


class _StubUpstreamWebSocket:
	def __init__(self, ready: asyncio.Event) -> None:
		self.protocol: str = "proto2"
		self._ready: asyncio.Event = ready
		self._receive_calls: int = 0
		self.send_str: AsyncMock = AsyncMock()
		self.send_bytes: AsyncMock = AsyncMock()
		self.close: AsyncMock = AsyncMock()

	def exception(self) -> None:
		return None

	async def receive(self) -> aiohttp.WSMessage:
		self._receive_calls += 1
		if self._receive_calls == 1:
			self._ready.set()
			return aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, "pong", None)
		await asyncio.Event().wait()
		raise RuntimeError("unreachable")


class _StubWebSocket:
	def __init__(
		self,
		*,
		url: str,
		headers: dict[str, str] | None,
		subprotocols: list[str],
		ready: asyncio.Event,
	) -> None:
		self.url: URL = URL(url)
		self.headers: Headers = Headers(headers or {})
		self.scope: dict[str, Any] = {"subprotocols": subprotocols}
		self._ready: asyncio.Event = ready
		self._receive_calls: int = 0
		self.accept_subprotocol: str | None = None
		self.send_text: AsyncMock = AsyncMock()
		self.send_bytes: AsyncMock = AsyncMock()
		self.close: AsyncMock = AsyncMock()

	async def accept(self, subprotocol: str | None = None) -> None:
		self.accept_subprotocol = subprotocol

	async def receive(self) -> Message:
		self._receive_calls += 1
		if self._receive_calls == 1:
			return {"type": "websocket.receive", "text": "ping"}
		await self._ready.wait()
		return {"type": "websocket.disconnect"}


class TestWebProxyUrlRewrite:
	@pytest.mark.parametrize(
		"web_upstream",
		[
			"localhost:5173",
			"ftp://localhost:5173",
			"http://user@localhost:5173",
			"http://localhost:5173/web",
		],
	)
	def test_rejects_invalid_web_upstream(self, web_upstream: str):
		with pytest.raises(ValueError, match="web_upstream"):
			WebProxy(web_upstream)

	def test_rewrites_web_upstream_url(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		assert proxy.rewrite_url("http://localhost:5173/foo") == "/foo"

	def test_rewrites_with_query_string(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		assert proxy.rewrite_url("http://localhost:5173/path?a=1") == "/path?a=1"

	def test_does_not_rewrite_other_urls(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		assert proxy.rewrite_url("http://example.com/foo") == "http://example.com/foo"

	def test_does_not_rewrite_relative_paths(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		assert proxy.rewrite_url("/foo/bar") == "/foo/bar"


class TestWebProxySessionLimits:
	def test_proxy_rejects_invalid_numeric_config(self):
		with pytest.raises(ValueError, match="max_concurrency"):
			WebProxyConfig(max_concurrency=0)
		with pytest.raises(ValueError, match="disconnect_watch_timeout"):
			WebProxyConfig(disconnect_watch_timeout=0)

	@pytest.mark.asyncio
	async def test_session_uses_connector_limits(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
			config=WebProxyConfig(max_concurrency=7),
		)
		session = proxy.session
		connector = session.connector
		assert connector is not None
		assert connector.limit == 7
		assert connector.limit_per_host == 7
		assert session.timeout.sock_connect == 30.0
		await proxy.close()

	@pytest.mark.asyncio
	async def test_session_uses_configured_connect_timeout(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
			config=WebProxyConfig(connect_timeout=3.5),
		)
		assert proxy.session.timeout.sock_connect == 3.5
		await proxy.close()


class TestWebProxyRequestURL:
	@pytest.mark.asyncio
	async def test_preserves_root_path(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			read_body=b"ok",
			content_length=2,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		scope = _make_asgi_scope("/assets/app.js", query="x=1", root_path="/root")
		await _run_proxy(proxy, scope)

		request_args = proxy._session.request.await_args  # pyright: ignore[reportPrivateUsage]
		assert (
			request_args.kwargs["url"] == "http://localhost:5173/root/assets/app.js?x=1"
		)

	@pytest.mark.asyncio
	async def test_forwards_public_host_via_forwarding_headers(self):
		"""The upstream sees its own host; the public host travels in X-Forwarded-*.

		Dev servers with host checks (Vite allowedHosts) must accept proxied
		requests that arrive via tunnels or remote hostnames.
		"""
		proxy = WebProxy(web_upstream="http://localhost:5173")
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			read_body=b"ok",
			content_length=2,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		await _run_proxy(
			proxy,
			_make_asgi_scope("/", headers={"host": "app.example.com"}),
		)

		request_args = proxy._session.request.await_args  # pyright: ignore[reportPrivateUsage]
		headers = request_args.kwargs["headers"]
		assert ("host", "app.example.com") not in headers
		assert ("x-forwarded-host", "app.example.com") in headers
		assert ("x-forwarded-proto", "http") in headers

	@pytest.mark.asyncio
	async def test_preserves_upstream_forwarding_headers(self):
		proxy = WebProxy(web_upstream="http://localhost:5173")
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			read_body=b"ok",
			content_length=2,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		await _run_proxy(
			proxy,
			_make_asgi_scope(
				"/",
				headers={
					"host": "internal:8000",
					"x-forwarded-host": "app.example.com",
					"x-forwarded-proto": "https",
				},
			),
		)

		request_args = proxy._session.request.await_args  # pyright: ignore[reportPrivateUsage]
		headers = request_args.kwargs["headers"]
		assert ("x-forwarded-host", "app.example.com") in headers
		assert ("x-forwarded-proto", "https") in headers
		assert ("host", "internal:8000") not in headers


class TestWebProxyHeaders:
	@pytest.mark.asyncio
	async def test_rewrites_location_header(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=302,
			raw_headers=[
				(b"location", b"http://localhost:5173/login"),
				(b"content-type", b"text/html"),
			],
			read_body=b"",
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		sent = await _run_proxy(proxy, _make_asgi_scope("/"))
		start = next(msg for msg in sent if msg["type"] == "http.response.start")
		headers = {k.decode(): v.decode() for k, v in start["headers"]}
		assert headers["location"] == "/login"
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_rewrites_content_location_header(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[
				(b"content-location", b"http://localhost:5173/resource"),
				(b"content-type", b"application/json"),
			],
			read_body=b"{}",
			content_length=2,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		sent = await _run_proxy(proxy, _make_asgi_scope("/api"))
		start = next(msg for msg in sent if msg["type"] == "http.response.start")
		headers = {k.decode(): v.decode() for k, v in start["headers"]}
		assert headers["content-location"] == "/resource"
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_preserves_other_headers(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[
				(b"content-type", b"text/html; charset=utf-8"),
				(b"x-custom-header", b"some-value"),
			],
			read_body=b"<html></html>",
			content_length=13,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		sent = await _run_proxy(proxy, _make_asgi_scope("/"))
		start = next(msg for msg in sent if msg["type"] == "http.response.start")
		headers = {k.decode(): v.decode() for k, v in start["headers"]}
		assert headers["content-type"] == "text/html; charset=utf-8"
		assert headers["x-custom-header"] == "some-value"
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_preserves_duplicate_set_cookie(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[
				(b"set-cookie", b"a=1; Path=/"),
				(b"set-cookie", b"b=2; Path=/"),
				(b"content-type", b"text/plain"),
			],
			read_body=b"ok",
			content_length=2,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		sent = await _run_proxy(proxy, _make_asgi_scope("/"))
		start = next(msg for msg in sent if msg["type"] == "http.response.start")
		cookies = [
			value.decode()
			for key, value in start["headers"]
			if key.lower() == b"set-cookie"
		]
		assert cookies == ["a=1; Path=/", "b=2; Path=/"]
		assert response.close.call_count >= 1


class TestWebProxyIncomingStreaming:
	@pytest.mark.asyncio
	async def test_streaming_body_not_read_ahead(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			read_body=b"ok",
			content_length=2,
		)
		session = MagicMock()
		session.request = AsyncMock(return_value=response)
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		async def receive() -> Message:
			raise AssertionError("receive called during streaming setup")

		async def send(_: Message) -> None:
			return None

		scope = _make_asgi_scope(
			"/upload",
			method="POST",
			headers={"content-length": str(10 * 1024 * 1024)},
		)
		await proxy(scope, receive, send)

	@pytest.mark.asyncio
	async def test_streaming_body_drops_content_length(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			read_body=b"ok",
			content_length=2,
		)
		captured_headers: list[tuple[str, str]] = []

		async def _request(
			*, headers: list[tuple[str, str]], **_: Any
		) -> _StubResponse:
			captured_headers.extend(headers)
			return response

		session = MagicMock()
		session.request = AsyncMock(side_effect=_request)
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		async def receive() -> Message:
			return {"type": "http.request", "body": b"", "more_body": False}

		async def send(_: Message) -> None:
			return None

		scope = _make_asgi_scope(
			"/upload",
			method="POST",
			headers={"content-length": str(10 * 1024 * 1024)},
		)
		await proxy(scope, receive, send)

		assert all(key.lower() != "content-length" for key, _ in captured_headers)

	@pytest.mark.asyncio
	async def test_disconnect_cancels_upstream_request(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		request_cancelled = asyncio.Event()
		request_started = asyncio.Event()
		wait_forever = asyncio.Event()

		async def _request(*, data: Any | None = None, **_: Any) -> _StubResponse:
			request_started.set()
			if data is not None:
				async for _ in data:
					pass
			try:
				await wait_forever.wait()
			except asyncio.CancelledError:
				request_cancelled.set()
				raise
			raise RuntimeError("unreachable")

		session = MagicMock()
		session.request = AsyncMock(side_effect=_request)
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		messages: list[Message] = [
			{"type": "http.request", "body": b"chunk", "more_body": True},
			{"type": "http.disconnect"},
		]
		sent: list[Message] = []

		async def receive() -> Message:
			if messages:
				return messages.pop(0)
			return {"type": "http.disconnect"}

		async def send(message: Message) -> None:
			sent.append(message)

		scope = _make_asgi_scope(
			"/upload",
			method="POST",
			headers={"content-length": str(10 * 1024 * 1024)},
		)
		await proxy(scope, receive, send)

		assert request_started.is_set()
		assert request_cancelled.is_set()
		assert sent == []


class TestWebProxyStreaming:
	@pytest.mark.asyncio
	async def test_closes_upstream_on_stream_end(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			chunks=[b"one", b"two"],
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		sent = await _run_proxy(proxy, _make_asgi_scope("/"))
		bodies = [msg["body"] for msg in sent if msg["type"] == "http.response.body"]
		assert bodies == [b"one", b"two", b""]
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_terminal_empty_request_does_not_spin_disconnect_watcher(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
			config=WebProxyConfig(
				disconnect_watch_base_sleep=0.05,
				disconnect_watch_max_sleep=0.05,
			),
		)

		async def _request(**_: Any) -> _StubResponse:
			await asyncio.sleep(0.02)
			return _StubResponse(
				status=200,
				raw_headers=[(b"content-type", b"text/plain")],
				read_body=b"ok",
				content_length=2,
			)

		session = MagicMock()
		session.request = AsyncMock(side_effect=_request)
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		receive_count = 0

		async def receive() -> Message:
			nonlocal receive_count
			receive_count += 1
			return {"type": "http.request", "body": b"", "more_body": False}

		async def send(_: Message) -> None:
			return None

		await proxy(_make_asgi_scope("/"), receive, send)

		assert receive_count <= 2

	@pytest.mark.asyncio
	async def test_disconnect_stops_stream_and_closes_upstream(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			chunks=[b"one", b"two", b"three"],
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		def _disconnect_after_first_chunk(
			message: Message, event: asyncio.Event
		) -> None:
			if message["type"] != "http.response.body":
				return
			if message.get("body") == b"one":
				event.set()

		sent = await _run_proxy(
			proxy,
			_make_asgi_scope("/"),
			on_send=_disconnect_after_first_chunk,
		)
		bodies = [msg["body"] for msg in sent if msg["type"] == "http.response.body"]
		assert bodies == [b"one"]
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_disconnect_while_idle_stops_stream(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		blocker = asyncio.Event()
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			chunks=[b"one", b"two"],
			blocker=blocker,
			block_after=1,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		def _disconnect_after_first_chunk(
			message: Message, event: asyncio.Event
		) -> None:
			if message["type"] != "http.response.body":
				return
			if message.get("body") == b"one":
				event.set()

		sent = await _run_proxy(
			proxy,
			_make_asgi_scope("/"),
			on_send=_disconnect_after_first_chunk,
		)
		bodies = [msg["body"] for msg in sent if msg["type"] == "http.response.body"]
		assert bodies == [b"one"]
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_disconnect_race_with_stream_end_retrieves_task_exception(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			chunks=[],
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		loop = asyncio.get_running_loop()
		previous_handler = loop.get_exception_handler()
		unhandled_contexts: list[dict[str, Any]] = []
		disconnect_ready = asyncio.Event()
		sent: list[Message] = []

		async def receive() -> Message:
			await disconnect_ready.wait()
			return {"type": "http.disconnect"}

		async def send(message: Message) -> None:
			sent.append(message)
			if message["type"] == "http.response.start":
				disconnect_ready.set()
				await asyncio.sleep(0)

		try:
			loop.set_exception_handler(
				lambda _loop, context: unhandled_contexts.append(context)
			)
			await proxy(_make_asgi_scope("/"), receive, send)
			await asyncio.sleep(0)
		finally:
			loop.set_exception_handler(previous_handler)

		assert sent == [
			{
				"type": "http.response.start",
				"status": 200,
				"headers": [(b"content-type", b"text/plain")],
			}
		]
		assert not any(
			context.get("message") == "Task exception was never retrieved"
			and isinstance(context.get("exception"), StopAsyncIteration)
			for context in unhandled_contexts
		)
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_send_start_failure_closes_response(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			read_body=b"one",
			content_length=3,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		scope = _make_asgi_scope("/")
		messages = [{"type": "http.request", "body": b"", "more_body": False}]

		async def receive() -> Message:
			if messages:
				return messages.pop(0)
			return {"type": "http.disconnect"}

		async def send(_: Message) -> None:
			raise RuntimeError("send failed")

		await proxy(scope, receive, send)
		assert response.close.call_count >= 1

	@pytest.mark.asyncio
	async def test_close_closes_active_responses(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		blocker = asyncio.Event()
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			chunks=[b"one"],
			blocker=blocker,
			block_after=0,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		scope = _make_asgi_scope("/")
		messages = [{"type": "http.request", "body": b"", "more_body": False}]

		disconnect_event = asyncio.Event()
		sent: list[Message] = []

		async def receive() -> Message:
			if messages:
				return messages.pop(0)
			await disconnect_event.wait()
			return {"type": "http.disconnect"}

		async def send(message: Message) -> None:
			sent.append(message)

		task = asyncio.create_task(proxy(scope, receive, send))
		for _ in range(5):
			if proxy._active_responses:  # pyright: ignore[reportPrivateUsage]
				break
			await asyncio.sleep(0)
		await proxy.close()
		disconnect_event.set()
		await asyncio.wait_for(task, timeout=1)
		assert response.close.call_count >= 1


class TestWebProxyErrors:
	@pytest.mark.asyncio
	async def test_timeout_returns_gateway_timeout(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		session = MagicMock()
		session.request = AsyncMock(side_effect=asyncio.TimeoutError())
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		sent = await _run_proxy(proxy, _make_asgi_scope("/"))

		assert sent[0]["status"] == 504
		assert sent[-1]["type"] == "http.response.body"

	@pytest.mark.asyncio
	async def test_shutdown_returns_service_unavailable(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		request_started = asyncio.Event()
		wait_forever = asyncio.Event()

		async def _request(**_: Any) -> _StubResponse:
			request_started.set()
			await wait_forever.wait()
			return _StubResponse(
				status=200,
				raw_headers=[(b"content-type", b"text/plain")],
				read_body=b"ok",
				content_length=2,
			)

		session = MagicMock()
		session.request = AsyncMock(side_effect=_request)
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		scope = _make_asgi_scope("/")
		messages = [{"type": "http.request", "body": b"", "more_body": False}]
		disconnect_event = asyncio.Event()
		sent: list[Message] = []

		async def receive() -> Message:
			if messages:
				return messages.pop(0)
			await disconnect_event.wait()
			return {"type": "http.disconnect"}

		async def send(message: Message) -> None:
			sent.append(message)

		task = asyncio.create_task(proxy(scope, receive, send))
		await request_started.wait()
		await proxy.close()
		await asyncio.wait_for(task, timeout=1)

		assert sent[0]["status"] == 503
		assert sent[-1]["type"] == "http.response.body"

	@pytest.mark.asyncio
	async def test_shutdown_after_response_ready_returns_service_unavailable(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)

		async def _request(**_: Any) -> _StubResponse:
			proxy._closing.set()  # pyright: ignore[reportPrivateUsage]
			return _StubResponse(
				status=200,
				raw_headers=[(b"content-type", b"text/plain")],
				read_body=b"ok",
				content_length=2,
			)

		session = MagicMock()
		session.request = AsyncMock(side_effect=_request)
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		sent = await _run_proxy(proxy, _make_asgi_scope("/"))

		assert sent[0]["status"] == 503
		assert sent[-1]["type"] == "http.response.body"


class TestWebProxyCleanup:
	@pytest.mark.asyncio
	async def test_request_clears_tracking_sets(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		response = _StubResponse(
			status=200,
			raw_headers=[(b"content-type", b"text/plain")],
			read_body=b"ok",
			content_length=2,
		)
		proxy._session = _make_session(response)  # pyright: ignore[reportPrivateUsage]

		await _run_proxy(proxy, _make_asgi_scope("/"))
		await asyncio.sleep(0)

		assert proxy._active_responses == set()  # pyright: ignore[reportPrivateUsage]
		assert proxy._tasks == set()  # pyright: ignore[reportPrivateUsage]


class TestWebProxyWebSocket:
	@pytest.mark.asyncio
	async def test_call_dispatches_websocket_scope(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		proxy.proxy_websocket = AsyncMock()
		headers: list[tuple[bytes, bytes]] = []
		scope: dict[str, Any] = {
			"type": "websocket",
			"path": "/socket",
			"query_string": b"",
			"headers": headers,
			"scheme": "ws",
			"server": ("localhost", 8000),
			"client": ("127.0.0.1", 1234),
		}

		async def receive() -> Message:
			return {"type": "websocket.disconnect"}

		async def send(_: Message) -> None:
			return None

		await proxy(scope, receive, send)
		assert proxy.proxy_websocket.await_count == 1

	@pytest.mark.asyncio
	async def test_websocket_forwards_text_and_cleans_up(self):
		proxy = WebProxy(
			web_upstream="http://localhost:5173",
		)
		ready = asyncio.Event()
		upstream_ws = _StubUpstreamWebSocket(ready)
		session = MagicMock()
		session.ws_connect = AsyncMock(return_value=upstream_ws)
		session.close = AsyncMock()
		proxy._session = session  # pyright: ignore[reportPrivateUsage]

		app_stub = SimpleNamespace(cookie=SimpleNamespace(name="pulse.sid"))
		ctx = PulseContext(app=app_stub, session=None)  # pyright: ignore[reportArgumentType]
		token = PULSE_CONTEXT.set(ctx)
		try:
			websocket = _StubWebSocket(
				url="ws://client.local/socket?x=1",
				headers={"host": "client.local"},
				subprotocols=["proto1", "proto2"],
				ready=ready,
			)
			await proxy.proxy_websocket(websocket)  # pyright: ignore[reportArgumentType]
		finally:
			PULSE_CONTEXT.reset(token)

		session.ws_connect.assert_awaited()
		ws_args = session.ws_connect.await_args
		assert ws_args.args[0] == "ws://localhost:5173/socket?x=1"
		assert ("host", "client.local") not in ws_args.kwargs["headers"]
		assert ("x-forwarded-host", "client.local") in ws_args.kwargs["headers"]
		assert ("x-forwarded-proto", "http") in ws_args.kwargs["headers"]
		assert ws_args.kwargs["protocols"] == ["proto1", "proto2"]
		assert websocket.accept_subprotocol == "proto2"
		upstream_ws.send_str.assert_awaited_once_with("ping")
		websocket.send_text.assert_awaited_once_with("pong")
		upstream_ws.close.assert_awaited()
		websocket.close.assert_awaited()
		assert upstream_ws not in proxy._active_websockets  # pyright: ignore[reportPrivateUsage]
