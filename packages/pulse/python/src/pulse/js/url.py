"""
JavaScript URL and URLSearchParams builtins.

Usage:

```python
from pulse.js import URL, URLSearchParams

@ps.javascript
def example():
    url = URL("https://example.com?foo=1")
    params = URLSearchParams(url.search)
    params.append("bar", "2")
    return url.toString(), params.toString()
```
"""

from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from typing import Any as _Any

from pulse.transpiler.js_module import JsModule


class URLSearchParams:
	"""Query string utility object."""

	def __init__(
		self,
		init: str | _Iterable[tuple[str, str]] | dict[str, str] | None = None,
		/,
	) -> None: ...

	@property
	def size(self) -> int: ...

	def append(self, name: str, value: str, /) -> None: ...

	def delete(self, name: str, value: str | None = None, /) -> None: ...

	def entries(self) -> _Iterable[tuple[str, str]]: ...

	def forEach(
		self,
		callback: _Callable[[str, str, "URLSearchParams"], None],
		thisArg: _Any | None = None,
		/,
	) -> None: ...

	def get(self, name: str, /) -> str | None: ...

	def getAll(self, name: str, /) -> list[str]: ...

	def has(self, name: str, value: str | None = None, /) -> bool: ...

	def keys(self) -> _Iterable[str]: ...

	def set(self, name: str, value: str, /) -> None: ...

	def sort(self) -> None: ...

	def toString(self) -> str: ...

	def values(self) -> _Iterable[str]: ...


class URL:
	"""URL parser and serializer."""

	def __init__(self, url: str, base: str | None = None, /) -> None: ...

	@property
	def href(self) -> str: ...

	@property
	def origin(self) -> str: ...

	@property
	def protocol(self) -> str: ...

	@property
	def username(self) -> str: ...

	@property
	def password(self) -> str: ...

	@property
	def host(self) -> str: ...

	@property
	def hostname(self) -> str: ...

	@property
	def port(self) -> str: ...

	@property
	def pathname(self) -> str: ...

	@property
	def search(self) -> str: ...

	@property
	def hash(self) -> str: ...

	@property
	def searchParams(self) -> URLSearchParams: ...

	def toString(self) -> str: ...

	def toJSON(self) -> str: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
