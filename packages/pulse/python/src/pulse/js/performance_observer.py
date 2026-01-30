"""
JavaScript PerformanceObserver builtin.

Usage:

```python
from pulse.js import PerformanceObserver, obj

@ps.javascript
def example():
    observer = PerformanceObserver(lambda list_, obs: None)
    observer.observe(obj(entryTypes=["mark", "measure"]))
```
"""

from collections.abc import Callable as _Callable
from typing import Any as _Any
from typing import Protocol as _Protocol
from typing import TypedDict as _TypedDict

from pulse.transpiler.js_module import JsModule


class PerformanceObserverInit(_TypedDict, total=False):
	buffered: bool
	durationThreshold: float
	entryTypes: list[str]
	type: str


class PerformanceObserverEntryList(_Protocol):
	def getEntries(self) -> list[_Any]: ...


class PerformanceObserver:
	"""Observe performance entry events."""

	def __init__(
		self,
		callback: _Callable[
			[PerformanceObserverEntryList, "PerformanceObserver"], None
		],
		/,
	) -> None: ...

	def observe(self, options: PerformanceObserverInit, /) -> None: ...

	def disconnect(self) -> None: ...

	def takeRecords(self) -> list[_Any]: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
