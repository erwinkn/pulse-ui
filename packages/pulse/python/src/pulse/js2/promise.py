"""
JavaScript Promise builtin module.

Usage:
    from pulse.js2 import Promise
    Promise(executor)             # -> new Promise(executor)
    Promise.resolve(value)        # -> Promise.resolve(value)
    Promise.reject(reason)        # -> Promise.reject(reason)

    # Or import from module directly:
    from pulse.js2.promise import Promise

The Promise class is generic and supports async/await via the Awaitable protocol.
"""

from collections.abc import Callable as _Callable
from collections.abc import Generator as _Generator
from collections.abc import Iterable as _Iterable
from typing import Any as _Any
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar
from typing import overload as _overload

from pulse.transpiler_v2.js_module import JsModule

T = _TypeVar("T")
T_co = _TypeVar("T_co", covariant=True)
U = _TypeVar("U")

# Result types for allSettled
PromiseFulfilledResult = dict[str, T | str]  # { status: "fulfilled", value: T }
PromiseRejectedResult = dict[str, str]  # { status: "rejected", reason: any }
PromiseSettledResult = PromiseFulfilledResult[T] | PromiseRejectedResult


class Promise(_Generic[T_co]):
	"""JavaScript Promise - a thenable that represents an async operation.

	Promise is both generic over its resolved type and implements Awaitable,
	allowing it to be used with Python's async/await syntax which transpiles
	to JavaScript async/await.

	Example:
	    @javascript
	    async def fetch_data() -> str:
	        response: Promise[Response] = fetch("/api/data")
	        data = await response  # Awaits the promise
	        return data.text()
	"""

	def __init__(
		self,
		executor: _Callable[
			[_Callable[[T_co], None], _Callable[[Exception], None]], None
		]
		| None = None,
		/,
	) -> None:
		"""Create a Promise.

		Args:
		    executor: Optional function receiving (resolve, reject) callbacks.
		        If omitted, creates a pending promise (for use with Promise.resolve/reject).
		"""
		...

	def then(
		self,
		on_fulfilled: _Callable[[T_co], U | "Promise[U]"] | None = None,
		on_rejected: _Callable[[Exception], U | "Promise[U]"] | None = None,
		/,
	) -> "Promise[U]":
		"""Attach callbacks to handle fulfillment and/or rejection."""
		...

	def catch(
		self, on_rejected: _Callable[[Exception], U | "Promise[U]"]
	) -> "Promise[T_co | U]":
		"""Attach a rejection handler callback."""
		...

	def finally_(self, on_finally: _Callable[[], None]) -> "Promise[T_co]":
		"""Attach a handler that is called when the promise settles (fulfilled or rejected)."""
		...

	def __await__(self) -> _Generator[None, None, T_co]:
		"""Support await syntax - transpiles to JavaScript await."""
		...

	# Static methods for Promise construction
	@staticmethod
	@_overload
	def resolve() -> "Promise[None]":
		"""Create a Promise that resolves with None."""
		...

	@staticmethod
	@_overload
	def resolve(value: U, /) -> "Promise[U]":
		"""Create a Promise that resolves with the given value."""
		...

	@staticmethod
	def resolve(value: U | None = None, /) -> "Promise[U] | Promise[None]":
		"""Create a Promise that resolves with the given value."""
		...

	@staticmethod
	def reject(reason: Exception | str) -> "Promise[_Any]":
		"""Create a Promise that rejects with the given reason."""
		...

	# Static methods for combining promises
	@staticmethod
	def all(iterable: _Iterable["Promise[T]"]) -> "Promise[list[T]]":
		"""Wait for all promises to resolve, or reject on first rejection.

		Returns a promise that resolves to a list of all resolved values.
		"""
		...

	@staticmethod
	def allSettled(
		iterable: _Iterable["Promise[T]"],
	) -> "Promise[list[PromiseSettledResult[T]]]":
		"""Wait for all promises to settle (resolve or reject).

		Returns a promise that resolves to a list of result objects.
		"""
		...

	@staticmethod
	def any(iterable: _Iterable["Promise[T]"]) -> "Promise[T]":
		"""Return first fulfilled promise, or reject if all reject."""
		...

	@staticmethod
	def race(iterable: _Iterable["Promise[T]"]) -> "Promise[T]":
		"""Return first settled promise (fulfilled or rejected)."""
		...

	@staticmethod
	def withResolvers() -> "PromiseWithResolvers[T]":
		"""Create a promise with its resolve and reject functions exposed.

		Returns an object with { promise, resolve, reject }.
		ES2024 feature.
		"""
		...


class PromiseWithResolvers(_Generic[T]):
	"""Result type for Promise.withResolvers()."""

	@property
	def promise(self) -> Promise[T]: ...

	@property
	def resolve(self) -> _Callable[[T], None]: ...

	@property
	def reject(self) -> _Callable[[Exception | str], None]: ...


# Self-register this module as a JS builtin (global identifier)
JsModule.register(name=None)
