"""
JavaScript Error builtin module.

Usage:
    import pulse.js.error as Error
    Error("message")              # -> new Error("message")
    Error.RangeError("message")   # -> new RangeError("message")

    from pulse.js.error import Error, TypeError, RangeError, ReferenceError
    Error("message")              # -> new Error("message")
    TypeError("message")         # -> new TypeError("message")
"""

from __future__ import annotations

from typing import Protocol

from pulse.transpiler.js_module import register_js_module


class Error(Protocol):
	"""Protocol for JavaScript Error instances."""

	def __init__(self, message: str | None = None): ...

	message: str
	name: str
	stack: str | None

	def toString(self) -> str: ...


# Error Subclasses - these are separate globals in JS, not members of Error
# TODO: These need a different architecture (separate modules or standalone identifiers)
class EvalError(Protocol):
	"""Protocol for JavaScript EvalError instances."""

	def __init__(self, message: str | None = None): ...

	message: str
	name: str
	stack: str | None

	def toString(self) -> str: ...


class RangeError(Protocol):
	"""Protocol for JavaScript RangeError instances."""

	def __init__(self, message: str | None = None): ...

	message: str
	name: str
	stack: str | None

	def toString(self) -> str: ...


class ReferenceError(Protocol):
	"""Protocol for JavaScript ReferenceError instances."""

	def __init__(self, message: str | None = None): ...

	message: str
	name: str
	stack: str | None

	def toString(self) -> str: ...


class SyntaxError(Protocol):
	"""Protocol for JavaScript SyntaxError instances."""

	def __init__(self, message: str | None = None): ...

	message: str
	name: str
	stack: str | None

	def toString(self) -> str: ...


class TypeError(Protocol):
	"""Protocol for JavaScript TypeError instances."""

	def __init__(self, message: str | None = None): ...

	message: str
	name: str
	stack: str | None

	def toString(self) -> str: ...


class URIError(Protocol):
	"""Protocol for JavaScript URIError instances."""

	def __init__(self, message: str | None = None): ...

	message: str
	name: str
	stack: str | None

	def toString(self) -> str: ...


# Self-register this module as a JS builtin
register_js_module(name="Error", global_scope=True)
