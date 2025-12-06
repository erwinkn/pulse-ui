"""
Python builtin functions -> JavaScript equivalents for v2 transpiler.

This module provides transpilation for Python builtins to JavaScript.
"""

from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from typing import Any, cast, override

from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.nodes import (
	JSArray,
	JSArrowFunction,
	JSBinary,
	JSCall,
	JSComma,
	JSExpr,
	JSIdentifier,
	JSMember,
	JSMemberCall,
	JSNew,
	JSNumber,
	JSSpread,
	JSString,
	JSSubscript,
	JSTemplate,
	JSTertiary,
	JSTransformer,
	JSUnary,
	JSUndefined,
	js_transformer,
)


@js_transformer("print")
def transform_print(*args: Any) -> JSExpr:
	"""print(*args) -> console.log(...)"""
	return JSMemberCall(JSIdentifier("console"), "log", [JSExpr.of(a) for a in args])


@js_transformer("len")
def transform_len(x: Any) -> JSExpr:
	"""len(x) -> x.length ?? x.size"""
	# .length for strings/arrays, .size for sets/maps
	x = JSExpr.of(x)
	return JSBinary(JSMember(x, "length"), "??", JSMember(x, "size"))


@js_transformer("min")
def transform_min(*args: Any) -> JSExpr:
	"""min(*args) -> Math.min(...)"""
	return JSMemberCall(JSIdentifier("Math"), "min", [JSExpr.of(a) for a in args])


@js_transformer("max")
def transform_max(*args: Any) -> JSExpr:
	"""max(*args) -> Math.max(...)"""
	return JSMemberCall(JSIdentifier("Math"), "max", [JSExpr.of(a) for a in args])


@js_transformer("abs")
def transform_abs(x: Any) -> JSExpr:
	"""abs(x) -> Math.abs(x)"""
	return JSMemberCall(JSIdentifier("Math"), "abs", [JSExpr.of(x)])


@js_transformer("round")
def transform_round(number: Any, ndigits: Any = None) -> JSExpr:
	"""round(number, ndigits=None) -> Math.round(...) or toFixed(...)"""
	number = JSExpr.of(number)
	if ndigits is None:
		return JSCall(JSIdentifier("Math.round"), [number])
	# With ndigits: Number(x).toFixed(ndigits) for positive, complex for negative
	# For simplicity, assume positive ndigits (most common case)
	return JSMemberCall(
		JSCall(JSIdentifier("Number"), [number]), "toFixed", [JSExpr.of(ndigits)]
	)


@js_transformer("str")
def transform_str(x: Any) -> JSExpr:
	"""str(x) -> String(x)"""
	return JSCall(JSIdentifier("String"), [JSExpr.of(x)])


@js_transformer("int")
def transform_int(*args: Any) -> JSExpr:
	"""int(x) or int(x, base) -> parseInt(...)"""
	if builtins.len(args) == 1:
		return JSCall(JSIdentifier("parseInt"), [JSExpr.of(args[0])])
	if builtins.len(args) == 2:
		return JSCall(
			JSIdentifier("parseInt"), [JSExpr.of(args[0]), JSExpr.of(args[1])]
		)
	raise JSCompilationError("int() expects one or two arguments")


@js_transformer("float")
def transform_float(x: Any) -> JSExpr:
	"""float(x) -> parseFloat(x)"""
	return JSCall(JSIdentifier("parseFloat"), [JSExpr.of(x)])


@js_transformer("list")
def transform_list(x: Any) -> JSExpr:
	"""list(x) -> Array.from(x)"""
	return JSCall(JSMember(JSIdentifier("Array"), "from"), [JSExpr.of(x)])


@js_transformer("bool")
def transform_bool(x: Any) -> JSExpr:
	"""bool(x) -> Boolean(x)"""
	return JSCall(JSIdentifier("Boolean"), [JSExpr.of(x)])


@js_transformer("set")
def transform_set(*args: Any) -> JSExpr:
	"""set() or set(iterable) -> new Set([iterable])"""
	if builtins.len(args) == 0:
		return JSNew(JSIdentifier("Set"), [])
	if builtins.len(args) == 1:
		return JSNew(JSIdentifier("Set"), [JSExpr.of(args[0])])
	raise JSCompilationError("set() expects at most one argument")


