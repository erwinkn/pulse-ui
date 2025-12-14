"""Browser window global object.

Usage:
    from pulse.js2 import window
    window.alert("Hello!")      # -> window.alert("Hello!")
    window.innerWidth           # -> window.innerWidth
"""

from collections.abc import Callable as _Callable
from typing import Any as _Any

from pulse.js2._types import Element as _Element
from pulse.js2._types import Selection as _Selection
from pulse.transpiler_v2.js_module import JsModule

# Dimensions
innerWidth: int
innerHeight: int
outerWidth: int
outerHeight: int

# Scroll position
scrollX: float
scrollY: float
pageXOffset: float  # Alias for scrollX
pageYOffset: float  # Alias for scrollY

# Screen information
devicePixelRatio: float

# Location and history (typed as Any since they're complex interfaces)
location: _Any
history: _Any
navigator: _Any
document: _Any

# Storage
localStorage: _Any
sessionStorage: _Any

# Performance
performance: _Any


# Dialog methods
def alert(message: str = "", /) -> None:
	"""Display an alert dialog with the given message."""
	...


def confirm(message: str = "", /) -> bool:
	"""Display a confirmation dialog. Returns True if user clicks OK."""
	...


def prompt(message: str = "", default: str = "", /) -> str | None:
	"""Display a prompt dialog. Returns input or None if cancelled."""
	...


# Scroll methods
def scrollTo(x: float | dict[str, float], y: float | None = None, /) -> None:
	"""Scroll to the given position."""
	...


def scrollBy(x: float | dict[str, float], y: float | None = None, /) -> None:
	"""Scroll by the given amount."""
	...


def scroll(x: float | dict[str, float], y: float | None = None, /) -> None:
	"""Alias for scrollTo."""
	...


# Selection
def getSelection() -> _Selection | None:
	"""Return the current text selection."""
	...


def getComputedStyle(element: _Element, pseudoElt: str | None = None, /) -> _Any:
	"""Return the computed style of an element."""
	...


# Focus
def focus() -> None:
	"""Give focus to the window."""
	...


def blur() -> None:
	"""Remove focus from the window."""
	...


# Open/close
def open(
	url: str = "",
	target: str = "_blank",
	features: str = "",
	/,
) -> _Any | None:
	"""Open a new window. Returns the new window object or None."""
	...


def close() -> None:
	"""Close the window (only works for windows opened by script)."""
	...


# Timers (these return timer IDs)
def setTimeout(handler: _Callable[..., None], timeout: int = 0, /, *args: _Any) -> int:
	"""Schedule a function to run after a delay. Returns timer ID."""
	...


def clearTimeout(timeoutId: int) -> None:
	"""Cancel a timeout scheduled with setTimeout."""
	...


def setInterval(handler: _Callable[..., None], timeout: int = 0, /, *args: _Any) -> int:
	"""Schedule a function to run repeatedly. Returns timer ID."""
	...


def clearInterval(intervalId: int) -> None:
	"""Cancel an interval scheduled with setInterval."""
	...


# Animation
def requestAnimationFrame(callback: _Callable[[float], None]) -> int:
	"""Request a callback before the next repaint. Returns request ID."""
	...


def cancelAnimationFrame(requestId: int) -> None:
	"""Cancel an animation frame request."""
	...


# Event listeners
def addEventListener(
	type: str,
	listener: _Callable[..., None],
	options: bool | dict[str, bool] | None = None,
	/,
) -> None:
	"""Add an event listener to the window."""
	...


def removeEventListener(
	type: str,
	listener: _Callable[..., None],
	options: bool | dict[str, bool] | None = None,
	/,
) -> None:
	"""Remove an event listener from the window."""
	...


def dispatchEvent(event: _Any) -> bool:
	"""Dispatch an event to the window."""
	...


# Encoding
def atob(encoded: str) -> str:
	"""Decode a base64 encoded string."""
	...


def btoa(data: str) -> str:
	"""Encode a string as base64."""
	...


# Misc
def matchMedia(query: str) -> _Any:
	"""Return a MediaQueryList for the given media query."""
	...


def print_() -> None:
	"""Open the print dialog."""
	...


def postMessage(
	message: _Any, targetOrigin: str, transfer: list[_Any] | None = None, /
) -> None:
	"""Post a message to another window."""
	...


JsModule.register(name="window")
