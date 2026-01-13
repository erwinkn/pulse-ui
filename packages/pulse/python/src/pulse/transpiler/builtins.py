"""Python builtin functions and methods -> JavaScript equivalents.

This module provides transpilation for Python builtins to JavaScript.
Builtin methods use runtime type checks when the type is not statically known.
"""

from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, override

from pulse.transpiler.errors import TranspileError
from pulse.transpiler.nodes import (
	Array,
	Arrow,
	Binary,
	Call,
	Expr,
	Identifier,
	Literal,
	Member,
	New,
	Spread,
	Subscript,
	Template,
	Ternary,
	Throw,
	Transformer,
	Unary,
	Undefined,
	transformer,
)

if TYPE_CHECKING:
	from pulse.transpiler.transpiler import Transpiler


# =============================================================================
# Builtin Function Transpilers
# =============================================================================


@transformer("print")
def emit_print(*args: Any, ctx: Transpiler) -> Expr:
	"""print(*args) -> console.log(...)"""
	return Call(Member(Identifier("console"), "log"), [ctx.emit_expr(a) for a in args])


@transformer("len")
def emit_len(x: Any, *, ctx: Transpiler) -> Expr:
	"""len(x) -> x.length ?? x.size"""
	x = ctx.emit_expr(x)
	return Binary(Member(x, "length"), "??", Member(x, "size"))


@transformer("min")
def emit_min(*args: Any, ctx: Transpiler) -> Expr:
	"""min(*args) -> Math.min(...)"""
	if builtins.len(args) == 0:
		raise TranspileError("min() expects at least one argument")
	if builtins.len(args) == 1:
		iterable = ctx.emit_expr(args[0])
		return Call(
			Member(Identifier("Math"), "min"),
			[Spread(Call(Member(Identifier("Array"), "from"), [iterable]))],
		)
	return Call(Member(Identifier("Math"), "min"), [ctx.emit_expr(a) for a in args])


@transformer("max")
def emit_max(*args: Any, ctx: Transpiler) -> Expr:
	"""max(*args) -> Math.max(...)"""
	if builtins.len(args) == 0:
		raise TranspileError("max() expects at least one argument")
	if builtins.len(args) == 1:
		iterable = ctx.emit_expr(args[0])
		return Call(
			Member(Identifier("Math"), "max"),
			[Spread(Call(Member(Identifier("Array"), "from"), [iterable]))],
		)
	return Call(Member(Identifier("Math"), "max"), [ctx.emit_expr(a) for a in args])


@transformer("abs")
def emit_abs(x: Any, *, ctx: Transpiler) -> Expr:
	"""abs(x) -> Math.abs(x)"""
	return Call(Member(Identifier("Math"), "abs"), [ctx.emit_expr(x)])


@transformer("round")
def emit_round(number: Any, ndigits: Any = None, *, ctx: Transpiler) -> Expr:
	"""round(number, ndigits=None) -> Math.round(...) or toFixed(...)"""
	number = ctx.emit_expr(number)
	if ndigits is None:
		return Call(Member(Identifier("Math"), "round"), [number])
	# With ndigits: Number(Number(x).toFixed(ndigits)) to keep numeric semantics
	return Call(
		Identifier("Number"),
		[
			Call(
				Member(Call(Identifier("Number"), [number]), "toFixed"),
				[ctx.emit_expr(ndigits)],
			)
		],
	)


@transformer("str")
def emit_str(x: Any, *, ctx: Transpiler) -> Expr:
	"""str(x) -> String(x)"""
	return Call(Identifier("String"), [ctx.emit_expr(x)])


@transformer("int")
def emit_int(*args: Any, ctx: Transpiler) -> Expr:
	"""int(x) or int(x, base) -> parseInt(...)"""
	if builtins.len(args) == 1:
		return Call(Identifier("parseInt"), [ctx.emit_expr(args[0])])
	if builtins.len(args) == 2:
		return Call(
			Identifier("parseInt"), [ctx.emit_expr(args[0]), ctx.emit_expr(args[1])]
		)
	raise TranspileError("int() expects one or two arguments")


@transformer("float")
def emit_float(x: Any, *, ctx: Transpiler) -> Expr:
	"""float(x) -> parseFloat(x)"""
	return Call(Identifier("parseFloat"), [ctx.emit_expr(x)])


@transformer("list")
def emit_list(x: Any, *, ctx: Transpiler) -> Expr:
	"""list(x) -> Array.from(x)"""
	return Call(Member(Identifier("Array"), "from"), [ctx.emit_expr(x)])


