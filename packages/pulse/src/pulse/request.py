from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from http.cookies import SimpleCookie
from typing import Any, cast


def _bytes_kv_to_str(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
	out: dict[str, str] = {}
	for k, v in headers:
		try:
			out[k.decode("latin1").lower()] = v.decode("latin1")
		except Exception:
			# Best effort
			out[str(k).lower()] = str(v)
	return out


class PulseRequest:
	"""Normalized request for both HTTP prerender and Socket.IO connect.

	Provides a minimal, consistent surface:
	  - headers: dict[str, str] (lowercased)
	  - cookies: dict[str, str]
	  - scheme, method, path, query_string, url
	  - client: tuple[str, int] | None
	  - auth: Any | None (only set for Socket.IO connect when provided)
	  - raw: underlying request/scope/environ for advanced users
	"""

	headers: dict[str, str]
	cookies: dict[str, str]
	scheme: str
	method: str
	path: str
	query_string: str
	client: tuple[str, int] | None
	auth: Any | None
	raw: Any | None

	def __init__(
		self,
		*,
		headers: Mapping[str, str] | None = None,
		cookies: Mapping[str, str] | None = None,
		scheme: str | None = None,
		method: str | None = None,
		path: str | None = None,
		query_string: str | None = None,
		client: tuple[str, int] | None = None,
		auth: Any | None = None,
		raw: Any | None = None,
	) -> None:
		self.headers = {k.lower(): v for k, v in (headers or {}).items()}
		self.cookies = dict(cookies or {})
		self.scheme = scheme or ""
		self.method = method or ""
		self.path = path or ""
		self.query_string = query_string or ""
		self.client = client
		self.auth = auth
		self.raw = raw

	@property
	def url(self) -> str:
		qs = f"?{self.query_string}" if self.query_string else ""
		host = self.headers.get("host", "")
		if host:
			return f"{self.scheme or 'http'}://{host}{self.path}{qs}"
		return f"{self.path}{qs}"

	@staticmethod
	def from_fastapi(request: Any) -> PulseRequest:
		# FastAPI/Starlette Request
		headers = {k.lower(): v for k, v in request.headers.items()}
		cookies = dict(request.cookies or {})
		scheme = request.url.scheme
		method = request.method
		path = request.url.path
		query_string = request.url.query or ""
		client = (request.client.host, request.client.port) if request.client else None
		return PulseRequest(
			headers=headers,
			cookies=cookies,
			scheme=scheme,
			method=method,
			path=path,
			query_string=query_string,
			client=client,
			raw=request,
		)

	@staticmethod
	def from_socketio_environ(
		environ: MutableMapping[str, Any], auth: Any | None
	) -> PulseRequest:
		# python-socketio passes a WSGI/ASGI-like environ. Try to detect ASGI scope first.
		scope: MutableMapping[str, Any] = environ.get("asgi.scope") or environ

		headers: dict[str, str] = {}
		cookies: dict[str, str] = {}
		scheme = ""
		method = ""
		path = ""
		query_string = ""
		client: tuple[str, int] | None = None

		if isinstance(scope, Mapping) and "type" in scope:  # ASGI scope
			scheme = scope.get("scheme", "")
			method = scope.get("method", "") or "GET"
			path = scope.get("path", "")
			raw_qs = scope.get("query_string", b"") or b""
			try:
				query_string = raw_qs.decode("latin1")
			except Exception:
				query_string = ""
			asgi_headers = cast(
				list[tuple[bytes, bytes]], scope.get("headers", []) or []
			)
			headers = _bytes_kv_to_str(asgi_headers)
			# Cookies from header if present
			cookie_header = headers.get("cookie")
			if cookie_header:
				sc = SimpleCookie()
				sc.load(cookie_header)
				cookies = {k: v.value for k, v in sc.items()}
			scope_client = scope.get("client")
			if scope_client:
				client = tuple(scope_client)
		else:
			# WSGI-like environ
			scheme = scope.get("wsgi.url_scheme", "") or scope.get("scheme", "")
			method = scope.get("REQUEST_METHOD", "GET")
			path = scope.get("PATH_INFO", "")
			query_string = scope.get("QUERY_STRING", "")
			# headers from HTTP_* keys
			for k, v in scope.items():
				if isinstance(k, str) and k.startswith("HTTP_"):
					name = k[5:].replace("_", "-").lower()
					headers[name] = str(v)
			if "CONTENT_TYPE" in scope:
				headers["content-type"] = str(scope["CONTENT_TYPE"])  # type: ignore
			if "CONTENT_LENGTH" in scope:
				headers["content-length"] = str(scope["CONTENT_LENGTH"])  # type: ignore
			# Cookies
			cookie_header = headers.get("cookie") or scope.get("HTTP_COOKIE")
			if cookie_header:
				sc = SimpleCookie()
				sc.load(cookie_header)  # type: ignore[arg-type]
				cookies = {k: v.value for k, v in sc.items()}
			# client is not standard in WSGI; try remote addr
			remote = scope.get("REMOTE_ADDR")
			port = scope.get("REMOTE_PORT")
			if remote is not None and port is not None:
				try:
					client = (str(remote), int(port))
				except Exception:
					client = None

		return PulseRequest(
			headers=headers,
			cookies=cookies,
			scheme=scheme,
			method=method,
			path=path,
			query_string=query_string,
			client=client,
			auth=auth,
			raw=environ,
		)