@js_transformer("tuple")
def transform_tuple(*args: Any) -> JSExpr:
	"""tuple() or tuple(iterable) -> Array.from(iterable)"""
	if builtins.len(args) == 0:
		return JSArray([])
	if builtins.len(args) == 1:
		return JSCall(JSMember(JSIdentifier("Array"), "from"), [JSExpr.of(args[0])])
	raise JSCompilationError("tuple() expects at most one argument")


@js_transformer("dict")
def transform_dict(*args: Any) -> JSExpr:
	"""dict() or dict(iterable) -> new Map([iterable])"""
	if builtins.len(args) == 0:
		return JSNew(JSIdentifier("Map"), [])
	if builtins.len(args) == 1:
		return JSNew(JSIdentifier("Map"), [JSExpr.of(args[0])])
	raise JSCompilationError("dict() expects at most one argument")


@js_transformer("filter")
def transform_filter(*args: Any) -> JSExpr:
	"""filter(func, iterable) -> iterable.filter(func)"""
	if not (1 <= builtins.len(args) <= 2):
		raise JSCompilationError("filter() expects one or two arguments")
	if builtins.len(args) == 1:
		# filter(iterable) - filter truthy values
		iterable = JSExpr.of(args[0])
		predicate = JSArrowFunction("v", JSIdentifier("v"))
		return JSMemberCall(iterable, "filter", [predicate])
	func, iterable = JSExpr.of(args[0]), JSExpr.of(args[1])
	# filter(None, iterable) means filter truthy
	if builtins.isinstance(func, JSUndefined):
		func = JSArrowFunction("v", JSIdentifier("v"))
	return JSMemberCall(iterable, "filter", [func])


@js_transformer("map")
def transform_map(func: Any, iterable: Any) -> JSExpr:
	"""map(func, iterable) -> iterable.map(func)"""
	return JSMemberCall(JSExpr.of(iterable), "map", [JSExpr.of(func)])


@js_transformer("reversed")
def transform_reversed(iterable: Any) -> JSExpr:
	"""reversed(iterable) -> iterable.slice().reverse()"""
	return JSMemberCall(JSMemberCall(JSExpr.of(iterable), "slice", []), "reverse", [])


@js_transformer("enumerate")
def transform_enumerate(iterable: Any, start: Any = None) -> JSExpr:
	"""enumerate(iterable, start=0) -> iterable.map((v, i) => [i + start, v])"""
	base = JSNumber(0) if start is None else JSExpr.of(start)
	return JSMemberCall(
		JSExpr.of(iterable),
		"map",
		[
			JSArrowFunction(
				"(v, i)",
				JSArray([JSBinary(JSIdentifier("i"), "+", base), JSIdentifier("v")]),
			)
		],
	)


@js_transformer("range")
def transform_range(*args: Any) -> JSExpr:
	"""range(stop) or range(start, stop[, step]) -> Array.from(...)"""
	if not (1 <= builtins.len(args) <= 3):
		raise JSCompilationError("range() expects 1 to 3 arguments")
	if builtins.len(args) == 1:
		stop = JSExpr.of(args[0])
		length = JSMemberCall(JSIdentifier("Math"), "max", [JSNumber(0), stop])
		return JSCall(
			JSMember(JSIdentifier("Array"), "from"),
			[JSMemberCall(JSNew(JSIdentifier("Array"), [length]), "keys", [])],
		)
	start = JSExpr.of(args[0])
	stop = JSExpr.of(args[1])
	step = JSExpr.of(args[2]) if builtins.len(args) == 3 else JSNumber(1)
	# count = max(0, ceil((stop - start) / step))
	diff = JSBinary(stop, "-", start)
	div = JSBinary(diff, "/", step)
	ceil = JSMemberCall(JSIdentifier("Math"), "ceil", [div])
	count = JSMemberCall(JSIdentifier("Math"), "max", [JSNumber(0), ceil])
	# Array.from(new Array(count).keys(), i => start + i * step)
	return JSCall(
		JSMember(JSIdentifier("Array"), "from"),
		[
			JSMemberCall(JSNew(JSIdentifier("Array"), [count]), "keys", []),
			JSArrowFunction(
				"i", JSBinary(start, "+", JSBinary(JSIdentifier("i"), "*", step))
			),
		],
	)


