from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, ClassVar, TypeVar, cast, overload, override

from pulse.transpiler.context import is_interpreted_mode
from pulse.transpiler.errors import JSCompilationError

# Global registry: id(value) -> JSExpr
# Used by JSExpr.of() to resolve registered Python values
JSEXPR_REGISTRY: dict[int, JSExpr] = {}

ALLOWED_BINOPS: dict[type[ast.operator], str] = {
	ast.Add: "+",
	ast.Sub: "-",
	ast.Mult: "*",
	ast.Div: "/",
	ast.Mod: "%",
	ast.Pow: "**",
}

ALLOWED_UNOPS: dict[type[ast.unaryop], str] = {
	ast.UAdd: "+",
	ast.USub: "-",
	ast.Not: "!",
}

ALLOWED_CMPOPS: dict[type[ast.cmpop], str] = {
	ast.Eq: "===",
	ast.NotEq: "!==",
	ast.Lt: "<",
	ast.LtE: "<=",
	ast.Gt: ">",
	ast.GtE: ">=",
}


###############################################################################
# JS AST
###############################################################################


class JSNode(ABC):
	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]

	@abstractmethod
	def emit(self) -> str:
		raise NotImplementedError


class JSExpr(JSNode, ABC):
	"""Base class for JavaScript expressions.

	Subclasses can override emit_call, emit_subscript, and emit_getattr to
	customize how the expression behaves when called, indexed, or accessed.
	This enables extensibility for things like JSX elements.
	"""

	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]

	# Set to True for expressions that emit JSX (should not be wrapped in {})
	is_jsx: ClassVar[bool] = False

	# Set to True for expressions that have primary precedence (identifiers, literals, etc.)
	# Used by expr_precedence to determine if parenthesization is needed
	is_primary: ClassVar[bool] = False

	@classmethod
	def of(cls, value: Any) -> JSExpr:
		"""Convert a Python value to a JSExpr.

		Resolution order:
		1. Already a JSExpr: returned as-is
		2. Registered in JSEXPR_REGISTRY: return the registered expr
		3. Primitives: str->JSString, int/float->JSNumber, bool->JSBoolean, None->JSNull
		4. Collections: list/tuple->JSArray, dict->JSObjectExpr (recursively converted)
		"""
		# Already a JSExpr
		if isinstance(value, JSExpr):
			return value

		# Check registry (for modules, functions, etc.)
		if (expr := JSEXPR_REGISTRY.get(id(value))) is not None:
			return expr

		# Primitives
		if isinstance(value, str):
			return JSString(value)
		if isinstance(
			value, bool
		):  # Must check before int since bool is subclass of int
			return JSBoolean(value)
		if isinstance(value, (int, float)):
			return JSNumber(value)
		if value is None:
			return JSNull()

		# Collections
		if isinstance(value, (list, tuple)):
			return JSArray([cls.of(v) for v in value])
		if isinstance(value, dict):
			props = [JSProp(JSString(str(k)), cls.of(v)) for k, v in value.items()]  # pyright: ignore[reportUnknownArgumentType]
			return JSObjectExpr(props)

		raise TypeError(f"Cannot convert {type(value).__name__} to JSExpr")

	@classmethod
	def register(cls, value: Any, expr: JSExpr | Callable[..., JSExpr]) -> None:
		"""Register a Python value for conversion via JSExpr.of().

		Args:
			value: The Python object to register (function, constant, etc.)
			expr: Either a JSExpr or a Callable[..., JSExpr] (will be wrapped in JSTransformer)
		"""
		if callable(expr) and not isinstance(expr, JSExpr):
			expr = JSTransformer(expr)
		JSEXPR_REGISTRY[id(value)] = expr

	def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
		"""Called when this expression is used as a function: expr(args).

		Override to customize call behavior. Default converts args/kwargs to
		JSExpr via JSExpr.of() and emits JSCall(self, args).
		Rejects keyword arguments by default.

		Args receive raw Python values. Use JSExpr.of() to convert as needed.

		The kwargs dict maps prop names to values:
		- "propName" -> value for named kwargs
		- "$spread{N}" -> JSSpread(expr) for **spread kwargs (already JSExpr)

		Dict order is preserved, so iteration order matches source order.
		"""
		if kwargs:
			raise JSCompilationError(
				"Keyword arguments not supported in default function call"
			)
		return JSCall(self, [JSExpr.of(a) for a in args])

	def emit_subscript(self, indices: list[Any]) -> JSExpr:
		"""Called when this expression is indexed: expr[a, b, c].

		Override to customize subscript behavior. Default requires single index
		and emits JSSubscript(self, index).

		Args receive raw Python values. Use JSExpr.of() to convert as needed.
		"""
		if len(indices) != 1:
			raise JSCompilationError("Multiple indices not supported in subscript")
		return JSSubscript(self, JSExpr.of(indices[0]))

	def emit_getattr(self, attr: str) -> JSExpr:
		"""Called when an attribute is accessed: expr.attr.

		Override to customize attribute access. Default emits JSMember(self, attr).
		"""
		return JSMember(self, attr)

	def __getattr__(self, attr: str) -> JSExpr:
		"""Support attribute access at Python runtime.

		Allows: expr.attr where expr is any JSExpr.
		Delegates to emit_getattr for transpilation.
		"""
		return self.emit_getattr(attr)

	def __call__(self, *args: Any, **kwargs: Any) -> JSExpr:
		"""Support function calls at Python runtime.

		Allows: expr(*args, **kwargs) where expr is any JSExpr.
		Delegates to emit_call for transpilation.
		"""
		return self.emit_call(list(args), kwargs)

	def __getitem__(self, key: Any) -> JSExpr:
		"""Support subscript access at Python runtime.

		Allows: expr[key] where expr is any JSExpr.
		Delegates to emit_subscript for transpilation.
		"""
		return self.emit_subscript([key])