@transformer("bool")
def emit_bool(x: Any, *, ctx: Transpiler) -> Expr:
	"""bool(x) -> Boolean(x)"""
	return Call(Identifier("Boolean"), [ctx.emit_expr(x)])


@transformer("set")
def emit_set(*args: Any, ctx: Transpiler) -> Expr:
	"""set() or set(iterable) -> new Set([iterable])"""
	if builtins.len(args) == 0:
		return New(Identifier("Set"), [])
	if builtins.len(args) == 1:
		return New(Identifier("Set"), [ctx.emit_expr(args[0])])
	raise TranspileError("set() expects at most one argument")


@transformer("tuple")
def emit_tuple(*args: Any, ctx: Transpiler) -> Expr:
	"""tuple() or tuple(iterable) -> Array.from(iterable)"""
	if builtins.len(args) == 0:
		return Array([])
	if builtins.len(args) == 1:
		return Call(Member(Identifier("Array"), "from"), [ctx.emit_expr(args[0])])
	raise TranspileError("tuple() expects at most one argument")


@transformer("dict")
def emit_dict(*args: Any, ctx: Transpiler) -> Expr:
	"""dict() or dict(iterable) -> new Map([iterable])"""
	if builtins.len(args) == 0:
		return New(Identifier("Map"), [])
	if builtins.len(args) == 1:
		return New(Identifier("Map"), [ctx.emit_expr(args[0])])
	raise TranspileError("dict() expects at most one argument")


@transformer("filter")
def emit_filter(*args: Any, ctx: Transpiler) -> Expr:
	"""filter(func, iterable) -> iterable.filter(func)"""
	if not (1 <= builtins.len(args) <= 2):
		raise TranspileError("filter() expects one or two arguments")
	if builtins.len(args) == 1:
		# filter(iterable) - filter truthy values
		iterable = ctx.emit_expr(args[0])
		predicate = Arrow(["v"], Identifier("v"))
		return Call(Member(iterable, "filter"), [predicate])
	func, iterable = ctx.emit_expr(args[0]), ctx.emit_expr(args[1])
	# filter(None, iterable) means filter truthy
	if builtins.isinstance(func, (Literal, Undefined)) and (
		builtins.isinstance(func, Undefined)
		or (builtins.isinstance(func, Literal) and func.value is None)
	):
		func = Arrow(["v"], Identifier("v"))
	return Call(Member(iterable, "filter"), [func])


@transformer("map")
def emit_map(func: Any, iterable: Any, *, ctx: Transpiler) -> Expr:
	"""map(func, iterable) -> iterable.map(func)"""
	return Call(Member(ctx.emit_expr(iterable), "map"), [ctx.emit_expr(func)])


@transformer("reversed")
def emit_reversed(iterable: Any, *, ctx: Transpiler) -> Expr:
	"""reversed(iterable) -> iterable.slice().reverse()"""
	return Call(
		Member(Call(Member(ctx.emit_expr(iterable), "slice"), []), "reverse"), []
	)


@transformer("enumerate")
def emit_enumerate(iterable: Any, start: Any = None, *, ctx: Transpiler) -> Expr:
	"""enumerate(iterable, start=0) -> iterable.map((v, i) => [i + start, v])"""
	base = Literal(0) if start is None else ctx.emit_expr(start)
	return Call(
		Member(ctx.emit_expr(iterable), "map"),
		[
			Arrow(
				["v", "i"],
				Array([Binary(Identifier("i"), "+", base), Identifier("v")]),
			)
		],
	)


@transformer("range")
def emit_range(*args: Any, ctx: Transpiler) -> Expr:
	"""range(stop) or range(start, stop[, step]) -> Array.from(...)"""
	if not (1 <= builtins.len(args) <= 3):
		raise TranspileError("range() expects 1 to 3 arguments")
	if builtins.len(args) == 1:
		stop = ctx.emit_expr(args[0])
		length = Call(Member(Identifier("Math"), "max"), [Literal(0), stop])
		return Call(
			Member(Identifier("Array"), "from"),
			[Call(Member(New(Identifier("Array"), [length]), "keys"), [])],
		)
	start = ctx.emit_expr(args[0])
	stop = ctx.emit_expr(args[1])
	step = ctx.emit_expr(args[2]) if builtins.len(args) == 3 else Literal(1)
	# count = max(0, ceil((stop - start) / step))
	diff = Binary(stop, "-", start)
	div = Binary(diff, "/", step)
	ceil = Call(Member(Identifier("Math"), "ceil"), [div])
	count = Call(Member(Identifier("Math"), "max"), [Literal(0), ceil])
	# Array.from(new Array(count).keys(), i => start + i * step)
	return Call(
		Member(Identifier("Array"), "from"),
		[
			Call(Member(New(Identifier("Array"), [count]), "keys"), []),
			Arrow(["i"], Binary(start, "+", Binary(Identifier("i"), "*", step))),
		],
	)