@js_transformer("sorted")
def transform_sorted(*args: Any, key: Any = None, reverse: Any = None) -> JSExpr:
	"""sorted(iterable, key=None, reverse=False) -> iterable.slice().sort(...)"""
	if builtins.len(args) != 1:
		raise JSCompilationError("sorted() expects exactly one positional argument")
	iterable = JSExpr.of(args[0])
	clone = JSMemberCall(iterable, "slice", [])
	# comparator: (a, b) => (a > b) - (a < b) or with key
	if key is None:
		cmp_expr = JSBinary(
			JSBinary(JSIdentifier("a"), ">", JSIdentifier("b")),
			"-",
			JSBinary(JSIdentifier("a"), "<", JSIdentifier("b")),
		)
	else:
		key_js = JSExpr.of(key)
		cmp_expr = JSBinary(
			JSBinary(
				JSCall(key_js, [JSIdentifier("a")]),
				">",
				JSCall(key_js, [JSIdentifier("b")]),
			),
			"-",
			JSBinary(
				JSCall(key_js, [JSIdentifier("a")]),
				"<",
				JSCall(key_js, [JSIdentifier("b")]),
			),
		)
	sort_call = JSMemberCall(clone, "sort", [JSArrowFunction("(a, b)", cmp_expr)])
	if reverse is None:
		return sort_call
	return JSTertiary(
		JSExpr.of(reverse), JSMemberCall(sort_call, "reverse", []), sort_call
	)


@js_transformer("zip")
def transform_zip(*args: Any) -> JSExpr:
	"""zip(*iterables) -> Array.from(...) with paired elements"""
	if builtins.len(args) == 0:
		return JSArray([])

	js_args = [JSExpr.of(a) for a in args]

	def length_of(x: JSExpr) -> JSExpr:
		return JSMember(x, "length")

	min_len = length_of(js_args[0])
	for it in js_args[1:]:
		min_len = JSMemberCall(JSIdentifier("Math"), "min", [min_len, length_of(it)])

	elems = [JSSubscript(arg, JSIdentifier("i")) for arg in js_args]
	make_pair = JSArrowFunction("i", JSArray(elems))
	return JSCall(
		JSMember(JSIdentifier("Array"), "from"),
		[JSMemberCall(JSNew(JSIdentifier("Array"), [min_len]), "keys", []), make_pair],
	)


@js_transformer("pow")
def transform_pow(*args: Any) -> JSExpr:
	"""pow(base, exp) -> Math.pow(base, exp)"""
	if builtins.len(args) != 2:
		raise JSCompilationError("pow() expects exactly two arguments")
	return JSMemberCall(
		JSIdentifier("Math"), "pow", [JSExpr.of(args[0]), JSExpr.of(args[1])]
	)


@js_transformer("chr")
def transform_chr(x: Any) -> JSExpr:
	"""chr(x) -> String.fromCharCode(x)"""
	return JSMemberCall(JSIdentifier("String"), "fromCharCode", [JSExpr.of(x)])


@js_transformer("ord")
def transform_ord(x: Any) -> JSExpr:
	"""ord(x) -> x.charCodeAt(0)"""
	return JSMemberCall(JSExpr.of(x), "charCodeAt", [JSNumber(0)])


@js_transformer("any")
def transform_any(x: Any) -> JSExpr:
	"""any(iterable) -> iterable.some(v => v)"""
	x = JSExpr.of(x)
	# Optimization: if x is a map call, use .some directly
	if builtins.isinstance(x, JSMemberCall) and x.method == "map" and x.args:
		return JSMemberCall(x.obj, "some", [x.args[0]])
	return JSMemberCall(x, "some", [JSArrowFunction("v", JSIdentifier("v"))])


@js_transformer("all")
def transform_all(x: Any) -> JSExpr:
	"""all(iterable) -> iterable.every(v => v)"""
	x = JSExpr.of(x)
	# Optimization: if x is a map call, use .every directly
	if builtins.isinstance(x, JSMemberCall) and x.method == "map" and x.args:
		return JSMemberCall(x.obj, "every", [x.args[0]])
	return JSMemberCall(x, "every", [JSArrowFunction("v", JSIdentifier("v"))])


@js_transformer("sum")
def transform_sum(*args: Any) -> JSExpr:
	"""sum(iterable, start=0) -> iterable.reduce((a, b) => a + b, start)"""
	if not (1 <= builtins.len(args) <= 2):
		raise JSCompilationError("sum() expects one or two arguments")
	start = JSExpr.of(args[1]) if builtins.len(args) == 2 else JSNumber(0)
	base = JSExpr.of(args[0])
	reducer = JSArrowFunction(
		"(a, b)", JSBinary(JSIdentifier("a"), "+", JSIdentifier("b"))
	)
	return JSMemberCall(base, "reduce", [reducer, start])


