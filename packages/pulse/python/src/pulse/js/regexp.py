"""
JavaScript RegExp builtin module.

Usage:
    import pulse.js.regexp as RegExp
    RegExp(pattern, flags)        # -> new RegExp(pattern, flags)

    from pulse.js.regexp import RegExp
    RegExp(pattern, flags)        # -> new RegExp(pattern, flags)
"""

from __future__ import annotations

from typing import Protocol

from pulse.transpiler.js_module import register_js_module


class RegExp(Protocol):
	"""Protocol for JavaScript RegExp instances."""

	def __init__(self, pattern: str, flags: str | None = None): ...

	def exec(self, string: str) -> list[str] | None: ...
	def test(self, string: str) -> bool: ...

	source: str
	flags: str
	glob: bool  # JavaScript 'global' property
	ignoreCase: bool
	multiline: bool
	dotAll: bool
	unicode: bool
	sticky: bool
	lastIndex: int

	def toString(self) -> str: ...


# Self-register this module as a JS builtin
register_js_module(name="RegExp", global_scope=True)
