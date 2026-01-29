"""
JavaScript FormData builtin.

Usage:

```python
from pulse.js import FormData

@ps.javascript
def example():
    form = FormData()
    form.append("name", "Ada")
    return form.get("name")
```
"""

from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from typing import Any as _Any

from pulse.transpiler.js_module import JsModule


class FormData:
	"""FormData key/value collection for multipart requests."""

	def __init__(self, form: _Any | None = None, /) -> None: ...

	def append(
		self, name: str, value: _Any, filename: str | None = None, /
	) -> None: ...

	def set(self, name: str, value: _Any, filename: str | None = None, /) -> None: ...

	def delete(self, name: str, /) -> None: ...

	def get(self, name: str, /) -> _Any | None: ...

	def getAll(self, name: str, /) -> list[_Any]: ...

	def has(self, name: str, /) -> bool: ...

	def entries(self) -> _Iterable[tuple[str, _Any]]: ...

	def keys(self) -> _Iterable[str]: ...

	def values(self) -> _Iterable[_Any]: ...

	def forEach(
		self,
		callback: _Callable[[_Any, str, "FormData"], None],
		thisArg: _Any | None = None,
		/,
	) -> None: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
