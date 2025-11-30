from __future__ import annotations

from typing import TypeAlias

from pulse.javascript_v2.errors import JSCompilationError
from pulse.javascript_v2.nodes import (
	JSArray,
	JSBoolean,
	JSExpr,
	JSIdentifier,
	JSNew,
	JSNumber,
	JSString,
)

JsPrimitive: TypeAlias = bool | int | float | str | None
JsValue: TypeAlias = "JsPrimitive | list[JsValue] | tuple[JsValue, ...] | set[JsValue] | frozenset[JsValue] | dict[str, JsValue]"
JsVar: TypeAlias = "JsValue | JSExpr"

# Global cache for deduplication across all transpiled functions
CONSTANTS_CACHE: dict[int, JSExpr] = {}  # id(value) -> JSExpr


def const_to_js(value: JsValue) -> JSExpr:
	# Check cache first (uses id for identity-based deduplication)
	value_id = id(value)
	if value_id in CONSTANTS_CACHE:
		return CONSTANTS_CACHE[value_id]

	result: JSExpr
	if value is None:
		# Represent None as undefined for our JS subset
		result = JSIdentifier("undefined")
	elif isinstance(value, bool):
		result = JSBoolean(value)
	elif isinstance(value, (int, float)):
		result = JSNumber(value)
	elif isinstance(value, str):
		result = JSString(value)
	elif isinstance(value, (list, tuple)):
		result = JSArray([const_to_js(v) for v in value])
	elif isinstance(value, (set, frozenset)):
		result = JSNew(
			JSIdentifier("Set"),
			[JSArray([const_to_js(v) for v in value])],
		)
	elif isinstance(value, dict):
		# Normalize Python dict constants to Map semantics so methods like .get() work
		entries: list[JSExpr] = []
		for k, v in value.items():
			if not isinstance(k, str):
				raise JSCompilationError("Only string keys supported in constant dicts")
			entries.append(JSArray([JSString(k), const_to_js(v)]))
		result = JSNew(JSIdentifier("Map"), [JSArray(entries)])
	else:
		raise JSCompilationError(
			f"Unsupported global constant: {type(value).__name__} (value: {value!r})"
		)

	CONSTANTS_CACHE[value_id] = result
	return result


def jsify(value: JsVar) -> JSExpr:
	if not isinstance(value, JSExpr):
		return const_to_js(value)
	return value
