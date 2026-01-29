"""
JavaScript IntersectionObserver builtin.

Usage:

```python
from pulse.js import IntersectionObserver, obj

@ps.javascript
def example(target):
    observer = IntersectionObserver(lambda entries, obs: None, obj(threshold=0.5))
    observer.observe(target)
```
"""

from collections.abc import Callable as _Callable
from typing import Any as _Any
from typing import Protocol as _Protocol
from typing import TypedDict as _TypedDict

from pulse.js._types import Element as _Element
from pulse.transpiler.js_module import JsModule


class IntersectionObserverInit(_TypedDict, total=False):
	root: _Any
	rootMargin: str
	scrollMargin: str
	threshold: float | list[float]
	delay: int
	trackVisibility: bool


class IntersectionObserverEntry(_Protocol):
	@property
	def target(self) -> _Element: ...

	@property
	def isIntersecting(self) -> bool: ...

	@property
	def intersectionRatio(self) -> float: ...


class IntersectionObserver:
	"""Observe element visibility within a root."""

	def __init__(
		self,
		callback: _Callable[
			[list[IntersectionObserverEntry], "IntersectionObserver"], None
		],
		options: IntersectionObserverInit | None = None,
		/,
	) -> None: ...

	def observe(self, target: _Element, /) -> None: ...

	def unobserve(self, target: _Element, /) -> None: ...

	def disconnect(self) -> None: ...

	def takeRecords(self) -> list[IntersectionObserverEntry]: ...

	@property
	def root(self) -> _Any: ...

	@property
	def rootMargin(self) -> str: ...

	@property
	def thresholds(self) -> list[float]: ...

	@property
	def trackVisibility(self) -> bool: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