@js_transformer("divmod")
def transform_divmod(x: Any, y: Any) -> JSExpr:
	"""divmod(x, y) -> [Math.floor(x / y), x - Math.floor(x / y) * y]"""
	x, y = JSExpr.of(x), JSExpr.of(y)
	q = JSMemberCall(JSIdentifier("Math"), "floor", [JSBinary(x, "/", y)])
	r = JSBinary(x, "-", JSBinary(q, "*", y))
	return JSArray([q, r])


@js_transformer("isinstance")
def transform_isinstance(*args: Any) -> JSExpr:
	"""isinstance is not directly supported in v2; raise error."""
	raise JSCompilationError(
		"isinstance() is not supported in JavaScript transpilation"
	)


# Registry of builtin transformers
BUILTINS = cast(
	builtins.dict[builtins.str, JSTransformer],
	{
		"print": transform_print,
		"len": transform_len,
		"min": transform_min,
		"max": transform_max,
		"abs": transform_abs,
		"round": transform_round,
		"str": transform_str,
		"int": transform_int,
		"float": transform_float,
		"list": transform_list,
		"bool": transform_bool,
		"set": transform_set,
		"tuple": transform_tuple,
		"dict": transform_dict,
		"filter": transform_filter,
		"map": transform_map,
		"reversed": transform_reversed,
		"enumerate": transform_enumerate,
		"range": transform_range,
		"sorted": transform_sorted,
		"zip": transform_zip,
		"pow": transform_pow,
		"chr": transform_chr,
		"ord": transform_ord,
		"any": transform_any,
		"all": transform_all,
		"sum": transform_sum,
		"divmod": transform_divmod,
		"isinstance": transform_isinstance,
	},
)


# =============================================================================
# Builtin Method Transpilation
# =============================================================================
#
# Methods are organized into classes by type (StringMethods, ListMethods, etc.).
# Each class contains methods that transpile Python methods to their JS equivalents.
#
# Methods return None to fall through to the default method call (when no
# transformation is needed).


class BuiltinMethods(ABC):
	"""Abstract base class for type-specific method transpilation."""

	def __init__(self, obj: JSExpr) -> None:
		self.this: JSExpr = obj

	@classmethod
	@abstractmethod
	def __runtime_check__(cls, expr: JSExpr) -> JSExpr:
		"""Return a JS expression that checks if expr is this type at runtime."""
		...

	@classmethod
	@abstractmethod
	def __methods__(cls) -> builtins.set[str]:
		"""Return the set of method names this class handles."""
		...


class StringMethods(BuiltinMethods):
	"""String method transpilation."""

	@classmethod
	@override
	def __runtime_check__(cls, expr: JSExpr) -> JSExpr:
		return JSBinary(JSUnary("typeof", expr), "===", JSString("string"))

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return STR_METHODS

	def lower(self) -> JSExpr:
		"""str.lower() -> str.toLowerCase()"""
		return JSMemberCall(self.this, "toLowerCase", [])

	def upper(self) -> JSExpr:
		"""str.upper() -> str.toUpperCase()"""
		return JSMemberCall(self.this, "toUpperCase", [])

	def strip(self) -> JSExpr:
		"""str.strip() -> str.trim()"""
		return JSMemberCall(self.this, "trim", [])

	def lstrip(self) -> JSExpr:
		"""str.lstrip() -> str.trimStart()"""
		return JSMemberCall(self.this, "trimStart", [])

	def rstrip(self) -> JSExpr:
		"""str.rstrip() -> str.trimEnd()"""
		return JSMemberCall(self.this, "trimEnd", [])

	def zfill(self, width: JSExpr) -> JSExpr:
		"""str.zfill(width) -> str.padStart(width, '0')"""
		return JSMemberCall(self.this, "padStart", [width, JSString("0")])

	def startswith(self, prefix: JSExpr) -> JSExpr:
		"""str.startswith(prefix) -> str.startsWith(prefix)"""
		return JSMemberCall(self.this, "startsWith", [prefix])

	def endswith(self, suffix: JSExpr) -> JSExpr:
		"""str.endswith(suffix) -> str.endsWith(suffix)"""
		return JSMemberCall(self.this, "endsWith", [suffix])

	def replace(self, old: JSExpr, new: JSExpr) -> JSExpr:
		"""str.replace(old, new) -> str.replaceAll(old, new)"""
		return JSMemberCall(self.this, "replaceAll", [old, new])

	def capitalize(self) -> JSExpr:
		"""str.capitalize() -> str.charAt(0).toUpperCase() + str.slice(1).toLowerCase()"""
		left = JSMemberCall(
			JSMemberCall(self.this, "charAt", [JSNumber(0)]), "toUpperCase", []
		)
		right = JSMemberCall(
			JSMemberCall(self.this, "slice", [JSNumber(1)]), "toLowerCase", []
		)
		return JSBinary(left, "+", right)

	def split(self, sep: JSExpr) -> JSExpr | None:
		"""str.split() doesn't need transformation."""
		return None

	def join(self, iterable: JSExpr) -> JSExpr:
		"""str.join(iterable) -> iterable.join(str)"""
		return JSMemberCall(iterable, "join", [self.this])


