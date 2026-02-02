"""Browser document global object.

Usage:

```python
from pulse.js import document
document.querySelector("#app")      # -> document.querySelector("#app")
```
"""

from collections.abc import Callable as _Callable
from typing import Any as _Any

from pulse.js._types import Element as _Element
from pulse.js._types import HTMLCollection as _HTMLCollection
from pulse.js._types import HTMLElement as _HTMLElement
from pulse.js._types import NodeList as _NodeList
from pulse.js.animation import Animation as _Animation
from pulse.js.animation import DocumentTimeline as _DocumentTimeline
from pulse.transpiler.js_module import JsModule

# Read-only properties
body: _HTMLElement
head: _HTMLElement
documentElement: _HTMLElement
activeElement: _Element | None
title: str
readyState: str  # "loading" | "interactive" | "complete"
cookie: str
referrer: str
URL: str
domain: str
timeline: _DocumentTimeline


# Query methods
def querySelector(selectors: str) -> _Element | None:
	"""Return the first element matching the selector, or None."""
	...


def querySelectorAll(selectors: str) -> _NodeList[_Element]:
	"""Return all elements matching the selector."""
	...


def getElementById(elementId: str) -> _Element | None:
	"""Return the element with the given ID, or None."""
	...


def getElementsByClassName(classNames: str) -> _HTMLCollection[_Element]:
	"""Return all elements with the given class name(s)."""
	...


def getElementsByTagName(qualifiedName: str) -> _HTMLCollection[_Element]:
	"""Return all elements with the given tag name."""
	...


def getElementsByName(elementName: str) -> _NodeList[_Element]:
	"""Return all elements with the given name attribute."""
	...


# Element creation
def createElement(
	tagName: str, options: dict[str, str] | None = None, /
) -> _HTMLElement:
	"""Create a new element with the given tag name."""
	...


def createTextNode(data: str) -> _Any:
	"""Create a new text node."""
	...


def createDocumentFragment() -> _Any:
	"""Create a new document fragment."""
	...


def createComment(data: str) -> _Any:
	"""Create a new comment node."""
	...


# Event methods
def addEventListener(
	type: str,
	listener: _Callable[..., None],
	options: bool | dict[str, bool] | None = None,
	/,
) -> None:
	"""Add an event listener to the document."""
	...


def removeEventListener(
	type: str,
	listener: _Callable[..., None],
	options: bool | dict[str, bool] | None = None,
	/,
) -> None:
	"""Remove an event listener from the document."""
	...


def dispatchEvent(event: _Any) -> bool:
	"""Dispatch an event to the document."""
	...


# Focus methods
def hasFocus() -> bool:
	"""Return True if the document has focus."""
	...


# Selection
def getSelection() -> _Any:
	"""Return the current selection."""
	...


def getAnimations() -> list[_Animation]:
	"""Return animations associated with this document."""
	...


# Node tree methods
def importNode(node: _Element, deep: bool = False, /) -> _Element:
	"""Import a node from another document."""
	...


def adoptNode(node: _Element) -> _Element:
	"""Adopt a node from another document."""
	...


# Full-screen API
def exitFullscreen() -> _Any:
	"""Exit full-screen mode. Returns a Promise."""
	...


fullscreenElement: _Element | None


JsModule.register(name="document")
