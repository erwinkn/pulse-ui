"""
JavaScript ResizeObserver builtin.

Usage:

```python
from pulse.js import ResizeObserver, obj

@ps.javascript
def example(target):
    observer = ResizeObserver(lambda entries, obs: None)
    observer.observe(target, obj(box="border-box"))
```
"""

from collections.abc import Callable as _Callable
from typing import Protocol as _Protocol
from typing import TypedDict as _TypedDict

from pulse.js._types import Element as _Element
from pulse.transpiler.js_module import JsModule


class ResizeObserverOptions(_TypedDict, total=False):
	box: str


class ResizeObserverEntry(_Protocol):
	@property
	def target(self) -> _Element: ...

	@property
	def contentRect(self) -> object: ...


class ResizeObserver:
	"""Observe element size changes."""

	def __init__(
		self,
		callback: _Callable[[list[ResizeObserverEntry], "ResizeObserver"], None],
		/,
	) -> None: ...

	def observe(
		self, target: _Element, options: ResizeObserverOptions | None = None, /
	) -> None: ...

	def unobserve(self, target: _Element, /) -> None: ...

	def disconnect(self) -> None: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
