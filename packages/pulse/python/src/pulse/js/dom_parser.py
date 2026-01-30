"""
JavaScript DOMParser and XMLSerializer builtins.

Usage:

```python
from pulse.js import DOMParser, XMLSerializer

@ps.javascript
def example(source: str):
    parser = DOMParser()
    doc = parser.parseFromString(source, "text/html")
    serializer = XMLSerializer()
    return serializer.serializeToString(doc)
```
"""

from typing import Any as _Any

from pulse.transpiler.js_module import JsModule


class DOMParser:
	"""Parses XML/HTML from strings."""

	def __init__(self) -> None: ...

	def parseFromString(self, string: str, mimeType: str, /) -> _Any: ...


class XMLSerializer:
	"""Serializes DOM nodes to strings."""

	def __init__(self) -> None: ...

	def serializeToString(self, root: _Any, /) -> str: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
