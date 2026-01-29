"""
JavaScript Blob builtin.

Usage:

```python
from pulse.js import Blob, obj

@ps.javascript
def example():
    blob = Blob(["hello"], obj(type="text/plain"))
    return blob.size
```
"""

from typing import Any as _Any
from typing import TypedDict as _TypedDict

from pulse.transpiler.js_module import JsModule


class BlobPropertyBag(_TypedDict, total=False):
	type: str


class Blob:
	"""Binary large object."""

	def __init__(
		self,
		blobParts: list[_Any] | None = None,
		options: BlobPropertyBag | None = None,
		/,
	) -> None: ...

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
	) -> "Blob": ...

	def stream(self) -> _Any: ...

	def text(self) -> _Any: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