@transformer("sorted")
def emit_sorted(
	*args: Any, key: Any = None, reverse: Any = None, ctx: Transpiler
) -> Expr:
	"""sorted(iterable, key=None, reverse=False) -> iterable.slice().sort(...)"""
	if builtins.len(args) != 1:
		raise TranspileError("sorted() expects exactly one positional argument")
	iterable = ctx.emit_expr(args[0])
	clone = Call(Member(iterable, "slice"), [])
	# comparator: (a, b) => (a > b) - (a < b) or with key
	if key is None:
		cmp_expr = Binary(
			Binary(Identifier("a"), ">", Identifier("b")),
			"-",
			Binary(Identifier("a"), "<", Identifier("b")),
		)
	else:
		key_js = ctx.emit_expr(key)
		cmp_expr = Binary(
			Binary(
				Call(key_js, [Identifier("a")]),
				">",
				Call(key_js, [Identifier("b")]),
			),
			"-",
			Binary(
				Call(key_js, [Identifier("a")]),
				"<",
				Call(key_js, [Identifier("b")]),
			),
		)
	sort_call = Call(Member(clone, "sort"), [Arrow(["a", "b"], cmp_expr)])
	if reverse is None:
		return sort_call
	return Ternary(
		ctx.emit_expr(reverse), Call(Member(sort_call, "reverse"), []), sort_call
	)


@transformer("zip")
def emit_zip(*args: Any, ctx: Transpiler) -> Expr:
	"""zip(*iterables) -> Array.from(...) with paired elements"""
	if builtins.len(args) == 0:
		return Array([])

	js_args = [ctx.emit_expr(a) for a in args]

	def length_of(x: Expr) -> Expr:
		return Member(x, "length")

	min_len = length_of(js_args[0])
	for it in js_args[1:]:
		min_len = Call(Member(Identifier("Math"), "min"), [min_len, length_of(it)])

	elems = [Subscript(arg, Identifier("i")) for arg in js_args]
	make_pair = Arrow(["i"], Array(elems))
	return Call(
		Member(Identifier("Array"), "from"),
		[Call(Member(New(Identifier("Array"), [min_len]), "keys"), []), make_pair],
	)


@transformer("pow")
def emit_pow(base: Any, exp: Any, *, ctx: Transpiler) -> Expr:
	"""pow(base, exp) -> Math.pow(base, exp)"""
	return Call(
		Member(Identifier("Math"), "pow"), [ctx.emit_expr(base), ctx.emit_expr(exp)]
	)


@transformer("chr")
def emit_chr(x: Any, *, ctx: Transpiler) -> Expr:
	"""chr(x) -> String.fromCharCode(x)"""
	return Call(Member(Identifier("String"), "fromCharCode"), [ctx.emit_expr(x)])


@transformer("ord")
def emit_ord(x: Any, *, ctx: Transpiler) -> Expr:
	"""ord(x) -> x.charCodeAt(0)"""
	return Call(Member(ctx.emit_expr(x), "charCodeAt"), [Literal(0)])


@transformer("any")
def emit_any(x: Any, *, ctx: Transpiler) -> Expr:
	"""any(iterable) -> iterable.some(v => v)"""
	x = ctx.emit_expr(x)
	# Optimization: if x is a map call, use .some directly
	if (
		builtins.isinstance(x, Call)
		and builtins.isinstance(x.callee, Member)
		and x.callee.prop == "map"
		and x.args
	):
		return Call(Member(x.callee.obj, "some"), [x.args[0]])
	return Call(Member(x, "some"), [Arrow(["v"], Identifier("v"))])


