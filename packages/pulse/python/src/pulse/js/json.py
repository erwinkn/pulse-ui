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

from collections.abc import Callable as _Callable
from collections.abc import Sequence as _Sequence
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

# JSON types
JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
JSONReplacer = _Sequence[str | int] | _Callable[[str, JSONValue], JSONValue]
JSONReviver = _Callable[[str, JSONValue], JSONValue]

T = _TypeVar("T")


def parse(text: str, reviver: JSONReviver | None = None) -> JSONValue:
	"""Parse a JSON string into a JavaScript value.

	Args:
	    text: The JSON string to parse.
	    reviver: Optional function (key: str, value: Any) -> Any that transforms the parsed value.
	        Called for each key-value pair. Return the value to use, or undefined to omit.

	Returns:
	    The parsed JavaScript value (null, bool, number, string, array, or object).
	"""
	...


def stringify(
	value: JSONValue,
	replacer: JSONReplacer | None = None,
	space: int | str | None = None,
) -> str:
	"""Convert a JavaScript value to a JSON string.

	Args:
	    value: The value to convert to JSON.
	    replacer: Optional array of property names/indices, or function (key: str, value: Any) -> Any
	        that controls which properties are included. Return undefined to omit.
	    space: Optional indentation. Number for spaces per level, or string (up to 10 chars).

	Returns:
	    The JSON string representation of the value.
	"""
	...


# Self-register this module as a JS builtin
_register_js_module(name="JSON")
