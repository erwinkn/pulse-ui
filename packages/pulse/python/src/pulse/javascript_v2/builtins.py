"""
Python builtin functions -> JavaScript equivalents for v2 transpiler.

This module provides transpilation for Python builtins to JavaScript.
"""

from __future__ import annotations

from collections.abc import Callable

from pulse.javascript_v2.errors import JSCompilationError
from pulse.javascript_v2.nodes import (
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
	JSTertiary,
	JSUndefined,
)


def emit_print(*args: JSExpr) -> JSExpr:
	"""print(*args) -> console.log(...)"""
	return JSMemberCall(JSIdentifier("console"), "log", list(args))


def emit_len(x: JSExpr) -> JSExpr:
	"""len(x) -> x.length ?? x.size"""
	# .length for strings/arrays, .size for sets/maps
	return JSBinary(JSMember(x, "length"), "??", JSMember(x, "size"))


def emit_min(*args: JSExpr) -> JSExpr:
	"""min(*args) -> Math.min(...)"""
	return JSMemberCall(JSIdentifier("Math"), "min", list(args))


def emit_max(*args: JSExpr) -> JSExpr:
	"""max(*args) -> Math.max(...)"""
	return JSMemberCall(JSIdentifier("Math"), "max", list(args))


def emit_abs(x: JSExpr) -> JSExpr:
	"""abs(x) -> Math.abs(x)"""
	return JSMemberCall(JSIdentifier("Math"), "abs", [x])


def emit_round(number: JSExpr, ndigits: JSExpr | None = None) -> JSExpr:
	"""round(number, ndigits=None) -> Math.round(...) or toFixed(...)"""
	if ndigits is None:
		return JSCall(JSIdentifier("Math.round"), [number])
	# With ndigits: Number(x).toFixed(ndigits) for positive, complex for negative
	# For simplicity, assume positive ndigits (most common case)
	return JSMemberCall(JSCall(JSIdentifier("Number"), [number]), "toFixed", [ndigits])


def emit_str(x: JSExpr) -> JSExpr:
	"""str(x) -> String(x)"""
	return JSCall(JSIdentifier("String"), [x])


def emit_int(*args: JSExpr) -> JSExpr:
	"""int(x) or int(x, base) -> parseInt(...)"""
	if len(args) == 1:
		return JSCall(JSIdentifier("parseInt"), [args[0]])
	if len(args) == 2:
		return JSCall(JSIdentifier("parseInt"), [args[0], args[1]])
	raise JSCompilationError("int() expects one or two arguments")


def emit_float(x: JSExpr) -> JSExpr:
	"""float(x) -> parseFloat(x)"""
	return JSCall(JSIdentifier("parseFloat"), [x])


def emit_list(x: JSExpr) -> JSExpr:
	"""list(x) -> Array.from(x)"""
	return JSCall(JSMember(JSIdentifier("Array"), "from"), [x])


def emit_bool(x: JSExpr) -> JSExpr:
	"""bool(x) -> Boolean(x)"""
	return JSCall(JSIdentifier("Boolean"), [x])


def emit_set(*args: JSExpr) -> JSExpr:
	"""set() or set(iterable) -> new Set([iterable])"""
	if len(args) == 0:
		return JSNew(JSIdentifier("Set"), [])
	if len(args) == 1:
		return JSNew(JSIdentifier("Set"), [args[0]])
	raise JSCompilationError("set() expects at most one argument")


def emit_tuple(*args: JSExpr) -> JSExpr:
	"""tuple() or tuple(iterable) -> Array.from(iterable)"""
	if len(args) == 0:
		return JSArray([])
	if len(args) == 1:
		return JSCall(JSMember(JSIdentifier("Array"), "from"), [args[0]])
	raise JSCompilationError("tuple() expects at most one argument")


def emit_dict(*args: JSExpr) -> JSExpr:
	"""dict() or dict(iterable) -> new Map([iterable])"""
	if len(args) == 0:
		return JSNew(JSIdentifier("Map"), [])
	if len(args) == 1:
		return JSNew(JSIdentifier("Map"), [args[0]])
	raise JSCompilationError("dict() expects at most one argument")


def emit_filter(*args: JSExpr) -> JSExpr:
	"""filter(func, iterable) -> iterable.filter(func)"""
	if not (1 <= len(args) <= 2):
		raise JSCompilationError("filter() expects one or two arguments")
	if len(args) == 1:
		# filter(iterable) - filter truthy values
		iterable = args[0]
		predicate = JSArrowFunction("v", JSIdentifier("v"))
		return JSMemberCall(iterable, "filter", [predicate])
	func, iterable = args[0], args[1]
	# filter(None, iterable) means filter truthy
	if isinstance(func, JSUndefined):
		func = JSArrowFunction("v", JSIdentifier("v"))
	return JSMemberCall(iterable, "filter", [func])