@transformer("all")
def emit_all(x: Any, *, ctx: Transpiler) -> Expr:
	"""all(iterable) -> iterable.every(v => v)"""
	x = ctx.emit_expr(x)
	# Optimization: if x is a map call, use .every directly
	if (
		builtins.isinstance(x, Call)
		and builtins.isinstance(x.callee, Member)
		and x.callee.prop == "map"
		and x.args
	):
		return Call(Member(x.callee.obj, "every"), [x.args[0]])
	return Call(Member(x, "every"), [Arrow(["v"], Identifier("v"))])


@transformer("sum")
def emit_sum(*args: Any, ctx: Transpiler) -> Expr:
	"""sum(iterable, start=0) -> iterable.reduce((a, b) => a + b, start)"""
	if not (1 <= builtins.len(args) <= 2):
		raise TranspileError("sum() expects one or two arguments")
	start = ctx.emit_expr(args[1]) if builtins.len(args) == 2 else Literal(0)
	base = ctx.emit_expr(args[0])
	reducer = Arrow(["a", "b"], Binary(Identifier("a"), "+", Identifier("b")))
	return Call(Member(base, "reduce"), [reducer, start])


@transformer("divmod")
def emit_divmod(x: Any, y: Any, *, ctx: Transpiler) -> Expr:
	"""divmod(x, y) -> [Math.floor(x / y), x - Math.floor(x / y) * y]"""
	x, y = ctx.emit_expr(x), ctx.emit_expr(y)
	q = Call(Member(Identifier("Math"), "floor"), [Binary(x, "/", y)])
	r = Binary(x, "-", Binary(q, "*", y))
	return Array([q, r])


@transformer("isinstance")
def emit_isinstance(*args: Any, ctx: Transpiler) -> Expr:
	"""isinstance is not directly supported in v2; raise error."""
	raise TranspileError("isinstance() is not supported in JavaScript transpilation")


@transformer("Exception")
def emit_exception(*args: Any, ctx: Transpiler) -> Expr:
	"""Exception(msg) -> new Error(msg)"""
	return New(Identifier("Error"), [ctx.emit_expr(a) for a in args])


@transformer("ValueError")
def emit_value_error(*args: Any, ctx: Transpiler) -> Expr:
	"""ValueError(msg) -> new Error(msg)"""
	return New(Identifier("Error"), [ctx.emit_expr(a) for a in args])


@transformer("TypeError")
def emit_type_error(*args: Any, ctx: Transpiler) -> Expr:
	"""TypeError(msg) -> new TypeError(msg)"""
	return New(Identifier("TypeError"), [ctx.emit_expr(a) for a in args])


@transformer("RuntimeError")
def emit_runtime_error(*args: Any, ctx: Transpiler) -> Expr:
	"""RuntimeError(msg) -> new Error(msg)"""
	return New(Identifier("Error"), [ctx.emit_expr(a) for a in args])


