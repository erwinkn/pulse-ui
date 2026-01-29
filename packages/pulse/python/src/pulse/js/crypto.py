"""
JavaScript crypto namespace.

Usage:

```python
from pulse.js import crypto

@ps.javascript
def example():
    buf = Uint8Array(16)
    crypto.getRandomValues(buf)
    return crypto.randomUUID()
```
"""

from typing import Any as _Any
from typing import Protocol as _Protocol

from pulse.transpiler.js_module import JsModule


class CryptoKey(_Protocol):
	@property
	def algorithm(self) -> _Any: ...

	@property
	def extractable(self) -> bool: ...

	@property
	def type(self) -> str: ...

	@property
	def usages(self) -> list[str]: ...


class SubtleCrypto(_Protocol):
	def generateKey(
		self, algorithm: _Any, extractable: bool, keyUsages: list[str], /
	) -> _Any: ...

	def importKey(
		self,
		format: str,
		keyData: _Any,
		algorithm: _Any,
		extractable: bool,
		keyUsages: list[str],
		/,
	) -> _Any: ...

	def exportKey(self, format: str, key: CryptoKey, /) -> _Any: ...

	def encrypt(self, algorithm: _Any, key: CryptoKey, data: _Any, /) -> _Any: ...

	def decrypt(self, algorithm: _Any, key: CryptoKey, data: _Any, /) -> _Any: ...


subtle: SubtleCrypto


def getRandomValues(typedArray: _Any, /) -> _Any: ...


def randomUUID() -> str: ...


# Self-register this module as a JS builtin namespace
JsModule.register(name="crypto")
