"""Common type definitions for JavaScript builtin bindings.

This module provides type aliases and protocols for proper typing of JS APIs.
These are purely for static type checking - they have no runtime effect.
"""

from collections.abc import Awaitable as _Awaitable
from collections.abc import Callable as _Callable
from collections.abc import Iterator as _Iterator
from typing import Protocol as _Protocol
from typing import TypeVar as _TypeVar
from typing import overload as _overload

# Type variables
T = _TypeVar("T")
T_co = _TypeVar("T_co", covariant=True)
T_contra = _TypeVar("T_contra", contravariant=True)
K = _TypeVar("K")
V = _TypeVar("V")
R = _TypeVar("R")

# Promise result types
PromiseSettledResult = dict[
	str, T | str
]  # { status: "fulfilled" | "rejected", value?: T, reason?: any }


# Callback type aliases for collection methods
# These mirror JavaScript's callback signatures

# Array callbacks
ArrayCallback = _Callable[[T, int, "JSArray[T]"], R]
ArrayCallbackNoIndex = _Callable[[T], R]
ArrayPredicate = _Callable[[T, int, "JSArray[T]"], bool]
ArrayReducer = _Callable[[R, T, int, "JSArray[T]"], R]
ArrayComparator = _Callable[[T, T], int]

# Map callbacks
MapForEachCallback = _Callable[[V, K, "JSMap[K, V]"], None]

# Set callbacks
SetForEachCallback = _Callable[[T, T, "JSSet[T]"], None]


# JavaScript Iterator protocol
class JSIterator(_Protocol[T_co]):
	"""Protocol for JavaScript Iterator objects."""

	def next(self) -> "JSIteratorResult[T_co]": ...

	def __iter__(self) -> "JSIterator[T_co]": ...


class JSIteratorResult(_Protocol[T_co]):
	"""Result from JavaScript Iterator.next()."""

	@property
	def value(self) -> T_co: ...

	@property
	def done(self) -> bool: ...


# JavaScript Iterable protocol
class JSIterable(_Protocol[T_co]):
	"""Protocol for JavaScript Iterable objects (has Symbol.iterator)."""

	def __iter__(self) -> _Iterator[T_co]: ...


# Placeholder for forward references within this module
class JSArray(_Protocol[T_co]):
	"""Forward reference for Array type - actual implementation in array.py."""

	...


V_co = _TypeVar("V_co", covariant=True)


class JSMap(_Protocol[T_co, V_co]):
	"""Forward reference for Map type - actual implementation in map.py."""

	...


class JSSet(_Protocol[T_co]):
	"""Forward reference for Set type - actual implementation in set.py."""

	...


# DOM Element types (for document/window methods)
class Element(_Protocol):
	"""Protocol for DOM Element objects."""

	@property
	def tagName(self) -> str: ...

	@property
	def id(self) -> str: ...

	@property
	def className(self) -> str: ...

	@property
	def innerHTML(self) -> str: ...

	@property
	def textContent(self) -> str | None: ...

	@property
	def parentElement(self) -> "Element | None": ...

	@property
	def children(self) -> "NodeList[Element]": ...

	def querySelector(self, selectors: str) -> "Element | None": ...
	def querySelectorAll(self, selectors: str) -> "NodeList[Element]": ...
	def getAttribute(self, name: str) -> str | None: ...
	def setAttribute(self, name: str, value: str) -> None: ...
	def removeAttribute(self, name: str) -> None: ...
	def hasAttribute(self, name: str) -> bool: ...
	def addEventListener(
		self,
		type: str,
		listener: _Callable[..., None],
		options: bool | dict[str, bool] | None = None,
	) -> None: ...
	def removeEventListener(
		self,
		type: str,
		listener: _Callable[..., None],
		options: bool | dict[str, bool] | None = None,
	) -> None: ...
	def remove(self) -> None: ...
	def append(self, *nodes: "Element | str") -> None: ...
	def prepend(self, *nodes: "Element | str") -> None: ...
	def replaceWith(self, *nodes: "Element | str") -> None: ...


