"""
JavaScript RegExp builtin module.

Usage:
    import pulse.js.regexp as RegExp
    RegExp(pattern, flags)        # -> new RegExp(pattern, flags)

    from pulse.js.regexp import RegExp
    RegExp(pattern, flags)        # -> new RegExp(pattern, flags)
"""

from pulse.transpiler.js_module import register_js_module as _register_js_module


class RegExp:
	"""Class for JavaScript RegExp instances."""

	def __init__(self, pattern: str, flags: str | None = None): ...

	def exec(self, string: str) -> list[str] | None: ...
	def test(self, string: str) -> bool: ...

	@property
	def source(self) -> str: ...

	@property
	def flags(self) -> str: ...

	@property
	def glob(self) -> bool: ...  # JavaScript 'global' property

	@property
	def ignoreCase(self) -> bool: ...

	@property
	def multiline(self) -> bool: ...

	@property
	def dotAll(self) -> bool: ...

	@property
	def unicode(self) -> bool: ...

	@property
	def sticky(self) -> bool: ...

	@property
	def lastIndex(self) -> int: ...

	def toString(self) -> str: ...


# Self-register this module as a JS builtin
_register_js_module(name="RegExp", global_scope=True)
