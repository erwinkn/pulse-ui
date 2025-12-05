"""
JavaScript String builtin module.

Usage:
    import pulse.js.string as String
    String.fromCharCode(65)        # -> String.fromCharCode(65)
    String.fromCodePoint(0x1F600)  # -> String.fromCodePoint(0x1F600)

    from pulse.js.string import fromCharCode, fromCodePoint
    fromCharCode(65)               # -> String.fromCharCode(65)
    fromCodePoint(0x1F600)         # -> String.fromCodePoint(0x1F600)
"""

from __future__ import annotations

from pulse.transpiler.js_module import register_js_module


# Static Methods (type stubs for IDE support)
def fromCharCode(*codes: int) -> str: ...
def fromCodePoint(*codePoints: int) -> str: ...
def raw(template: str, *substitutions: str) -> str: ...


# Self-register this module as a JS builtin
register_js_module(name="String", global_scope=True)
