"""Python asyncio module transpilation to JavaScript Promise operations.

This module provides transpilation from Python's `asyncio` module to JavaScript's `Promise` methods.
"""

from pulse.transpiler.nodes import JSArray, JSExpr, JSIdentifier, JSMemberCall
from pulse.transpiler.py_module import PyModule


class PyAsyncio(PyModule):
	"""Provides transpilation for Python asyncio functions to JavaScript Promise methods."""

	@staticmethod
	def gather(*coros: JSExpr, **kwargs: JSExpr) -> JSExpr:
		"""Transpile asyncio.gather to Promise.all or Promise.allSettled.

		Args:
			*coros: Variable number of coroutine/promise expressions
			**kwargs: Keyword arguments, including return_exceptions

		Returns:
			JSExpr representing Promise.all([...]) or Promise.allSettled([...])
		"""
		# Convert coros to array
		promises = JSArray(list(coros))

		# Check return_exceptions keyword argument
		return_exceptions = kwargs.get("return_exceptions")
		if return_exceptions is not None:
			# Check if it's a boolean true (JSBoolean(True))
			from pulse.transpiler.nodes import JSBoolean

			if isinstance(return_exceptions, JSBoolean) and return_exceptions.value:
				# Promise.allSettled returns results with status
				return JSMemberCall(JSIdentifier("Promise"), "allSettled", [promises])

		# Default: Promise.all fails fast on first rejection
		return JSMemberCall(JSIdentifier("Promise"), "all", [promises])