# Registry of builtin transformers
# Note: @transformer decorator returns Transformer but lies about the type
# for ergonomic reasons. These are all Transformer instances at runtime.
BUILTINS: dict[str, Transformer[Any]] = dict(
	print=emit_print,
	len=emit_len,
	min=emit_min,
	max=emit_max,
	abs=emit_abs,
	round=emit_round,
	str=emit_str,
	int=emit_int,
	float=emit_float,
	list=emit_list,
	bool=emit_bool,
	set=emit_set,
	tuple=emit_tuple,
	dict=emit_dict,
	filter=emit_filter,
	map=emit_map,
	reversed=emit_reversed,
	enumerate=emit_enumerate,
	range=emit_range,
	sorted=emit_sorted,
	zip=emit_zip,
	pow=emit_pow,
	chr=emit_chr,
	ord=emit_ord,
	any=emit_any,
	all=emit_all,
	sum=emit_sum,
	divmod=emit_divmod,
	isinstance=emit_isinstance,
	# Exception types
	Exception=emit_exception,
	ValueError=emit_value_error,
	TypeError=emit_type_error,
	RuntimeError=emit_runtime_error,
)  # pyright: ignore[reportAssignmentType]


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

	def __init__(self, obj: Expr) -> None:
		self.this: Expr = obj

	@classmethod
	@abstractmethod
	def __runtime_check__(cls, expr: Expr) -> Expr:
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
	def __runtime_check__(cls, expr: Expr) -> Expr:
		return Binary(Unary("typeof", expr), "===", Literal("string"))

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return STR_METHODS

	def lower(self) -> Expr:
		"""str.lower() -> str.toLowerCase()"""
		return Call(Member(self.this, "toLowerCase"), [])

	def upper(self) -> Expr:
		"""str.upper() -> str.toUpperCase()"""
		return Call(Member(self.this, "toUpperCase"), [])

	def strip(self) -> Expr:
		"""str.strip() -> str.trim()"""
		return Call(Member(self.this, "trim"), [])

	def lstrip(self) -> Expr:
		"""str.lstrip() -> str.trimStart()"""
		return Call(Member(self.this, "trimStart"), [])

	def rstrip(self) -> Expr:
		"""str.rstrip() -> str.trimEnd()"""
		return Call(Member(self.this, "trimEnd"), [])

	def zfill(self, width: Expr) -> Expr:
		"""str.zfill(width) -> str.padStart(width, '0')"""
		return Call(Member(self.this, "padStart"), [width, Literal("0")])

	def startswith(self, prefix: Expr) -> Expr:
		"""str.startswith(prefix) -> str.startsWith(prefix)"""
		return Call(Member(self.this, "startsWith"), [prefix])

	def endswith(self, suffix: Expr) -> Expr:
		"""str.endswith(suffix) -> str.endsWith(suffix)"""
		return Call(Member(self.this, "endsWith"), [suffix])

	def replace(self, old: Expr, new: Expr) -> Expr:
		"""str.replace(old, new) -> str.replaceAll(old, new)"""
		return Call(Member(self.this, "replaceAll"), [old, new])

	def capitalize(self) -> Expr:
		"""str.capitalize() -> str.charAt(0).toUpperCase() + str.slice(1).toLowerCase()"""
		left = Call(
			Member(Call(Member(self.this, "charAt"), [Literal(0)]), "toUpperCase"), []
		)
		right = Call(
			Member(Call(Member(self.this, "slice"), [Literal(1)]), "toLowerCase"), []
		)
		return Binary(left, "+", right)

	def split(self, sep: Expr | None = None) -> Expr | None:
		"""str.split(sep) -> str.split(sep) or special whitespace handling.

		Python's split() without args splits on whitespace and removes empties:
		"a  b".split() -> ["a", "b"]

		JavaScript's split() without args returns the whole string:
		"a  b".split() -> ["a  b"]

		Fix: str.trim().split(/\\s+/)
		"""
		if sep is None:
			# Python's default: split on whitespace and filter empties
			trimmed = Call(Member(self.this, "trim"), [])
			return Call(Member(trimmed, "split"), [Identifier(r"/\s+/")])
		return None  # Fall through for explicit separator

	def join(self, iterable: Expr) -> Expr:
		"""str.join(iterable) -> iterable.join(str)"""
		return Call(Member(iterable, "join"), [self.this])

	def find(self, sub: Expr) -> Expr:
		"""str.find(sub) -> str.indexOf(sub)"""
		return Call(Member(self.this, "indexOf"), [sub])

	def rfind(self, sub: Expr) -> Expr:
		"""str.rfind(sub) -> str.lastIndexOf(sub)"""
		return Call(Member(self.this, "lastIndexOf"), [sub])

	def count(self, sub: Expr) -> Expr:
		"""str.count(sub) -> (str.split(sub).length - 1)"""
		return Binary(
			Member(Call(Member(self.this, "split"), [sub]), "length"),
			"-",
			Literal(1),
		)

	def isdigit(self) -> Expr:
		r"""str.isdigit() -> /^\d+$/.test(str)"""
		return Call(
			Member(Identifier("/^\\d+$/"), "test"),
			[self.this],
		)

	def isalpha(self) -> Expr:
		r"""str.isalpha() -> /^[a-zA-Z]+$/.test(str)"""
		return Call(
			Member(Identifier("/^[a-zA-Z]+$/"), "test"),
			[self.this],
		)

	def isalnum(self) -> Expr:
		r"""str.isalnum() -> /^[a-zA-Z0-9]+$/.test(str)"""
		return Call(
			Member(Identifier("/^[a-zA-Z0-9]+$/"), "test"),
			[self.this],
		)


STR_METHODS = {k for k in StringMethods.__dict__ if not k.startswith("_")}