STR_METHODS = {k for k in StringMethods.__dict__ if not k.startswith("_")}


class ListMethods(BuiltinMethods):
	"""List method transpilation."""

	@classmethod
	@override
	def __runtime_check__(cls, expr: JSExpr) -> JSExpr:
		return JSMemberCall(JSIdentifier("Array"), "isArray", [expr])

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return LIST_METHODS

	def append(self, value: JSExpr) -> JSExpr:
		"""list.append(value) -> (list.push(value), undefined)"""
		return JSComma([JSMemberCall(self.this, "push", [value]), JSUndefined()])

	def extend(self, iterable: JSExpr) -> JSExpr:
		"""list.extend(iterable) -> (list.push(...iterable), undefined)"""
		return JSComma(
			[JSMemberCall(self.this, "push", [JSSpread(iterable)]), JSUndefined()]
		)

	def pop(self, index: JSExpr | None = None) -> JSExpr | None:
		"""list.pop() or list.pop(index)"""
		if index is None:
			return None  # Fall through to default .pop()
		return JSSubscript(
			JSMemberCall(self.this, "splice", [index, JSNumber(1)]), JSNumber(0)
		)

	def copy(self) -> JSExpr:
		"""list.copy() -> list.slice()"""
		return JSMemberCall(self.this, "slice", [])

	def count(self, value: JSExpr) -> JSExpr:
		"""list.count(value) -> list.filter(v => v === value).length"""
		return JSMember(
			JSMemberCall(
				self.this,
				"filter",
				[JSArrowFunction("v", JSBinary(JSIdentifier("v"), "===", value))],
			),
			"length",
		)

	def index(self, value: JSExpr) -> JSExpr:
		"""list.index(value) -> list.indexOf(value)"""
		return JSMemberCall(self.this, "indexOf", [value])

	def reverse(self) -> JSExpr:
		"""list.reverse() -> (list.reverse(), undefined)"""
		return JSComma([JSMemberCall(self.this, "reverse", []), JSUndefined()])

	def sort(self) -> JSExpr:
		"""list.sort() -> (list.sort(), undefined)"""
		return JSComma([JSMemberCall(self.this, "sort", []), JSUndefined()])


LIST_METHODS = {k for k in ListMethods.__dict__ if not k.startswith("_")}


class DictMethods(BuiltinMethods):
	"""Dict (Map) method transpilation."""

	@classmethod
	@override
	def __runtime_check__(cls, expr: JSExpr) -> JSExpr:
		return JSBinary(expr, "instanceof", JSIdentifier("Map"))

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return DICT_METHODS

	def get(self, key: JSExpr, default: JSExpr | None = None) -> JSExpr | None:
		"""dict.get(key, default) -> dict.get(key) ?? default"""
		if default is None:
			return None  # Fall through to default .get()
		return JSBinary(JSMemberCall(self.this, "get", [key]), "??", default)

	def keys(self) -> JSExpr:
		"""dict.keys() -> [...dict.keys()]"""
		return JSArray([JSSpread(JSMemberCall(self.this, "keys", []))])

	def values(self) -> JSExpr:
		"""dict.values() -> [...dict.values()]"""
		return JSArray([JSSpread(JSMemberCall(self.this, "values", []))])

	def items(self) -> JSExpr:
		"""dict.items() -> [...dict.entries()]"""
		return JSArray([JSSpread(JSMemberCall(self.this, "entries", []))])

	def copy(self) -> JSExpr:
		"""dict.copy() -> new Map(dict.entries())"""
		return JSNew(JSIdentifier("Map"), [JSMemberCall(self.this, "entries", [])])

	def clear(self) -> JSExpr | None:
		"""dict.clear() doesn't need transformation."""
		return None


