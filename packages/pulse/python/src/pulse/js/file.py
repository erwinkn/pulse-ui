"""
JavaScript File builtin.

Usage:

```python
from pulse.js import File, obj

@ps.javascript
def example():
    f = File(["hello"], "greeting.txt", obj(type="text/plain"))
    return f.name
```
"""

from typing import Any as _Any
from typing import TypedDict as _TypedDict

from pulse.transpiler.js_module import JsModule


class FilePropertyBag(_TypedDict, total=False):
	type: str
	endings: str
	lastModified: int


class File:
	"""File object backed by a Blob."""

	def __init__(
		self,
		fileBits: list[_Any],
		fileName: str,
		options: FilePropertyBag | None = None,
		/,
	) -> None: ...

	@property
	def name(self) -> str: ...

	@property
	def lastModified(self) -> int: ...

	@property
	def webkitRelativePath(self) -> str: ...

	@property
	def size(self) -> int: ...

	@property
	def type(self) -> str: ...

	def arrayBuffer(self) -> _Any: ...

	def bytes(self) -> _Any: ...

	def slice(
		self,
		start: int | None = None,
		end: int | None = None,
		contentType: str | None = None,
		/,
	) -> "File": ...

	def stream(self) -> _Any: ...

	def text(self) -> _Any: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