class ListMethods(BuiltinMethods):
	"""List method transpilation."""

	@classmethod
	@override
	def __runtime_check__(cls, expr: Expr) -> Expr:
		return Call(Member(Identifier("Array"), "isArray"), [expr])

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return LIST_METHODS

	def append(self, value: Expr) -> Expr:
		"""list.append(value) -> (list.push(value), undefined)[1]"""
		# Returns undefined to match Python's None return
		return Subscript(
			Array([Call(Member(self.this, "push"), [value]), Undefined()]),
			Literal(1),
		)

	def extend(self, iterable: Expr) -> Expr:
		"""list.extend(iterable) -> (list.push(...iterable), undefined)[1]"""
		return Subscript(
			Array([Call(Member(self.this, "push"), [Spread(iterable)]), Undefined()]),
			Literal(1),
		)

	def pop(self, index: Expr | None = None) -> Expr | None:
		"""list.pop() or list.pop(index)"""
		if index is None:
			return None  # Fall through to default .pop()
		return Subscript(
			Call(Member(self.this, "splice"), [index, Literal(1)]), Literal(0)
		)

	def copy(self) -> Expr:
		"""list.copy() -> list.slice()"""
		return Call(Member(self.this, "slice"), [])

	def count(self, value: Expr) -> Expr:
		"""list.count(value) -> list.filter(v => v === value).length"""
		return Member(
			Call(
				Member(self.this, "filter"),
				[Arrow(["v"], Binary(Identifier("v"), "===", value))],
			),
			"length",
		)

	def index(self, value: Expr) -> Expr:
		"""list.index(value) -> list.indexOf(value)"""
		return Call(Member(self.this, "indexOf"), [value])

	def reverse(self) -> Expr:
		"""list.reverse() -> (list.reverse(), undefined)[1]"""
		return Subscript(
			Array([Call(Member(self.this, "reverse"), []), Undefined()]),
			Literal(1),
		)

	def sort(self) -> Expr:
		"""list.sort() -> (list.sort(), undefined)[1]"""
		return Subscript(
			Array([Call(Member(self.this, "sort"), []), Undefined()]),
			Literal(1),
		)

	def clear(self) -> Expr:
		"""list.clear() -> (list.length = 0, undefined)[1]"""
		# Setting length to 0 clears the array
		return Subscript(
			Array([Binary(Member(self.this, "length"), "=", Literal(0)), Undefined()]),
			Literal(1),
		)

	def insert(self, index: Expr, value: Expr) -> Expr:
		"""list.insert(index, value) -> (list.splice(index, 0, value), undefined)[1]"""
		return Subscript(
			Array(
				[
					Call(Member(self.this, "splice"), [index, Literal(0), value]),
					Undefined(),
				]
			),
			Literal(1),
		)

	def remove(self, value: Expr) -> Expr:
		"""list.remove(value) -> safe removal with error on not found.

		Python raises ValueError if value not in list. We generate:
		(($i) => $i < 0 ? (() => { throw new Error(...) })() : list.splice($i, 1))(list.indexOf(value))
		"""
		idx = Identifier("$i")
		index_call = Call(Member(self.this, "indexOf"), [value])
		# IIFE that throws using Arrow with statement body
		throw_iife = Call(
			Arrow(
				[],
				[
					Throw(
						New(
							Identifier("Error"),
							[Literal("list.remove(x): x not in list")],
						)
					)
				],
			),
			[],
		)
		safe_splice = Ternary(
			Binary(idx, "<", Literal(0)),
			throw_iife,
			Call(Member(self.this, "splice"), [idx, Literal(1)]),
		)
		return Call(Arrow(["$i"], safe_splice), [index_call])


LIST_METHODS = {k for k in ListMethods.__dict__ if not k.startswith("_")}


