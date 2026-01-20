"""
JavaScript Error builtin module.

Usage:

```python
from pulse.js import Error
Error("message")              # -> new Error("message")

from pulse.js.error import TypeError, RangeError, ReferenceError
TypeError("message")         # -> new TypeError("message")
```
"""

from pulse.transpiler.js_module import JsModule


class Error:
	"""Class for JavaScript Error instances."""

	def __init__(self, message: str | None = None, /): ...

	@property
	def message(self) -> str: ...

	@property
	def name(self) -> str: ...

	@property
	def stack(self) -> str | None: ...

	def toString(self) -> str: ...


# Error Subclasses - these are separate globals in JS, not members of Error
# TODO: These need a different architecture (separate modules or standalone identifiers)
class EvalError:
	"""Class for JavaScript EvalError instances."""

	def __init__(self, message: str | None = None, /): ...

	@property
	def message(self) -> str: ...

	@property
	def name(self) -> str: ...

	@property
	def stack(self) -> str | None: ...

	def toString(self) -> str: ...


class RangeError:
	"""Class for JavaScript RangeError instances."""

	def __init__(self, message: str | None = None, /): ...

	@property
	def message(self) -> str: ...

	@property
	def name(self) -> str: ...

	@property
	def stack(self) -> str | None: ...

	def toString(self) -> str: ...


class ReferenceError:
	"""Class for JavaScript ReferenceError instances."""

	def __init__(self, message: str | None = None, /): ...

	@property
	def message(self) -> str: ...

	@property
	def name(self) -> str: ...

	@property
	def stack(self) -> str | None: ...

	def toString(self) -> str: ...


class SyntaxError:
	"""Class for JavaScript SyntaxError instances."""

	def __init__(self, message: str | None = None, /): ...

	@property
	def message(self) -> str: ...

	@property
	def name(self) -> str: ...

	@property
	def stack(self) -> str | None: ...

	def toString(self) -> str: ...


class TypeError:
	"""Class for JavaScript TypeError instances."""

	def __init__(self, message: str | None = None, /): ...

	@property
	def message(self) -> str: ...

	@property
	def name(self) -> str: ...

	@property
	def stack(self) -> str | None: ...

	def toString(self) -> str: ...


class URIError:
	"""Class for JavaScript URIError instances."""

	def __init__(self, message: str | None = None, /): ...

	@property
	def message(self) -> str: ...

	@property
	def name(self) -> str: ...

	@property
	def stack(self) -> str | None: ...

	def toString(self) -> str: ...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
