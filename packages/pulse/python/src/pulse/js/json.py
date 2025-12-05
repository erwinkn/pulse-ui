"""
JavaScript JSON builtin module.

Usage:
    import pulse.js.json as JSON
    JSON.stringify({"a": 1})      # -> JSON.stringify({"a": 1})
    JSON.parse('{"a": 1}')        # -> JSON.parse('{"a": 1}')

    from pulse.js.json import stringify, parse
    stringify({"a": 1})           # -> JSON.stringify({"a": 1})
    parse('{"a": 1}')             # -> JSON.parse('{"a": 1}')
"""

from __future__ import annotations

from pulse.transpiler.js_module import register_js_module


# Static Methods (type stubs for IDE support)
def parse(text: str, reviver: object | None = None) -> object: ...
def stringify(
	value: object, replacer: object | None = None, space: int | str | None = None
) -> str: ...


# Self-register this module as a JS builtin
register_js_module(name="JSON")
