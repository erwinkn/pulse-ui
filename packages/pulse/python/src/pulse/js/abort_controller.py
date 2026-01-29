"""
JavaScript AbortController and AbortSignal builtins.

Usage:

```python
from pulse.js import AbortController

@ps.javascript
def example():
    controller = AbortController()
    signal = controller.signal
    controller.abort()
```
"""

from collections.abc import Callable as _Callable
from typing import Any as _Any

from pulse.transpiler.js_module import JsModule


class AbortSignal:
	"""Signal object used to abort async operations."""

	@property
	def aborted(self) -> bool: ...

	@property
	def onabort(self) -> _Callable[[_Any], _Any] | None: ...

	def throwIfAborted(self) -> None: ...

	def addEventListener(
		self,
		type: str,
		listener: _Callable[..., None],
		options: bool | dict[str, bool] | None = None,
		/,
	) -> None: ...

	def removeEventListener(
		self,
		type: str,
		listener: _Callable[..., None],
		options: bool | dict[str, bool] | None = None,
		/,
	) -> None: ...


class AbortController:
	"""Controller for creating and aborting AbortSignals."""

	@property
	def signal(self) -> AbortSignal: ...

	def abort(self) -> None: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
