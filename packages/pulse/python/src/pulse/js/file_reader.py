"""
JavaScript FileReader builtin.

Usage:

```python
from pulse.js import FileReader

@ps.javascript
def example(blob):
    reader = FileReader()
    reader.readAsText(blob)
    return reader.result
```
"""

from typing import Any as _Any

from pulse.transpiler.js_module import JsModule


class FileReader:
	"""Read File/Blob contents."""

	@property
	def result(self) -> _Any: ...

	@property
	def readyState(self) -> int: ...

	def readAsText(self, blob: _Any, encoding: str | None = None, /) -> None: ...

	def readAsArrayBuffer(self, blob: _Any, /) -> None: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
