"""
JavaScript String builtin module.

Usage:
    from pulse.js2 import String
    String(x)                      # -> new String(x)
    String.fromCharCode(65)        # -> String.fromCharCode(65)
    String.fromCodePoint(0x1F600)  # -> String.fromCodePoint(0x1F600)

    # Or import from module directly:
    from pulse.js2.string import String
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


# Self-register this module as a JS builtin (global identifier)
JsModule.register(name=None)