class DictMethods(BuiltinMethods):
	"""Dict (Map) method transpilation."""

	@classmethod
	@override
	def __runtime_check__(cls, expr: Expr) -> Expr:
		return Binary(expr, "instanceof", Identifier("Map"))

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return DICT_METHODS

	def get(self, key: Expr, default: Expr | None = None) -> Expr | None:
		"""dict.get(key, default) -> dict.get(key) ?? default"""
		if default is None:
			return None  # Fall through to default .get()
		return Binary(Call(Member(self.this, "get"), [key]), "??", default)

	def keys(self) -> Expr:
		"""dict.keys() -> [...dict.keys()]"""
		return Array([Spread(Call(Member(self.this, "keys"), []))])

	def values(self) -> Expr:
		"""dict.values() -> [...dict.values()]"""
		return Array([Spread(Call(Member(self.this, "values"), []))])

	def items(self) -> Expr:
		"""dict.items() -> [...dict.entries()]"""
		return Array([Spread(Call(Member(self.this, "entries"), []))])

	def copy(self) -> Expr:
		"""dict.copy() -> new Map(dict.entries())"""
		return New(Identifier("Map"), [Call(Member(self.this, "entries"), [])])

	def clear(self) -> Expr | None:
		"""dict.clear() doesn't need transformation."""
		return None

	def pop(self, key: Expr, default: Expr | None = None) -> Expr:
		"""dict.pop(key, default) -> complex expression to get and delete"""
		# (v => (dict.delete(key), v))(dict.get(key) ?? default)
		get_val = Call(Member(self.this, "get"), [key])
		if default is not None:
			get_val = Binary(get_val, "??", default)
		delete_call = Call(Member(self.this, "delete"), [key])
		return Call(
			Arrow(
				["$v"], Subscript(Array([delete_call, Identifier("$v")]), Literal(1))
			),
			[get_val],
		)

	def update(self, other: Expr) -> Expr:
		"""dict.update(other) -> other.forEach((v, k) => dict.set(k, v))"""
		return Call(
			Member(other, "forEach"),
			[
				Arrow(
					["$v", "$k"],
					Call(
						Member(self.this, "set"), [Identifier("$k"), Identifier("$v")]
					),
				)
			],
		)

	def setdefault(self, key: Expr, default: Expr | None = None) -> Expr:
		"""dict.setdefault(key, default) -> dict.has(key) ? dict.get(key) : (dict.set(key, default), default)[1]"""
		default_val = default if default is not None else Literal(None)
		return Ternary(
			Call(Member(self.this, "has"), [key]),
			Call(Member(self.this, "get"), [key]),
			Subscript(
				Array(
					[Call(Member(self.this, "set"), [key, default_val]), default_val]
				),
				Literal(1),
			),
		)


DICT_METHODS = {k for k in DictMethods.__dict__ if not k.startswith("_")}


class SetMethods(BuiltinMethods):
	"""Set method transpilation."""

	@classmethod
	@override
	def __runtime_check__(cls, expr: Expr) -> Expr:
		return Binary(expr, "instanceof", Identifier("Set"))

	@classmethod
	@override
	def __methods__(cls) -> set[str]:
		return SET_METHODS

	def add(self, value: Expr) -> Expr | None:
		"""set.add() doesn't need transformation."""
		return None

	def remove(self, value: Expr) -> Expr:
		"""set.remove(value) -> set.delete(value)"""
		return Call(Member(self.this, "delete"), [value])

	def discard(self, value: Expr) -> Expr:
		"""set.discard(value) -> set.delete(value)"""
		return Call(Member(self.this, "delete"), [value])

	def clear(self) -> Expr | None:
		"""set.clear() doesn't need transformation."""
		return None

	def copy(self) -> Expr:
		"""set.copy() -> new Set(set)"""
		return New(Identifier("Set"), [self.this])

	def pop(self) -> Expr:
		"""set.pop() -> (v => (set.delete(v), v))(set.values().next().value)"""
		get_first = Member(
			Call(Member(Call(Member(self.this, "values"), []), "next"), []), "value"
		)
		delete_call = Call(Member(self.this, "delete"), [Identifier("$v")])
		return Call(
			Arrow(
				["$v"], Subscript(Array([delete_call, Identifier("$v")]), Literal(1))
			),
			[get_first],
		)

	def update(self, other: Expr) -> Expr:
		"""set.update(other) -> other.forEach(v => set.add(v))"""
		return Call(
			Member(other, "forEach"),
			[Arrow(["$v"], Call(Member(self.this, "add"), [Identifier("$v")]))],
		)

	def intersection(self, other: Expr) -> Expr:
		"""set.intersection(other) -> new Set([...set].filter(x => other.has(x)))"""
		filtered = Call(
			Member(Array([Spread(self.this)]), "filter"),
			[Arrow(["$x"], Call(Member(other, "has"), [Identifier("$x")]))],
		)
		return New(Identifier("Set"), [filtered])

	def union(self, other: Expr) -> Expr:
		"""set.union(other) -> new Set([...set, ...other])"""
		return New(
			Identifier("Set"),
			[Array([Spread(self.this), Spread(other)])],
		)

	def difference(self, other: Expr) -> Expr:
		"""set.difference(other) -> new Set([...set].filter(x => !other.has(x)))"""
		filtered = Call(
			Member(Array([Spread(self.this)]), "filter"),
			[
				Arrow(
					["$x"],
					Unary("!", Call(Member(other, "has"), [Identifier("$x")])),
				)
			],
		)
		return New(Identifier("Set"), [filtered])

	def issubset(self, other: Expr) -> Expr:
		"""set.issubset(other) -> [...set].every(x => other.has(x))"""
		return Call(
			Member(Array([Spread(self.this)]), "every"),
			[Arrow(["$x"], Call(Member(other, "has"), [Identifier("$x")]))],
		)

	def issuperset(self, other: Expr) -> Expr:
		"""set.issuperset(other) -> [...other].every(x => set.has(x))"""
		return Call(
			Member(Array([Spread(other)]), "every"),
			[Arrow(["$x"], Call(Member(self.this, "has"), [Identifier("$x")]))],
		)