class HTMLElement(Element, _Protocol):
	"""Protocol for HTMLElement objects."""

	@property
	def style(self) -> "CSSStyleDeclaration": ...

	@property
	def dataset(self) -> dict[str, str]: ...

	@property
	def offsetWidth(self) -> int: ...

	@property
	def offsetHeight(self) -> int: ...

	def focus(self) -> None: ...
	def blur(self) -> None: ...
	def click(self) -> None: ...


class CSSStyleDeclaration(_Protocol):
	"""Protocol for CSSStyleDeclaration."""

	def getPropertyValue(self, property: str) -> str: ...
	def setProperty(self, property: str, value: str, priority: str = "") -> None: ...
	def removeProperty(self, property: str) -> str: ...


class NodeList(_Protocol[T]):
	"""Protocol for NodeList objects."""

	@property
	def length(self) -> int: ...

	def item(self, index: int) -> T | None: ...
	def __iter__(self) -> _Iterator[T]: ...
	def __len__(self) -> int: ...

	@_overload
	def __getitem__(self, index: int) -> T: ...
	@_overload
	def __getitem__(self, index: slice) -> list[T]: ...


class HTMLCollection(_Protocol[T_co]):
	"""Protocol for HTMLCollection objects."""

	@property
	def length(self) -> int: ...

	def item(self, index: int) -> T_co | None: ...
	def namedItem(self, name: str) -> T_co | None: ...
	def __iter__(self) -> _Iterator[T_co]: ...
	def __len__(self) -> int: ...


# Selection API
class Selection(_Protocol):
	"""Protocol for window.getSelection() result."""

	@property
	def anchorNode(self) -> Element | None: ...

	@property
	def focusNode(self) -> Element | None: ...

	@property
	def isCollapsed(self) -> bool: ...

	@property
	def rangeCount(self) -> int: ...

	def getRangeAt(self, index: int) -> "Range": ...
	def collapse(self, node: Element | None, offset: int = 0) -> None: ...
	def selectAllChildren(self, node: Element) -> None: ...
	def removeAllRanges(self) -> None: ...
	def toString(self) -> str: ...


class Range(_Protocol):
	"""Protocol for Range objects."""

	@property
	def startContainer(self) -> Element: ...

	@property
	def endContainer(self) -> Element: ...

	@property
	def startOffset(self) -> int: ...

	@property
	def endOffset(self) -> int: ...

	@property
	def collapsed(self) -> bool: ...

	def setStart(self, node: Element, offset: int) -> None: ...
	def setEnd(self, node: Element, offset: int) -> None: ...
	def selectNode(self, node: Element) -> None: ...
	def selectNodeContents(self, node: Element) -> None: ...
	def collapse(self, toStart: bool = False) -> None: ...
	def cloneContents(self) -> Element: ...
	def deleteContents(self) -> None: ...


# Clipboard API
class Clipboard(_Protocol):
	"""Protocol for Navigator.clipboard."""

	def read(self) -> _Awaitable[list["ClipboardItem"]]: ...
	def readText(self) -> _Awaitable[str]: ...
	def write(self, data: list["ClipboardItem"]) -> _Awaitable[None]: ...
	def writeText(self, text: str) -> _Awaitable[None]: ...


class ClipboardItem(_Protocol):
	"""Protocol for ClipboardItem."""

	@property
	def types(self) -> list[str]: ...

	def getType(self, type: str) -> _Awaitable[bytes]: ...


# Event types
class Event(_Protocol):
	"""Protocol for Event objects."""

	@property
	def type(self) -> str: ...

	@property
	def target(self) -> Element | None: ...

	@property
	def currentTarget(self) -> Element | None: ...

	@property
	def bubbles(self) -> bool: ...

	@property
	def cancelable(self) -> bool: ...

	@property
	def defaultPrevented(self) -> bool: ...

	def preventDefault(self) -> None: ...
	def stopPropagation(self) -> None: ...
	def stopImmediatePropagation(self) -> None: ...


# JSON types
JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
JSONReplacer = list[str | int] | _Callable[[str, JSONValue], JSONValue]
JSONReviver = _Callable[[str, JSONValue], JSONValue]