class JSStmt(JSNode, ABC):
	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]


class JSIdentifier(JSExpr):
	__slots__ = ("name",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	name: str

	def __init__(self, name: str):
		self.name = name

	@override
	def emit(self) -> str:
		return self.name


class JSString(JSExpr):
	__slots__ = ("value",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	value: str

	def __init__(self, value: str):
		self.value = value

	@override
	def emit(self) -> str:
		s = self.value
		# Escape for double-quoted JS string literals
		s = (
			s.replace("\\", "\\\\")
			.replace('"', '\\"')
			.replace("\n", "\\n")
			.replace("\r", "\\r")
			.replace("\t", "\\t")
			.replace("\b", "\\b")
			.replace("\f", "\\f")
			.replace("\v", "\\v")
			.replace("\x00", "\\x00")
			.replace("\u2028", "\\u2028")
			.replace("\u2029", "\\u2029")
		)
		return f'"{s}"'


class JSNumber(JSExpr):
	__slots__ = ("value",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	value: int | float

	def __init__(self, value: int | float):
		self.value = value

	@override
	def emit(self) -> str:
		return str(self.value)


class JSBoolean(JSExpr):
	__slots__ = ("value",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	value: bool

	def __init__(self, value: bool):
		self.value = value

	@override
	def emit(self) -> str:
		return "true" if self.value else "false"


class JSNull(JSExpr):
	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True

	@override
	def emit(self) -> str:
		return "null"


class JSUndefined(JSExpr):
	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True

	@override
	def emit(self) -> str:
		return "undefined"


class JSArray(JSExpr):
	__slots__ = ("elements",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	elements: Sequence[JSExpr]

	def __init__(self, elements: Sequence[JSExpr]):
		self.elements = elements

	@override
	def emit(self) -> str:
		inner = ", ".join(e.emit() for e in self.elements)
		return f"[{inner}]"


class JSSpread(JSExpr):
	__slots__ = ("expr",)  # pyright: ignore[reportUnannotatedClassAttribute]
	expr: JSExpr

	def __init__(self, expr: JSExpr):
		self.expr = expr

	@override
	def emit(self) -> str:
		return f"...{self.expr.emit()}"


class JSProp(JSExpr):
	__slots__ = ("key", "value")  # pyright: ignore[reportUnannotatedClassAttribute]
	key: JSString
	value: JSExpr

	def __init__(self, key: JSString, value: JSExpr):
		self.key = key
		self.value = value

	@override
	def emit(self) -> str:
		return f"{self.key.emit()}: {self.value.emit()}"


class JSComputedProp(JSExpr):
	__slots__ = ("key", "value")  # pyright: ignore[reportUnannotatedClassAttribute]
	key: JSExpr
	value: JSExpr

	def __init__(self, key: JSExpr, value: JSExpr):
		self.key = key
		self.value = value

	@override
	def emit(self) -> str:
		return f"[{self.key.emit()}]: {self.value.emit()}"


class JSObjectExpr(JSExpr):
	__slots__ = ("props",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	props: Sequence[JSProp | JSComputedProp | JSSpread]

	def __init__(self, props: Sequence[JSProp | JSComputedProp | JSSpread]):
		self.props = props

	@override
	def emit(self) -> str:
		inner = ", ".join(p.emit() for p in self.props)
		return "{" + inner + "}"


class JSUnary(JSExpr):
	__slots__ = ("op", "operand")  # pyright: ignore[reportUnannotatedClassAttribute]
	op: str  # '-', '+', '!', 'typeof', 'await'
	operand: JSExpr

	def __init__(self, op: str, operand: JSExpr):
		self.op = op
		self.operand = operand

	@override
	def emit(self) -> str:
		operand_code = _emit_child_for_binary_like(
			self.operand, parent_op=self.op, side="unary"
		)
		if self.op == "typeof":
			return f"typeof {operand_code}"
		return f"{self.op}{operand_code}"


class JSAwait(JSExpr):
	__slots__ = ("operand",)  # pyright: ignore[reportUnannotatedClassAttribute]
	operand: JSExpr

	def __init__(self, operand: JSExpr):
		self.operand = operand

	@override
	def emit(self) -> str:
		operand_code = _emit_child_for_binary_like(
			self.operand, parent_op="await", side="unary"
		)
		return f"await {operand_code}"


class JSBinary(JSExpr):
	__slots__ = ("left", "op", "right")  # pyright: ignore[reportUnannotatedClassAttribute]
	left: JSExpr
	op: str
	right: JSExpr

	def __init__(self, left: JSExpr, op: str, right: JSExpr):
		self.left = left
		self.op = op
		self.right = right

	@override
	def emit(self) -> str:
		# Left child
		force_left_paren = False
		# Special JS grammar rule: left operand of ** cannot be a unary +/- without parentheses
		if (
			self.op == "**"
			and isinstance(self.left, JSUnary)
			and self.left.op in {"-", "+"}
		):
			force_left_paren = True
		left_code = _emit_child_for_binary_like(
			self.left,
			parent_op=self.op,
			side="left",
			force_paren=force_left_paren,
		)
		# Right child
		right_code = _emit_child_for_binary_like(
			self.right, parent_op=self.op, side="right"
		)
		return f"{left_code} {self.op} {right_code}"


class JSLogicalChain(JSExpr):
	__slots__ = ("op", "values")  # pyright: ignore[reportUnannotatedClassAttribute]
	op: str  # '&&' or '||'
	values: Sequence[JSExpr]

	def __init__(self, op: str, values: Sequence[JSExpr]):
		self.op = op
		self.values = values

	@override
	def emit(self) -> str:
		if len(self.values) == 1:
			return self.values[0].emit()
		parts: list[str] = []
		for v in self.values:
			# No strict left/right in chains, but treat as middle
			code = _emit_child_for_binary_like(v, parent_op=self.op, side="chain")
			parts.append(code)
		return f" {self.op} ".join(parts)


class JSTertiary(JSExpr):
	__slots__ = ("test", "if_true", "if_false")  # pyright: ignore[reportUnannotatedClassAttribute]
	test: JSExpr
	if_true: JSExpr
	if_false: JSExpr

	def __init__(self, test: JSExpr, if_true: JSExpr, if_false: JSExpr):
		self.test = test
		self.if_true = if_true
		self.if_false = if_false

	@override
	def emit(self) -> str:
		return f"{self.test.emit()} ? {self.if_true.emit()} : {self.if_false.emit()}"


class JSFunctionDef(JSExpr):
	__slots__ = ("params", "body", "name", "is_async")  # pyright: ignore[reportUnannotatedClassAttribute]
	params: Sequence[str]
	body: Sequence[JSStmt]
	name: str | None
	is_async: bool

	def __init__(
		self,
		params: Sequence[str],
		body: Sequence[JSStmt],
		name: str | None = None,
		is_async: bool = False,
	):
		self.params = params
		self.body = body
		self.name = name
		self.is_async = is_async

	@override
	def emit(self) -> str:
		params = ", ".join(self.params)
		body_code = "\n".join(s.emit() for s in self.body)
		prefix = "async " if self.is_async else ""
		if self.name:
			return f"{prefix}function {self.name}({params}){{\n{body_code}\n}}"
		return f"{prefix}function({params}){{\n{body_code}\n}}"


class JSTemplate(JSExpr):
	__slots__ = ("parts",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	parts: Sequence[str | JSExpr]

	def __init__(self, parts: Sequence[str | JSExpr]):
		# parts are either raw strings (literal text) or JSExpr instances which are
		# emitted inside ${...}
		self.parts = parts

	@override
	def emit(self) -> str:
		out: list[str] = ["`"]
		for p in self.parts:
			if isinstance(p, str):
				out.append(
					p.replace("\\", "\\\\")
					.replace("`", "\\`")
					.replace("${", "\\${")
					.replace("\n", "\\n")
					.replace("\r", "\\r")
					.replace("\t", "\\t")
					.replace("\b", "\\b")
					.replace("\f", "\\f")
					.replace("\v", "\\v")
					.replace("\x00", "\\x00")
					.replace("\u2028", "\\u2028")
					.replace("\u2029", "\\u2029")
				)
			else:
				out.append("${" + p.emit() + "}")
		out.append("`")
		return "".join(out)


class JSMember(JSExpr):
	__slots__ = ("obj", "prop")  # pyright: ignore[reportUnannotatedClassAttribute]
	obj: JSExpr
	prop: str

	def __init__(self, obj: JSExpr, prop: str):
		self.obj = obj
		self.prop = prop

	@override
	def emit(self) -> str:
		obj_code = _emit_child_for_primary(self.obj)
		return f"{obj_code}.{self.prop}"

	@override
	def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
		"""Called when this member is used as a function: obj.prop(args).

		Checks for Python builtin method transpilation (e.g., str.upper -> toUpperCase),
		then falls back to regular JSMemberCall.
		"""
		if kwargs:
			raise JSCompilationError("Keyword arguments not supported in method call")
		# Convert args to JSExpr
		js_args = [JSExpr.of(a) for a in args]
		# Check for Python builtin method transpilation (late import to avoid cycle)
		from pulse.transpiler.builtins import emit_method

		result = emit_method(self.obj, self.prop, js_args)
		if result is not None:
			return result
		return JSMemberCall(self.obj, self.prop, js_args)


class JSSubscript(JSExpr):
	__slots__ = ("obj", "index")  # pyright: ignore[reportUnannotatedClassAttribute]
	obj: JSExpr
	index: JSExpr

	def __init__(self, obj: JSExpr, index: JSExpr):
		self.obj = obj
		self.index = index

	@override
	def emit(self) -> str:
		obj_code = _emit_child_for_primary(self.obj)
		return f"{obj_code}[{self.index.emit()}]"


class JSCall(JSExpr):
	__slots__ = ("callee", "args")  # pyright: ignore[reportUnannotatedClassAttribute]
	callee: JSExpr  # typically JSIdentifier
	args: Sequence[JSExpr]

	def __init__(self, callee: JSExpr, args: Sequence[JSExpr]):
		self.callee = callee
		self.args = args

	@override
	def emit(self) -> str:
		fn = _emit_child_for_primary(self.callee)
		return f"{fn}({', '.join(a.emit() for a in self.args)})"


class JSMemberCall(JSExpr):
	__slots__ = ("obj", "method", "args")  # pyright: ignore[reportUnannotatedClassAttribute]
	obj: JSExpr
	method: str
	args: Sequence[JSExpr]

	def __init__(self, obj: JSExpr, method: str, args: Sequence[JSExpr]):
		self.obj = obj
		self.method = method
		self.args = args

	@override
	def emit(self) -> str:
		obj_code = _emit_child_for_primary(self.obj)
		return f"{obj_code}.{self.method}({', '.join(a.emit() for a in self.args)})"


class JSNew(JSExpr):
	__slots__ = ("ctor", "args")  # pyright: ignore[reportUnannotatedClassAttribute]
	ctor: JSExpr
	args: Sequence[JSExpr]

	def __init__(self, ctor: JSExpr, args: Sequence[JSExpr]):
		self.ctor = ctor
		self.args = args

	@override
	def emit(self) -> str:
		ctor_code = _emit_child_for_primary(self.ctor)
		return f"new {ctor_code}({', '.join(a.emit() for a in self.args)})"


class JSArrowFunction(JSExpr):
	__slots__ = ("params_code", "body")  # pyright: ignore[reportUnannotatedClassAttribute]
	params_code: str  # already formatted e.g. 'x' or '(a, b)' or '([k, v])'
	body: JSExpr | JSBlock

	def __init__(self, params_code: str, body: JSExpr | JSBlock):
		self.params_code = params_code
		self.body = body

	@override
	def emit(self) -> str:
		return f"{self.params_code} => {self.body.emit()}"


class JSComma(JSExpr):
	__slots__ = ("values",)  # pyright: ignore[reportUnannotatedClassAttribute]
	values: Sequence[JSExpr]

	def __init__(self, values: Sequence[JSExpr]):
		self.values = values

	@override
	def emit(self) -> str:
		# Always wrap comma expressions in parentheses to avoid precedence surprises
		inner = ", ".join(v.emit() for v in self.values)
		return f"({inner})"


class JSTransformer(JSExpr):
	"""JSExpr that wraps a function transforming JSExpr args to JSExpr output.

	Generalizes the pattern of call-only expressions. The wrapped function
	receives positional and keyword JSExpr arguments and returns a JSExpr.

	Example:
		emit_len = JSTransformer(lambda x: JSMember(x, "length"), name="len")
		# When called: emit_len.emit_call([some_expr], {}) -> JSMember(some_expr, "length")
	"""

	__slots__ = ("fn", "name")  # pyright: ignore[reportUnannotatedClassAttribute]
	fn: Callable[..., JSExpr]
	name: str  # Optional name for error messages

	def __init__(self, fn: Callable[..., JSExpr], name: str = ""):
		self.fn = fn
		self.name = name

	@override
	def emit(self) -> str:
		label = self.name or "JSTransformer"
		raise JSCompilationError(f"{label} cannot be emitted directly - must be called")

	@override
	def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
		# Pass raw args to the transformer function - it decides what to convert
		if kwargs:
			return self.fn(*args, **kwargs)
		return self.fn(*args)

	@override
	def emit_subscript(self, indices: list[Any]) -> JSExpr:
		label = self.name or "JSTransformer"
		raise JSCompilationError(f"{label} cannot be subscripted")

	@override
	def emit_getattr(self, attr: str) -> JSExpr:
		label = self.name or "JSTransformer"
		raise JSCompilationError(f"{label} cannot have attributes")


_F = TypeVar("_F", bound=Callable[..., Any])


@overload
def js_transformer(arg: str) -> Callable[[_F], _F]: ...


@overload
def js_transformer(arg: _F) -> _F: ...


def js_transformer(arg: str | _F) -> Callable[[_F], _F] | _F:
	"""Decorator/helper for JSTransformer.

	Usage:
		@js_transformer("len")
		def emit_len(x): ...
	or:
		emit_len = js_transformer(lambda x: ...)

	Returns a JSTransformer, but the type signature lies and preserves
	the original function type. This allows decorated functions to have
	proper return types (e.g., NoReturn for throw).
	"""
	if isinstance(arg, str):

		def decorator(fn: _F) -> _F:
			return cast(_F, JSTransformer(fn, name=arg))

		return decorator
	elif callable(arg):
		return cast(_F, JSTransformer(arg))
	else:
		raise TypeError(
			"js_transformer expects a function or string (for decorator usage)"
		)


class JSReturn(JSStmt):
	__slots__ = ("value",)  # pyright: ignore[reportUnannotatedClassAttribute]
	value: JSExpr

	def __init__(self, value: JSExpr):
		self.value = value

	@override
	def emit(self) -> str:
		return f"return {self.value.emit()};"


class JSThrow(JSStmt):
	__slots__ = ("value",)  # pyright: ignore[reportUnannotatedClassAttribute]
	value: JSExpr

	def __init__(self, value: JSExpr):
		self.value = value

	@override
	def emit(self) -> str:
		return f"throw {self.value.emit()};"


class JSStmtExpr(JSExpr):
	"""Expression wrapper for a statement (e.g., throw).

	Used for constructs like `throw(x)` that syntactically look like function calls
	but must be emitted as statements. When used as an expression-statement,
	the transpiler unwraps this and emits the inner statement directly.
	"""

	__slots__ = ("stmt", "name")  # pyright: ignore[reportUnannotatedClassAttribute]
	stmt: JSStmt
	name: str  # For error messages (e.g., "throw")

	def __init__(self, stmt: JSStmt, name: str = ""):
		self.stmt = stmt
		self.name = name

	@override
	def emit(self) -> str:
		label = self.name or "statement"
		raise JSCompilationError(
			f"'{label}' cannot be used inside an expression. "
			+ "Use it as a standalone statement instead. "
			+ f"For example, write `{label}(x)` on its own line, not `y = {label}(x)` or `f({label}(x))`."
		)


class JSAssign(JSStmt):
	__slots__ = ("name", "value", "declare")  # pyright: ignore[reportUnannotatedClassAttribute]
	name: str
	value: JSExpr
	declare: bool  # when True emit 'let name = ...'

	def __init__(self, name: str, value: JSExpr, declare: bool = False):
		self.name = name
		self.value = value
		self.declare = declare

	@override
	def emit(self) -> str:
		if self.declare:
			return f"let {self.name} = {self.value.emit()};"
		return f"{self.name} = {self.value.emit()};"


class JSRaw(JSExpr):
	__slots__ = ("content",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_primary: ClassVar[bool] = True
	content: str

	def __init__(self, content: str):
		self.content = content

	@override
	def emit(self) -> str:
		return self.content


###############################################################################
# JSX AST (minimal)
###############################################################################


def _check_not_interpreted_mode(node_type: str) -> None:
	"""Raise an error if we're in interpreted mode - JSX can't be eval'd."""
	if is_interpreted_mode():
		raise ValueError(
			f"{node_type} cannot be used in interpreted mode (as a prop or child value). "
			+ "JSX syntax requires transpilation and cannot be evaluated at runtime. "
			+ "Use standard VDOM elements (ps.div, ps.span, etc.) instead."
		)


def _escape_jsx_text(text: str) -> str:
	# Minimal escaping for text nodes
	return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class JSXProp(JSExpr):
	__slots__ = ("name", "value")  # pyright: ignore[reportUnannotatedClassAttribute]
	name: str
	value: JSExpr | None

	def __init__(self, name: str, value: JSExpr | None = None):
		self.name = name
		self.value = value

	@override
	def emit(self) -> str:
		_check_not_interpreted_mode("JSXProp")
		if self.value is None:
			return self.name
		# Prefer compact string literal attribute when possible
		if isinstance(self.value, JSString):
			return f"{self.name}={self.value.emit()}"
		return self.name + "={" + self.value.emit() + "}"


class JSXSpreadProp(JSExpr):
	__slots__ = ("value",)  # pyright: ignore[reportUnannotatedClassAttribute]
	value: JSExpr

	def __init__(self, value: JSExpr):
		self.value = value

	@override
	def emit(self) -> str:
		_check_not_interpreted_mode("JSXSpreadProp")
		return f"{{...{self.value.emit()}}}"


class JSXElement(JSExpr):
	__slots__ = ("tag", "props", "children")  # pyright: ignore[reportUnannotatedClassAttribute]
	is_jsx: ClassVar[bool] = True
	is_primary: ClassVar[bool] = True
	tag: str | JSExpr
	props: Sequence[JSXProp | JSXSpreadProp]
	children: Sequence[str | JSExpr | JSXElement]

	def __init__(
		self,
		tag: str | JSExpr,
		props: Sequence[JSXProp | JSXSpreadProp] = (),
		children: Sequence[str | JSExpr | JSXElement] = (),
	):
		self.tag = tag
		self.props = props
		self.children = children

	@override
	def emit(self) -> str:
		_check_not_interpreted_mode("JSXElement")
		tag_code = self.tag if isinstance(self.tag, str) else self.tag.emit()
		props_code = " ".join(p.emit() for p in self.props) if self.props else ""
		if not self.children:
			if props_code:
				return f"<{tag_code} {props_code} />"
			return f"<{tag_code} />"
		# Open tag
		open_tag = f"<{tag_code}>" if not props_code else f"<{tag_code} {props_code}>"
		# Children
		child_parts: list[str] = []
		for c in self.children:
			if isinstance(c, str):
				child_parts.append(_escape_jsx_text(c))
			elif isinstance(c, JSXElement) or (isinstance(c, JSExpr) and c.is_jsx):
				child_parts.append(c.emit())
			else:
				child_parts.append("{" + c.emit() + "}")
		inner = "".join(child_parts)
		return f"{open_tag}{inner}</{tag_code}>"


class JSXFragment(JSExpr):
	__slots__ = ("children",)  # pyright: ignore[reportUnannotatedClassAttribute]
	is_jsx: ClassVar[bool] = True
	is_primary: ClassVar[bool] = True
	children: Sequence[str | JSExpr | JSXElement]

	def __init__(self, children: Sequence[str | JSExpr | JSXElement] = ()):
		self.children = children

	@override
	def emit(self) -> str:
		_check_not_interpreted_mode("JSXFragment")
		if not self.children:
			return "<></>"
		parts: list[str] = []
		for c in self.children:
			if isinstance(c, str):
				parts.append(_escape_jsx_text(c))
			elif isinstance(c, JSXElement) or (isinstance(c, JSExpr) and c.is_jsx):
				parts.append(c.emit())
			else:
				parts.append("{" + c.emit() + "}")
		return "<>" + "".join(parts) + "</>"


class JSImport:
	__slots__ = ("src", "default", "named")  # pyright: ignore[reportUnannotatedClassAttribute]
	src: str
	default: str | None
	named: list[str | tuple[str, str]]

	def __init__(
		self,
		src: str,
		default: str | None = None,
		named: list[str | tuple[str, str]] | None = None,
	):
		self.src = src
		self.default = default
		self.named = named if named is not None else []

	def emit(self) -> str:
		parts: list[str] = []
		if self.default:
			parts.append(self.default)
		if self.named:
			named_parts: list[str] = []
			for n in self.named:
				if isinstance(n, tuple):
					named_parts.append(f"{n[0]} as {n[1]}")
				else:
					named_parts.append(n)
			if named_parts:
				if self.default:
					parts.append(",")
				parts.append("{" + ", ".join(named_parts) + "}")
		return f"import {' '.join(parts)} from {JSString(self.src).emit()};"


# -----------------------------
# Precedence helpers
# -----------------------------

PRIMARY_PRECEDENCE = 20


def op_precedence(op: str) -> int:
	# Higher number = binds tighter
	if op in {".", "[]", "()"}:  # pseudo ops for primary contexts
		return PRIMARY_PRECEDENCE
	if op in {"!", "+u", "-u"}:  # unary; we encode + and - as unary with +u/-u
		return 17
	if op in {"typeof", "await"}:
		return 17
	if op == "**":
		return 16
	if op in {"*", "/", "%"}:
		return 15
	if op in {"+", "-"}:
		return 14
	if op in {"<", "<=", ">", ">=", "===", "!=="}:
		return 12
	if op == "instanceof":
		return 12
	if op == "in":
		return 12
	if op == "&&":
		return 7
	if op == "||":
		return 6
	if op == "??":
		return 6
	if op == "?:":  # ternary
		return 4
	if op == ",":
		return 1
	return 0


def op_is_right_associative(op: str) -> bool:
	return op == "**"


def expr_precedence(e: JSExpr) -> int:
	if isinstance(e, JSBinary):
		return op_precedence(e.op)
	if isinstance(e, JSUnary):
		# Distinguish unary + and - from binary precedence table by tag
		tag = "+u" if e.op == "+" else ("-u" if e.op == "-" else e.op)
		return op_precedence(tag)
	if isinstance(e, JSAwait):
		return op_precedence("await")
	if isinstance(e, JSTertiary):
		return op_precedence("?:")
	if isinstance(e, JSLogicalChain):
		return op_precedence(e.op)
	if isinstance(e, JSComma):
		return op_precedence(",")
	# Nullish now represented as JSBinary with op "??"; precedence resolved below
	if isinstance(e, (JSMember, JSSubscript, JSCall, JSMemberCall, JSNew)):
		return op_precedence(".")
	# Primary expressions (identifiers, literals, containers) don't need parens
	if e.is_primary:
		return PRIMARY_PRECEDENCE
	return 0


class JSBlock(JSStmt):
	__slots__ = ("body",)  # pyright: ignore[reportUnannotatedClassAttribute]
	body: Sequence[JSStmt]

	def __init__(self, body: Sequence[JSStmt]):
		self.body = body

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		return f"{{\n{body_code}\n}}"


class JSAugAssign(JSStmt):
	__slots__ = ("name", "op", "value")  # pyright: ignore[reportUnannotatedClassAttribute]
	name: str
	op: str
	value: JSExpr

	def __init__(self, name: str, op: str, value: JSExpr):
		self.name = name
		self.op = op
		self.value = value

	@override
	def emit(self) -> str:
		return f"{self.name} {self.op}= {self.value.emit()};"


class JSConstAssign(JSStmt):
	__slots__ = ("name", "value")  # pyright: ignore[reportUnannotatedClassAttribute]
	name: str
	value: JSExpr

	def __init__(self, name: str, value: JSExpr):
		self.name = name
		self.value = value

	@override
	def emit(self) -> str:
		return f"const {self.name} = {self.value.emit()};"


class JSSingleStmt(JSStmt):
	__slots__ = ("expr",)  # pyright: ignore[reportUnannotatedClassAttribute]
	expr: JSExpr

	def __init__(self, expr: JSExpr):
		self.expr = expr

	@override
	def emit(self) -> str:
		return f"{self.expr.emit()};"


class JSMultiStmt(JSStmt):
	__slots__ = ("stmts",)  # pyright: ignore[reportUnannotatedClassAttribute]
	stmts: Sequence[JSStmt]

	def __init__(self, stmts: Sequence[JSStmt]):
		self.stmts = stmts

	@override
	def emit(self) -> str:
		return "\n".join(s.emit() for s in self.stmts)


class JSIf(JSStmt):
	__slots__ = ("test", "body", "orelse")  # pyright: ignore[reportUnannotatedClassAttribute]
	test: JSExpr
	body: Sequence[JSStmt]
	orelse: Sequence[JSStmt]

	def __init__(
		self, test: JSExpr, body: Sequence[JSStmt], orelse: Sequence[JSStmt] = ()
	):
		self.test = test
		self.body = body
		self.orelse = orelse

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		if not self.orelse:
			return f"if ({self.test.emit()}){{\n{body_code}\n}}"
		else_code = "\n".join(s.emit() for s in self.orelse)
		return f"if ({self.test.emit()}){{\n{body_code}\n}} else {{\n{else_code}\n}}"


class JSForOf(JSStmt):
	__slots__ = ("target", "iter_expr", "body")  # pyright: ignore[reportUnannotatedClassAttribute]
	target: str | list[str]
	iter_expr: JSExpr
	body: Sequence[JSStmt]

	def __init__(
		self, target: str | list[str], iter_expr: JSExpr, body: Sequence[JSStmt]
	):
		self.target = target
		self.iter_expr = iter_expr
		self.body = body

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		target = self.target
		if not isinstance(target, str):
			target = f"[{', '.join(x for x in target)}]"
		return f"for (const {target} of {self.iter_expr.emit()}){{\n{body_code}\n}}"


class JSWhile(JSStmt):
	__slots__ = ("test", "body")  # pyright: ignore[reportUnannotatedClassAttribute]
	test: JSExpr
	body: Sequence[JSStmt]

	def __init__(self, test: JSExpr, body: Sequence[JSStmt]):
		self.test = test
		self.body = body

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		return f"while ({self.test.emit()}){{\n{body_code}\n}}"


class JSBreak(JSStmt):
	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]

	@override
	def emit(self) -> str:
		return "break;"


class JSContinue(JSStmt):
	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]

	@override
	def emit(self) -> str:
		return "continue;"


def _mixes_nullish_and_logical(parent_op: str, child: JSExpr) -> bool:
	if parent_op in {"&&", "||"} and isinstance(child, JSBinary) and child.op == "??":
		return True
	if parent_op == "??" and isinstance(child, JSLogicalChain):
		return True
	return False


def _emit_child_for_binary_like(
	child: JSExpr, parent_op: str, side: str, force_paren: bool = False
) -> str:
	# side is one of: 'left', 'right', 'unary', 'chain'
	code = child.emit()
	if force_paren:
		return f"({code})"
	# Ternary as child should always be wrapped under binary-like contexts
	if isinstance(child, JSTertiary):
		return f"({code})"
	# Explicit parens when mixing ?? with &&/||
	if _mixes_nullish_and_logical(parent_op, child):
		return f"({code})"
	child_prec = expr_precedence(child)
	parent_prec = op_precedence(parent_op)
	if child_prec < parent_prec:
		return f"({code})"
	if child_prec == parent_prec:
		# Handle associativity for exact same precedence buckets
		if isinstance(child, JSBinary):
			if op_is_right_associative(parent_op):
				# Need parens on left child for same prec to preserve grouping
				if side == "left":
					return f"({code})"
			else:
				# Left-associative: protect right child when equal precedence
				if side == "right":
					return f"({code})"
		if isinstance(child, JSLogicalChain):
			# Same op chains don't need parens; different logical ops rely on precedence
			if child.op != parent_op:
				# '&&' has higher precedence than '||'; no parens needed for tighter child
				# But if equal (shouldn't happen here), remain as-is
				pass
		# For other equal-precedence non-binary nodes, keep as-is
	return code


def _emit_child_for_primary(expr: JSExpr) -> str:
	code = expr.emit()
	if expr_precedence(expr) < PRIMARY_PRECEDENCE or isinstance(expr, JSTertiary):
		return f"({code})"
	return code


def is_primary(expr: JSExpr):
	return isinstance(expr, (JSNumber, JSString, JSUndefined, JSNull, JSIdentifier))
