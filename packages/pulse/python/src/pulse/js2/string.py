"""
JavaScript String builtin module.

Usage:
    import pulse.js2.string as String
    String.fromCharCode(65)        # -> String.fromCharCode(65)
    String.fromCodePoint(0x1F600)  # -> String.fromCodePoint(0x1F600)

    from pulse.js2.string import fromCharCode, fromCodePoint
    fromCharCode(65)               # -> String.fromCharCode(65)
    fromCodePoint(0x1F600)         # -> String.fromCodePoint(0x1F600)
"""

from typing import Any as _Any

from pulse.transpiler_v2.js_module import JsModule


class String:
	"""JavaScript String constructor."""

	def __init__(self, value: _Any) -> None: ...

	@staticmethod
	def fromCharCode(*codes: int) -> str: ...

	@staticmethod
	def fromCodePoint(*codePoints: int) -> str: ...

	@staticmethod
	def raw(template: str, *substitutions: str) -> str: ...


# Self-register this module as a JS builtin
JsModule.register(name="String")
