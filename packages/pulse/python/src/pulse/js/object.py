"""
JavaScript Object builtin module.

Usage:
    import pulse.js.object as Object
    Object.keys({"a": 1})         # -> Object.keys({"a": 1})
    Object.assign({}, {"a": 1})   # -> Object.assign({}, {"a": 1})
    Object.is(x, y)                # -> Object.is(x, y)

    # Note: For 'is' (Python keyword), use namespace import:
    # import pulse.js.object as Object; Object.is(...)
    # Or use the underscore version for direct import:
    from pulse.js.object import keys, assign, is_
    keys({"a": 1})                # -> Object.keys({"a": 1})
    assign({}, {"a": 1})          # -> Object.assign({}, {"a": 1})
    is_(x, y)                     # -> Object.is(x, y)
"""

from pulse.transpiler.js_module import register_js_module as _register_js_module


class Object:
	"""JavaScript Object namespace."""

	@staticmethod
	def assign(target: object, *sources: object) -> object: ...

	@staticmethod
	def create(
		proto: object | None, propertiesObject: object | None = None
	) -> object: ...

	@staticmethod
	def defineProperty(obj: object, prop: str, descriptor: object) -> object: ...

	@staticmethod
	def defineProperties(obj: object, props: object) -> object: ...

	@staticmethod
	def entries(obj: object) -> list[tuple[str, object]]: ...

	@staticmethod
	def freeze(obj: object) -> object: ...

	@staticmethod
	def fromEntries(entries: list[tuple[str, object]]) -> object: ...

	@staticmethod
	def getOwnPropertyDescriptor(obj: object, prop: str) -> object | None: ...

	@staticmethod
	def getOwnPropertyDescriptors(obj: object) -> object: ...

	@staticmethod
	def getOwnPropertyNames(obj: object) -> list[str]: ...

	@staticmethod
	def getOwnPropertySymbols(obj: object) -> list[object]: ...

	@staticmethod
	def getPrototypeOf(obj: object) -> object | None: ...

	@staticmethod
	def hasOwn(obj: object, prop: str) -> bool: ...

	@staticmethod
	def is_(value1: object, value2: object) -> bool: ...

	@staticmethod
	def isExtensible(obj: object) -> bool: ...

	@staticmethod
	def isFrozen(obj: object) -> bool: ...

	@staticmethod
	def isSealed(obj: object) -> bool: ...

	@staticmethod
	def keys(obj: object) -> list[str]: ...

	@staticmethod
	def preventExtensions(obj: object) -> object: ...

	@staticmethod
	def seal(obj: object) -> object: ...

	@staticmethod
	def setPrototypeOf(obj: object, prototype: object | None) -> object: ...

	@staticmethod
	def values(obj: object) -> list[object]: ...


# Self-register this module as a JS builtin
_register_js_module(name="Object", global_scope=True)