def emit_map(func: JSExpr, iterable: JSExpr) -> JSExpr:
	"""map(func, iterable) -> iterable.map(func)"""
	return JSMemberCall(iterable, "map", [func])


def emit_reversed(iterable: JSExpr) -> JSExpr:
	"""reversed(iterable) -> iterable.slice().reverse()"""
	return JSMemberCall(JSMemberCall(iterable, "slice", []), "reverse", [])


def emit_enumerate(iterable: JSExpr, start: JSExpr | None = None) -> JSExpr:
	"""enumerate(iterable, start=0) -> iterable.map((v, i) => [i + start, v])"""
	base = JSNumber(0) if start is None else start
	return JSMemberCall(
		iterable,
		"map",
		[
			JSArrowFunction(
				"(v, i)",
				JSArray([JSBinary(JSIdentifier("i"), "+", base), JSIdentifier("v")]),
			)
		],
	)


def emit_range(*args: JSExpr) -> JSExpr:
	"""range(stop) or range(start, stop[, step]) -> Array.from(...)"""
	if not (1 <= len(args) <= 3):
		raise JSCompilationError("range() expects 1 to 3 arguments")
	if len(args) == 1:
		stop = args[0]
		length = JSMemberCall(JSIdentifier("Math"), "max", [JSNumber(0), stop])
		return JSCall(
			JSMember(JSIdentifier("Array"), "from"),
			[JSMemberCall(JSNew(JSIdentifier("Array"), [length]), "keys", [])],
		)
	start = args[0]
	stop = args[1]
	step = args[2] if len(args) == 3 else JSNumber(1)
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


def emit_sorted(
	*args: JSExpr, key: JSExpr | None = None, reverse: JSExpr | None = None
) -> JSExpr:
	"""sorted(iterable, key=None, reverse=False) -> iterable.slice().sort(...)"""
	if len(args) != 1:
		raise JSCompilationError("sorted() expects exactly one positional argument")
	iterable = args[0]
	clone = JSMemberCall(iterable, "slice", [])
	# comparator: (a, b) => (a > b) - (a < b) or with key
	if key is None:
		cmp_expr = JSBinary(
			JSBinary(JSIdentifier("a"), ">", JSIdentifier("b")),
			"-",
			JSBinary(JSIdentifier("a"), "<", JSIdentifier("b")),
		)
	else:
		cmp_expr = JSBinary(
			JSBinary(
				JSCall(key, [JSIdentifier("a")]),
				">",
				JSCall(key, [JSIdentifier("b")]),
			),
			"-",
			JSBinary(
				JSCall(key, [JSIdentifier("a")]),
				"<",
				JSCall(key, [JSIdentifier("b")]),
			),
		)
	sort_call = JSMemberCall(clone, "sort", [JSArrowFunction("(a, b)", cmp_expr)])
	if reverse is None:
		return sort_call
	return JSTertiary(reverse, JSMemberCall(sort_call, "reverse", []), sort_call)


def emit_zip(*args: JSExpr) -> JSExpr:
	"""zip(*iterables) -> Array.from(...) with paired elements"""
	if len(args) == 0:
		return JSArray([])

	def length_of(x: JSExpr) -> JSExpr:
		return JSMember(x, "length")

	min_len = length_of(args[0])
	for it in args[1:]:
		min_len = JSMemberCall(JSIdentifier("Math"), "min", [min_len, length_of(it)])

	elems = [JSSubscript(arg, JSIdentifier("i")) for arg in args]
	make_pair = JSArrowFunction("i", JSArray(elems))
	return JSCall(
		JSMember(JSIdentifier("Array"), "from"),
		[JSMemberCall(JSNew(JSIdentifier("Array"), [min_len]), "keys", []), make_pair],
	)


def emit_pow(*args: JSExpr) -> JSExpr:
	"""pow(base, exp) -> Math.pow(base, exp)"""
	if len(args) != 2:
		raise JSCompilationError("pow() expects exactly two arguments")
	return JSMemberCall(JSIdentifier("Math"), "pow", [args[0], args[1]])


def emit_chr(x: JSExpr) -> JSExpr:
	"""chr(x) -> String.fromCharCode(x)"""
	return JSMemberCall(JSIdentifier("String"), "fromCharCode", [x])


def emit_ord(x: JSExpr) -> JSExpr:
	"""ord(x) -> x.charCodeAt(0)"""
	return JSMemberCall(x, "charCodeAt", [JSNumber(0)])


