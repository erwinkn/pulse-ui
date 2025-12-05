"""
JavaScript Promise builtin module.

Usage:
    import pulse.js.promise as Promise
    Promise.resolve(value)        # -> Promise.resolve(value)
    Promise.reject(reason)        # -> Promise.reject(reason)

    from pulse.js.promise import resolve, reject, all, allSettled, race, any
    resolve(value)                # -> Promise.resolve(value)
    reject(reason)                 # -> Promise.reject(reason)
"""

from pulse.transpiler.js_module import register_js_module as _register_js_module


class Promise:
	"""JavaScript Promise constructor."""

	def __init__(self, executor: object) -> None: ...

	@staticmethod
	def all(iterable: list[object]) -> object: ...

	@staticmethod
	def allSettled(iterable: list[object]) -> object: ...

	@staticmethod
	def any(iterable: list[object]) -> object: ...

	@staticmethod
	def race(iterable: list[object]) -> object: ...

	@staticmethod
	def reject(reason: object) -> object: ...

	@staticmethod
	def resolve(value: object) -> object: ...


# Self-register this module as a JS builtin
_register_js_module(name="Promise", global_scope=True)
