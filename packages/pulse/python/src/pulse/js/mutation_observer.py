"""
JavaScript MutationObserver builtin module.

Usage:

```python
from pulse.js import MutationObserver, obj

@ps.javascript
def example(target):
    observer = MutationObserver(lambda records, obs: None)
    observer.observe(target, obj(childList=True))
```

# Or import from module directly:
from pulse.js.mutation_observer import MutationObserver
"""

from collections.abc import Callable as _Callable
from typing import Any as _Any
from typing import Protocol as _Protocol
from typing import TypedDict as _TypedDict

from pulse.transpiler.js_module import JsModule


class MutationObserverInit(_TypedDict, total=False):
	"""Options for MutationObserver.observe()."""

	childList: bool
	attributes: bool
	characterData: bool
	subtree: bool
	attributeOldValue: bool
	characterDataOldValue: bool
	attributeFilter: list[str]


class MutationRecord(_Protocol):
	"""Minimal MutationRecord shape for type checking."""

	@property
	def type(self) -> str: ...

	@property
	def target(self) -> _Any: ...

	@property
	def addedNodes(self) -> _Any: ...

	@property
	def removedNodes(self) -> _Any: ...

	@property
	def previousSibling(self) -> _Any: ...

	@property
	def nextSibling(self) -> _Any: ...

	@property
	def attributeName(self) -> str | None: ...

	@property
	def attributeNamespace(self) -> str | None: ...

	@property
	def oldValue(self) -> str | None: ...


class MutationObserver:
	"""JavaScript MutationObserver - observe DOM changes."""

	def __init__(
		self,
		callback: _Callable[[list[MutationRecord], "MutationObserver"], _Any],
		/,
	) -> None: ...

	def observe(self, target: _Any, options: MutationObserverInit, /) -> None: ...

	def disconnect(self) -> None: ...

	def takeRecords(self) -> list[MutationRecord]: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
