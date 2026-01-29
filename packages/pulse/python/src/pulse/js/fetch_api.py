"""
JavaScript Fetch API builtins.

Usage:

```python
from pulse.js import fetch, Request, Headers, obj

@ps.javascript
async def example():
    req = Request("/api", obj(method="GET"))
    res = await fetch(req)
    return res.json()
```
"""

from __future__ import annotations

from collections.abc import Callable as _Callable
from typing import Any as _Any
from typing import TypedDict as _TypedDict

from pulse.js.abort_controller import AbortSignal
from pulse.transpiler.js_module import JsModule


class RequestInit(_TypedDict, total=False):
	method: str
	headers: _Any
	body: _Any
	mode: str
	credentials: str
	cache: str
	redirect: str
	referrer: str
	referrerPolicy: str
	integrity: str
	keepalive: bool
	signal: AbortSignal
	window: _Any


class ResponseInit(_TypedDict, total=False):
	status: int
	statusText: str
	headers: _Any


class Headers:
	"""HTTP headers for fetch requests/responses."""

	def __init__(self, init: _Any | None = None, /) -> None: ...

	def append(self, name: str, value: str, /) -> None: ...

	def delete(self, name: str, /) -> None: ...

	def get(self, name: str, /) -> str | None: ...

	def has(self, name: str, /) -> bool: ...

	def set(self, name: str, value: str, /) -> None: ...

	def forEach(
		self,
		callback: _Callable[[str, str, "Headers"], None],
		thisArg: _Any | None = None,
		/,
	) -> None: ...


class Request:
	"""Represents a resource request."""

	def __init__(
		self, input: str | Request, init: RequestInit | None = None, /
	) -> None: ...

	@property
	def url(self) -> str: ...

	@property
	def method(self) -> str: ...

	@property
	def headers(self) -> Headers: ...

	@property
	def body(self) -> _Any: ...


class Response:
	"""Represents a response to a request."""

	def __init__(
		self, body: _Any | None = None, init: ResponseInit | None = None, /
	) -> None: ...

	@property
	def status(self) -> int: ...

	@property
	def ok(self) -> bool: ...

	@property
	def headers(self) -> Headers: ...

	@property
	def body(self) -> _Any: ...

	def json(self) -> _Any: ...

	def text(self) -> _Any: ...

	def blob(self) -> _Any: ...

	def formData(self) -> _Any: ...

	def arrayBuffer(self) -> _Any: ...


def fetch(input: str | Request, init: RequestInit | None = None, /) -> _Any: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
