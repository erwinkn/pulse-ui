"""
JavaScript TextEncoder/TextDecoder builtins.

Usage:

```python
from pulse.js import TextEncoder, TextDecoder

@ps.javascript
def example(text: str, data):
    encoder = TextEncoder()
    encoded = encoder.encode(text)
    decoder = TextDecoder("utf-8")
    return decoder.decode(encoded)
```
"""

from typing import Any as _Any
from typing import TypedDict as _TypedDict

from pulse.transpiler.js_module import JsModule


class TextDecoderOptions(_TypedDict, total=False):
	fatal: bool
	ignoreBOM: bool


class TextDecodeOptions(_TypedDict, total=False):
	stream: bool


class TextEncoder:
	"""UTF-8 encoder."""

	@property
	def encoding(self) -> str: ...

	def encode(self, string: str = "", /) -> _Any: ...

	def encodeInto(self, string: str, destination: _Any, /) -> _Any: ...


class TextDecoder:
	"""Text decoder for byte streams."""

	def __init__(
		self, label: str | None = None, options: TextDecoderOptions | None = None, /
	) -> None: ...

	@property
	def encoding(self) -> str: ...

	@property
	def fatal(self) -> bool: ...

	@property
	def ignoreBOM(self) -> bool: ...

	def decode(
		self, input: _Any | None = None, options: TextDecodeOptions | None = None, /
	) -> str: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
