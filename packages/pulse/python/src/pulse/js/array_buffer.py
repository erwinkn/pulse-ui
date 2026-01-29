"""
JavaScript ArrayBuffer/DataView/TypedArray builtins.

Usage:

```python
from pulse.js import ArrayBuffer, Uint8Array

@ps.javascript
def example():
    buf = ArrayBuffer(8)
    view = Uint8Array(buf)
    view[0] = 255
    return buf.byteLength
```
"""

from typing import Any as _Any
from typing import ClassVar as _ClassVar
from typing import TypedDict as _TypedDict

from pulse.transpiler.js_module import JsModule


class ArrayBufferOptions(_TypedDict, total=False):
	maxByteLength: int


class ArrayBuffer:
	"""Fixed-length raw binary data buffer."""

	def __init__(
		self, length: int, options: ArrayBufferOptions | None = None, /
	) -> None: ...

	@property
	def byteLength(self) -> int: ...

	@property
	def maxByteLength(self) -> int: ...

	@property
	def resizable(self) -> bool: ...

	def slice(self, begin: int = 0, end: int | None = None, /) -> "ArrayBuffer": ...

	@staticmethod
	def isView(value: _Any, /) -> bool: ...


class DataView:
	"""View for reading/writing multiple numeric types."""

	def __init__(
		self,
		buffer: ArrayBuffer,
		byteOffset: int = 0,
		byteLength: int | None = None,
		/,
	) -> None: ...

	@property
	def buffer(self) -> ArrayBuffer: ...

	@property
	def byteLength(self) -> int: ...

	@property
	def byteOffset(self) -> int: ...


class _TypedArray:
	"""Common TypedArray surface for typing."""

	@property
	def buffer(self) -> ArrayBuffer: ...

	@property
	def byteLength(self) -> int: ...

	@property
	def byteOffset(self) -> int: ...

	@property
	def length(self) -> int: ...

	def set(self, source: _Any, offset: int | None = None, /) -> None: ...

	def subarray(self, begin: int = 0, end: int | None = None, /) -> _Any: ...

	def slice(self, begin: int = 0, end: int | None = None, /) -> _Any: ...


class Int8Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Uint8Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Uint8ClampedArray(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Int16Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Uint16Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Int32Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Uint32Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Float32Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class Float64Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class BigInt64Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


class BigUint64Array(_TypedArray):
	BYTES_PER_ELEMENT: _ClassVar[int]

	def __init__(
		self,
		data: _Any | None = None,
		byteOffset: int | None = None,
		length: int | None = None,
		/,
	) -> None: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
