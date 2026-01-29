"""
JavaScript CustomEvent builtin.

Usage:

```python
from pulse.js import CustomEvent, obj

@ps.javascript
def example():
    event = CustomEvent("my-event", obj(detail={"ok": True}))
    return event.detail
```
"""

from typing import Any as _Any
from typing import TypedDict as _TypedDict

from pulse.transpiler.js_module import JsModule


class CustomEventInit(_TypedDict, total=False):
	detail: _Any
	bubbles: bool
	cancelable: bool


class CustomEvent:
	"""Custom event with a detail payload."""

	def __init__(
		self, type: str, eventInitDict: CustomEventInit | None = None, /
	) -> None: ...

	@property
	def detail(self) -> _Any: ...

	def initCustomEvent(
		self,
		type: str,
		bubbles: bool | None = None,
		cancelable: bool | None = None,
		detail: _Any | None = None,
		/,
	) -> None: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
