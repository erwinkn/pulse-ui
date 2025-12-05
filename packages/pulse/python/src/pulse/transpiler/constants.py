from __future__ import annotations

from typing import TypeAlias, override

from pulse.transpiler.context import is_interpreted_mode
from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.ids import generate_id
from pulse.transpiler.nodes import (
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
CONSTANTS_CACHE: dict[int, "JsConstant"] = {}  # id(value) -> JsConstant


class JsConstant(JSExpr):
	"""Wrapper for constant values used in transpiled JS functions."""

	is_primary: bool = True

	value: object
	expr: JSExpr
	id: str
	name: str  # Original Python variable name (set by codegen)

	def __init__(self, value: object, expr: JSExpr, name: str = "") -> None:
		self.value = value
		self.expr = expr
		self.id = generate_id()
		self.name = name

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this constant."""
		return f"{self.name}_{self.id}" if self.name else f"_const_{self.id}"

	@override
	def emit(self) -> str:
		"""Emit JS code for this constant.

		In normal mode: returns the unique JS name (e.g., "CONSTANT_1")
		In interpreted mode: returns a get_object call (e.g., "get_object('CONSTANT_1')")
		"""
		base = self.js_name
		if is_interpreted_mode():
			return f"get_object('{base}')"
		return base


def _value_to_expr(value: JsValue) -> JSExpr:
	"""Convert a Python value to a JSExpr (no caching)."""
	if value is None:
		return JSIdentifier("undefined")
	elif isinstance(value, bool):
		return JSBoolean(value)
	elif isinstance(value, (int, float)):
		return JSNumber(value)
	elif isinstance(value, str):
		return JSString(value)
	elif isinstance(value, (list, tuple)):
		return JSArray([_value_to_expr(v) for v in value])
	elif isinstance(value, (set, frozenset)):
		return JSNew(
			JSIdentifier("Set"),
			[JSArray([_value_to_expr(v) for v in value])],
		)
	elif isinstance(value, dict):
		entries: list[JSExpr] = []
		for k, v in value.items():
			if not isinstance(k, str):
				raise JSCompilationError("Only string keys supported in constant dicts")
			entries.append(JSArray([JSString(k), _value_to_expr(v)]))
		return JSNew(JSIdentifier("Map"), [JSArray(entries)])
	else:
		raise JSCompilationError(
			f"Unsupported global constant: {type(value).__name__} (value: {value!r})"
		)


def const_to_js(value: JsValue, name: str = "") -> JsConstant:
	"""Convert a Python value to a JsConstant (cached by identity)."""
	value_id = id(value)
	if value_id in CONSTANTS_CACHE:
		return CONSTANTS_CACHE[value_id]

	expr = _value_to_expr(value)
	result = JsConstant(value, expr, name)
	CONSTANTS_CACHE[value_id] = result
	return result


def jsify(value: JsVar) -> JSExpr:
	if not isinstance(value, JSExpr):
		return const_to_js(value).expr
	return value


def registered_constants() -> list[JsConstant]:
	"""Get all registered JS constants."""
	return list(CONSTANTS_CACHE.values())