def emit_any(x: JSExpr) -> JSExpr:
	"""any(iterable) -> iterable.some(v => v)"""
	# Optimization: if x is a map call, use .some directly
	if isinstance(x, JSMemberCall) and x.method == "map" and x.args:
		return JSMemberCall(x.obj, "some", [x.args[0]])
	return JSMemberCall(x, "some", [JSArrowFunction("v", JSIdentifier("v"))])


def emit_all(x: JSExpr) -> JSExpr:
	"""all(iterable) -> iterable.every(v => v)"""
	# Optimization: if x is a map call, use .every directly
	if isinstance(x, JSMemberCall) and x.method == "map" and x.args:
		return JSMemberCall(x.obj, "every", [x.args[0]])
	return JSMemberCall(x, "every", [JSArrowFunction("v", JSIdentifier("v"))])


def emit_sum(*args: JSExpr) -> JSExpr:
	"""sum(iterable, start=0) -> iterable.reduce((a, b) => a + b, start)"""
	if not (1 <= len(args) <= 2):
		raise JSCompilationError("sum() expects one or two arguments")
	start = args[1] if len(args) == 2 else JSNumber(0)
	base = args[0]
	reducer = JSArrowFunction(
		"(a, b)", JSBinary(JSIdentifier("a"), "+", JSIdentifier("b"))
	)
	return JSMemberCall(base, "reduce", [reducer, start])


def emit_divmod(x: JSExpr, y: JSExpr) -> JSExpr:
	"""divmod(x, y) -> [Math.floor(x / y), x - Math.floor(x / y) * y]"""
	q = JSMemberCall(JSIdentifier("Math"), "floor", [JSBinary(x, "/", y)])
	r = JSBinary(x, "-", JSBinary(q, "*", y))
	return JSArray([q, r])


def emit_isinstance(*args: JSExpr) -> JSExpr:
	"""isinstance is not directly supported in v2; raise error."""
	raise JSCompilationError(
		"isinstance() is not supported in JavaScript transpilation"
	)


# Registry of builtin emitters
BUILTIN_EMITTERS: dict[str, Callable[..., JSExpr]] = {
	"print": emit_print,
	"len": emit_len,
	"min": emit_min,
	"max": emit_max,
	"abs": emit_abs,
	"round": emit_round,
	"str": emit_str,
	"int": emit_int,
	"float": emit_float,
	"list": emit_list,
	"bool": emit_bool,
	"set": emit_set,
	"tuple": emit_tuple,
	"dict": emit_dict,
	"filter": emit_filter,
	"map": emit_map,
	"reversed": emit_reversed,
	"enumerate": emit_enumerate,
	"range": emit_range,
	"sorted": emit_sorted,
	"zip": emit_zip,
	"pow": emit_pow,
	"chr": emit_chr,
	"ord": emit_ord,
	"any": emit_any,
	"all": emit_all,
	"sum": emit_sum,
	"divmod": emit_divmod,
	"isinstance": emit_isinstance,
}


# =============================================================================
# Builtin Method Transpilation
# =============================================================================
#
# Methods are organized into classes by type (StringMethods, ListMethods, etc.).
# Each class contains methods that transpile Python methods to their JS equivalents.
#
# Methods return None to fall through to the default method call (when no
# transformation is needed).


class StringMethods:
	"""String method transpilation."""

	def __init__(self, obj: JSExpr) -> None:
		self.this = obj

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


class ListMethods:
	"""List method transpilation."""

	def __init__(self, obj: JSExpr) -> None:
		self.this = obj

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


class DictMethods:
	"""Dict (Map) method transpilation."""

	def __init__(self, obj: JSExpr) -> None:
		self.this = obj

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


class SetMethods:
	"""Set method transpilation."""

	def __init__(self, obj: JSExpr) -> None:
		self.this = obj

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

# Map method names to their handler classes
# Note: Some methods exist in multiple classes (e.g., copy, clear)
# We apply all that might match since we don't have runtime type info
METHOD_CLASSES: list[
	type[StringMethods] | type[ListMethods] | type[DictMethods] | type[SetMethods]
] = [
	StringMethods,
	ListMethods,
	DictMethods,
	SetMethods,
]


def emit_method(obj: JSExpr, method: str, args: list[JSExpr]) -> JSExpr | None:
	"""Emit a method call, handling Python builtin methods.

	Tries each method class that has the method name. Returns the first
	non-None result, or None if all return None (fall through to default).

	Returns:
		JSExpr if the method should be transpiled specially
		None if the method should be emitted as a regular method call
	"""
	if method not in ALL_METHODS:
		return None

	for cls in METHOD_CLASSES:
		if method not in {k for k in cls.__dict__ if not k.startswith("_")}:
			continue

		handler = cls(obj)
		method_fn = getattr(handler, method, None)
		if method_fn is None:
			continue

		# Call with args
		result = method_fn(*args)
		if result is not None:
			return result

	return None