DICT_METHODS = {k for k in DictMethods.__dict__ if not k.startswith("_")}


class SetMethods(BuiltinMethods):
	"""Set method transpilation."""

	@classmethod
	@override
	def __runtime_check__(cls, expr: JSExpr) -> JSExpr:
		return JSBinary(expr, "instanceof", JSIdentifier("Set"))

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return SET_METHODS

	def add(self, value: JSExpr) -> JSExpr | None:
		"""set.add() doesn't need transformation."""
		return None

	def remove(self, value: JSExpr) -> JSExpr:
		"""set.remove(value) -> set.delete(value)"""
		return JSMemberCall(self.this, "delete", [value])

	def discard(self, value: JSExpr) -> JSExpr:
		"""set.discard(value) -> set.delete(value)"""
		return JSMemberCall(self.this, "delete", [value])

	def clear(self) -> JSExpr | None:
		"""set.clear() doesn't need transformation."""
		return None


SET_METHODS = {k for k in SetMethods.__dict__ if not k.startswith("_")}


# Collect all known method names for quick lookup
ALL_METHODS = STR_METHODS | LIST_METHODS | DICT_METHODS | SET_METHODS

# Method classes in priority order (higher priority = later in list = outermost ternary)
# We prefer string/list semantics first, then set, then dict.
METHOD_CLASSES: list[type[BuiltinMethods]] = [
	DictMethods,
	SetMethods,
	ListMethods,
	StringMethods,
]


def _try_dispatch_method(
	cls: type[BuiltinMethods], obj: JSExpr, method: str, args: list[JSExpr]
) -> JSExpr | None:
	"""Try to dispatch a method call to a specific builtin class.

	Returns the transformed expression, or None if the method returns None
	(fall through to default) or if dispatch fails.
	"""
	if method not in cls.__methods__():
		return None

	try:
		handler = cls(obj)
		method_fn = getattr(handler, method, None)
		if method_fn is None:
			return None
		return method_fn(*args)
	except TypeError:
		return None


def emit_method(obj: JSExpr, method: str, args: list[JSExpr]) -> JSExpr | None:
	"""Emit a method call, handling Python builtin methods.

	For known literal types (JSString, JSTemplate, JSArray, JSNew Set/Map),
	dispatches directly without runtime checks.

	For unknown types, builds a ternary chain that checks types at runtime
	and dispatches to the appropriate method implementation.

	Returns:
		JSExpr if the method should be transpiled specially
		None if the method should be emitted as a regular method call
	"""
	if method not in ALL_METHODS:
		return None

	# Fast path: known literal types - dispatch directly without runtime checks
	if builtins.isinstance(obj, (JSString, JSTemplate)):
		if method in StringMethods.__methods__():
			result = _try_dispatch_method(StringMethods, obj, method, args)
			if result is not None:
				return result
		return None

	if builtins.isinstance(obj, JSArray):
		if method in ListMethods.__methods__():
			result = _try_dispatch_method(ListMethods, obj, method, args)
			if result is not None:
				return result
		return None

	# Fast path: new Set(...) and new Map(...) are known types
	if builtins.isinstance(obj, JSNew) and builtins.isinstance(obj.ctor, JSIdentifier):
		if obj.ctor.name == "Set" and method in SetMethods.__methods__():
			result = _try_dispatch_method(SetMethods, obj, method, args)
			if result is not None:
				return result
			return None
		if obj.ctor.name == "Map" and method in DictMethods.__methods__():
			result = _try_dispatch_method(DictMethods, obj, method, args)
			if result is not None:
				return result
			return None

	# Slow path: unknown type - build ternary chain with runtime type checks
	# Start with the default fallback (regular method call)
	default_expr = JSMemberCall(obj, method, args)
	expr: JSExpr = default_expr

	# Apply in increasing priority so that later (higher priority) wrappers
	# end up outermost in the final expression.
	for cls in METHOD_CLASSES:
		if method not in cls.__methods__():
			continue

		dispatch_expr = _try_dispatch_method(cls, obj, method, args)
		if dispatch_expr is not None:
			expr = JSTertiary(cls.__runtime_check__(obj), dispatch_expr, expr)

	# If we built ternaries, return them; otherwise return None to fall through
	if expr is not default_expr:
		return expr

	return None