SET_METHODS = {k for k in SetMethods.__dict__ if not k.startswith("_")}


# Collect all known method names for quick lookup
ALL_METHODS = STR_METHODS | LIST_METHODS | DICT_METHODS | SET_METHODS

# Method classes in priority order (higher priority = later in list = outermost ternary)
# We prefer string/list semantics first, then set, then dict.
METHOD_CLASSES: builtins.list[builtins.type[BuiltinMethods]] = [
	DictMethods,
	SetMethods,
	ListMethods,
	StringMethods,
]


def _try_dispatch_method(
	cls: builtins.type[BuiltinMethods],
	obj: Expr,
	method: str,
	args: list[Expr],
	kwargs: builtins.dict[builtins.str, Expr] | None = None,
) -> Expr | None:
	"""Try to dispatch a method call to a specific builtin class.

	Returns the transformed expression, or None if the method returns None
	(fall through to default) or if dispatch fails.
	"""
	if method not in cls.__methods__():
		return None

	try:
		handler = cls(obj)
		method_fn = builtins.getattr(handler, method, None)
		if method_fn is None:
			return None
		if kwargs:
			return method_fn(*args, **kwargs)
		return method_fn(*args)
	except TypeError:
		return None


def emit_method(
	obj: Expr,
	method: str,
	args: list[Expr],
	kwargs: builtins.dict[builtins.str, Expr] | None = None,
) -> Expr | None:
	"""Emit a method call, handling Python builtin methods.

	For known literal types (Literal str, Template, Array, New Set/Map),
	dispatches directly without runtime checks.

	For unknown types, builds a ternary chain that checks types at runtime
	and dispatches to the appropriate method implementation.

	Returns:
		Expr if the method should be transpiled specially
		None if the method should be emitted as a regular method call
	"""
	if method not in ALL_METHODS:
		return None

	# Fast path: known literal types - dispatch directly without runtime checks
	if builtins.isinstance(obj, Literal) and builtins.isinstance(obj.value, str):
		if method in StringMethods.__methods__():
			result = _try_dispatch_method(StringMethods, obj, method, args, kwargs)
			if result is not None:
				return result
		return None

	if builtins.isinstance(obj, Template):
		if method in StringMethods.__methods__():
			result = _try_dispatch_method(StringMethods, obj, method, args, kwargs)
			if result is not None:
				return result
		return None

	if builtins.isinstance(obj, Array):
		if method in ListMethods.__methods__():
			result = _try_dispatch_method(ListMethods, obj, method, args, kwargs)
			if result is not None:
				return result
		return None

	# Fast path: new Set(...) and new Map(...) are known types
	if builtins.isinstance(obj, New) and builtins.isinstance(obj.ctor, Identifier):
		if obj.ctor.name == "Set" and method in SetMethods.__methods__():
			result = _try_dispatch_method(SetMethods, obj, method, args, kwargs)
			if result is not None:
				return result
			return None
		if obj.ctor.name == "Map" and method in DictMethods.__methods__():
			result = _try_dispatch_method(DictMethods, obj, method, args, kwargs)
			if result is not None:
				return result
			return None

	# Slow path: unknown type - build ternary chain with runtime type checks
	# Start with the default fallback (regular method call)
	default_expr = Call(Member(obj, method), args)
	expr: Expr = default_expr

	# Apply in increasing priority so that later (higher priority) wrappers
	# end up outermost in the final expression.
	for cls in METHOD_CLASSES:
		if method not in cls.__methods__():
			continue

		dispatch_expr = _try_dispatch_method(cls, obj, method, args, kwargs)
		if dispatch_expr is not None:
			expr = Ternary(cls.__runtime_check__(obj), dispatch_expr, expr)

	# If we built ternaries, return them; otherwise return None to fall through
	if expr is not default_expr:
		return expr

	return None
