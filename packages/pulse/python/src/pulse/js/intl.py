"""
JavaScript Intl namespace.

Usage:

```python
from pulse.js import Intl

@ps.javascript
def example(value: float):
    fmt = Intl.NumberFormat("en-US")
    return fmt.format(value)
```
"""

from typing import Any as _Any

from pulse.transpiler.js_module import JsModule


class Collator:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def compare(self, x: str, y: str, /) -> int: ...


class DateTimeFormat:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def format(self, date: _Any = None, /) -> str: ...


class DisplayNames:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def of(self, code: str, /) -> str | None: ...


class ListFormat:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def format(self, items: list[str], /) -> str: ...


class NumberFormat:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def format(self, value: _Any, /) -> str: ...


class PluralRules:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def select(self, value: _Any, /) -> str: ...


class RelativeTimeFormat:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def format(self, value: int, unit: str, /) -> str: ...


class Segmenter:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def segment(self, text: str, /) -> _Any: ...


class Locale:
	def __init__(self, tag: str, options: _Any | None = None, /) -> None: ...

	@property
	def baseName(self) -> str: ...


class DurationFormat:
	def __init__(
		self, locales: _Any | None = None, options: _Any | None = None, /
	) -> None: ...

	def format(self, value: _Any, /) -> str: ...


# Self-register this module as a JS builtin namespace
JsModule.register(name="Intl")
