from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from inspect import isfunction
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar, cast, overload, override
from typing import Literal as Lit

if TYPE_CHECKING:
	from pulse.transpiler_v2.transpiler import Transpiler

Primitive: TypeAlias = bool | int | float | str | dt.datetime | None

# Global registry: id(value) -> ExprNode
# Used by ExprNode.of() to resolve registered Python values
EXPR_REGISTRY: dict[int, "ExprNode"] = {}
TransformerFn: TypeAlias = Callable[..., "ExprNode"]
_F = TypeVar("_F", bound="Callable[[*tuple[Any, ...], Transpiler], Any]")


# =============================================================================
# Base classes
# =============================================================================
class Node(ABC):
	"""Base class for all AST nodes."""

	__slots__: tuple[str, ...] = ()

	@abstractmethod
	def emit(self, out: list[str]) -> None:
		"""Emit this node as JavaScript/JSX code into the output buffer."""


class ExprNode(Node, ABC):
	"""Base class for expression nodes.

	Provides hooks for custom transpilation behavior:
	- emit_call: customize behavior when called as a function
	- emit_getattr: customize attribute access
	- emit_subscript: customize subscript access

	And serialization for client-side rendering:
	- render: serialize to dict for client renderer (stub for now)
	"""

	__slots__: tuple[str, ...] = ()

	def precedence(self) -> int:
		"""Operator precedence (higher = binds tighter). Default: primary (20)."""
		return 20

	# -------------------------------------------------------------------------
	# Transpilation hooks (override to customize behavior)
	# -------------------------------------------------------------------------

	def emit_call(
		self,
		args: list[Any],
		kwargs: dict[str, Any],
		ctx: Transpiler,
	) -> ExprNode:
		"""Called when this expression is used as a function: expr(args).

		Override to customize call behavior.
		Default raises - most expressions are not callable.

		Args and kwargs are raw Python AST values (not yet emitted).
		Use ctx.emit_expr() to convert them to ExprNode as needed.
		"""
		raise NotImplementedError(f"{type(self).__name__} is not callable")

	def emit_getattr(self, attr: str, ctx: Transpiler) -> ExprNode:
		"""Called when an attribute is accessed: expr.attr.

		Override to customize attribute access.
		Default returns Member(self, attr).
		"""
		return Member(self, attr)

	def emit_subscript(self, key: Any, ctx: Transpiler) -> ExprNode:
		"""Called when subscripted: expr[key].

		Override to customize subscript behavior.
		Default returns Subscript(self, emitted_key).
		"""
		return Subscript(self, ctx.emit_expr(key))

	# -------------------------------------------------------------------------
	# Serialization for client-side rendering (stub for now)
	# -------------------------------------------------------------------------

	def render(self) -> dict[str, Any]:
		"""Serialize this node for client-side rendering.

		Override in concrete serializable nodes.
		Raises NotImplementedError for nodes that cannot be serialized.
		"""
		raise NotImplementedError(
			f"{type(self).__name__} cannot be serialized for client rendering"
		)

	# -------------------------------------------------------------------------
	# Registry for Python value -> ExprNode mapping
	# -------------------------------------------------------------------------

	@staticmethod
	def of(value: Any) -> ExprNode:
		"""Convert a Python value to an ExprNode.

		Resolution order:
		1. Already an ExprNode: returned as-is
		2. Registered in EXPR_REGISTRY: return the registered expr
		3. Primitives: str/int/float -> Literal, bool -> Literal, None -> Literal(None)
		4. Collections: list/tuple -> Array, dict -> Object (recursively converted)
		5. set -> Call(Identifier("Set"), [Array(...)])

		Raises TypeError for unconvertible values.
		"""
		# Already an ExprNode
		if isinstance(value, ExprNode):
			return value

		# Check registry (for modules, functions, etc.)
		if (expr := EXPR_REGISTRY.get(id(value))) is not None:
			return expr

		# Primitives - must check bool before int since bool is subclass of int
		if isinstance(value, bool):
			return Literal(value)
		if isinstance(value, (int, float, str)):
			return Literal(value)
		if value is None:
			return Literal(None)

		# Collections
		if isinstance(value, (list, tuple)):
			return Array([ExprNode.of(v) for v in value])
		if isinstance(value, dict):
			props = [(str(k), ExprNode.of(v)) for k, v in value.items()]  # pyright: ignore[reportUnknownArgumentType]
			return Object(props)
		if isinstance(value, set):
			# new Set([...])
			return New(Identifier("Set"), [Array([ExprNode.of(v) for v in value])])

		raise TypeError(f"Cannot convert {type(value).__name__} to ExprNode")

	@staticmethod
	def register(value: Any, expr: ExprNode | Callable[..., ExprNode]) -> None:
		"""Register a Python value for conversion via ExprNode.of().

		Args:
			value: The Python object to register (function, constant, etc.)
			expr: Either an ExprNode or a Callable[..., ExprNode] (will be wrapped in Transformer)
		"""
		if callable(expr) and not isinstance(expr, ExprNode):
			expr = Transformer(expr)
		EXPR_REGISTRY[id(value)] = expr


class StmtNode(Node, ABC):
	"""Base class for statement nodes."""

	__slots__: tuple[str, ...] = ()


# =============================================================================
# Data Nodes
# =============================================================================


@dataclass(slots=True)
class ValueNode(ExprNode):
	"""Wraps a non-primitive Python value for pass-through serialization.

	Use cases:
	- Complex prop values: options={"a": 1, "b": 2}
	- Server-computed data passed to client components
	- Any value that doesn't need expression semantics
	"""

	value: Any

	@override
	def emit(self, out: list[str]) -> None:
		_emit_value(self.value, out)


@dataclass(slots=True)
class ElementNode(ExprNode):
	"""A React element: built-in tag, fragment, or client component.

	Tag conventions:
	- "" (empty): Fragment
	- "div", "span", etc.: HTML element
	- "$$ComponentId": Client component (registered in JS registry)
	"""

	tag: str
	props: dict[str, Prop] | None = None
	children: Sequence[Child] | None = None
	key: str | None = None

	@override
	def emit(self, out: list[str]) -> None:
		# Fragment
		if not self.tag:
			if self.key is not None:
				# Fragment with key needs explicit Fragment component
				out.append('<Fragment key="')
				out.append(_escape_jsx_attr(self.key))
				out.append('">')
				for c in self.children or []:
					_emit_jsx_child(c, out)
				out.append("</Fragment>")
			else:
				out.append("<>")
				for c in self.children or []:
					_emit_jsx_child(c, out)
				out.append("</>")
			return

		# Resolve tag (strip $$ prefix for client components)
		tag = self.tag[2:] if self.tag.startswith("$$") else self.tag

		# Build props into a separate buffer to check if empty
		props_out: list[str] = []
		if self.key is not None:
			props_out.append('key="')
			props_out.append(_escape_jsx_attr(self.key))
			props_out.append('"')
		if self.props:
			for name, value in self.props.items():
				if props_out:
					props_out.append(" ")
				_emit_jsx_prop(name, value, props_out)

		# Build children into a separate buffer to check if empty
		children_out: list[str] = []
		for c in self.children or []:
			_emit_jsx_child(c, children_out)

		# Self-closing if no children
		if not children_out:
			out.append("<")
			out.append(tag)
			if props_out:
				out.append(" ")
				out.extend(props_out)
			out.append(" />")
			return

		# Open tag
		out.append("<")
		out.append(tag)
		if props_out:
			out.append(" ")
			out.extend(props_out)
		out.append(">")
		# Children
		out.extend(children_out)
		# Close tag
		out.append("</")
		out.append(tag)
		out.append(">")

	def with_children(self, children: Sequence[Child]) -> ElementNode:
		"""Return new ElementNode with children set.

		Raises if this element already has children.
		"""
		if self.children:
			raise ValueError(
				f"ElementNode '{self.tag}' already has children; cannot add more via subscript"
			)
		return ElementNode(
			tag=self.tag,
			props=self.props,
			children=list(children),
			key=self.key,
		)


@dataclass(slots=True)
class PulseNode(Node):
	"""A Pulse server-side component instance.

	During rendering, PulseNode is called and replaced by its returned tree.
	Can only appear in VDOM context (render path), never in transpiled code.
	"""

	fn: Any  # Callable[..., Child]
	args: tuple[Any, ...] = ()
	kwargs: dict[str, Any] = field(default_factory=dict)
	key: str | None = None
	# Renderer state (mutable, set during render)
	hooks: Any = None  # HookContext
	contents: Child | None = None

	@override
	def emit(self, out: list[str]) -> None:
		fn_name = getattr(self.fn, "__name__", "unknown")
		raise TypeError(
			f"Cannot transpile PulseNode '{fn_name}'. "
			+ "Server components must be rendered, not transpiled."
		)


# =============================================================================
# Expression Nodes
# =============================================================================


@dataclass(slots=True)
class Identifier(ExprNode):
	"""JS identifier: x, foo, myFunc"""

	name: str

	@override
	def emit(self, out: list[str]) -> None:
		out.append(self.name)


@dataclass(slots=True)
class Literal(ExprNode):
	"""JS literal: 42, "hello", true, null"""

	value: int | float | str | bool | None

	@override
	def emit(self, out: list[str]) -> None:
		if self.value is None:
			out.append("null")
		elif isinstance(self.value, bool):
			out.append("true" if self.value else "false")
		elif isinstance(self.value, str):
			out.append('"')
			out.append(_escape_string(self.value))
			out.append('"')
		else:
			out.append(str(self.value))


class Undefined(ExprNode):
	"""JS undefined literal.

	Use Undefined() for JS `undefined`. Literal(None) emits `null`.
	This is a singleton-like class with no fields.
	"""

	__slots__: tuple[str, ...] = ()

	@override
	def emit(self, out: list[str]) -> None:
		out.append("undefined")


# Singleton instance for convenience
UNDEFINED = Undefined()


@dataclass(slots=True)
class Array(ExprNode):
	"""JS array: [a, b, c]"""

	elements: Sequence[ExprNode]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("[")
		for i, e in enumerate(self.elements):
			if i > 0:
				out.append(", ")
			e.emit(out)
		out.append("]")


@dataclass(slots=True)
class Object(ExprNode):
	"""JS object: { key: value }"""

	props: Sequence[tuple[str, ExprNode]]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("{")
		for i, (k, v) in enumerate(self.props):
			if i > 0:
				out.append(", ")
			out.append('"')
			out.append(_escape_string(k))
			out.append('": ')
			v.emit(out)
		out.append("}")


@dataclass(slots=True)
class Member(ExprNode):
	"""JS member access: obj.prop"""

	obj: ExprNode
	prop: str

	@override
	def emit(self, out: list[str]) -> None:
		_emit_primary(self.obj, out)
		out.append(".")
		out.append(self.prop)


@dataclass(slots=True)
class Subscript(ExprNode):
	"""JS subscript access: obj[key]"""

	obj: ExprNode
	key: ExprNode

	@override
	def emit(self, out: list[str]) -> None:
		_emit_primary(self.obj, out)
		out.append("[")
		self.key.emit(out)
		out.append("]")


@dataclass(slots=True)
class Call(ExprNode):
	"""JS function call: fn(args)"""

	callee: ExprNode
	args: Sequence[ExprNode]

	@override
	def emit(self, out: list[str]) -> None:
		_emit_primary(self.callee, out)
		out.append("(")
		for i, a in enumerate(self.args):
			if i > 0:
				out.append(", ")
			a.emit(out)
		out.append(")")


@dataclass(slots=True)
class Unary(ExprNode):
	"""JS unary expression: -x, !x, typeof x"""

	op: str
	operand: ExprNode

	@override
	def precedence(self) -> int:
		op = self.op
		tag = "+u" if op == "+" else ("-u" if op == "-" else op)
		return _PRECEDENCE.get(tag, 17)

	@override
	def emit(self, out: list[str]) -> None:
		if self.op in {"typeof", "await", "void", "delete"}:
			out.append(self.op)
			out.append(" ")
		else:
			out.append(self.op)
		_emit_paren(self.operand, self.op, "unary", out)


@dataclass(slots=True)
class Binary(ExprNode):
	"""JS binary expression: x + y, a && b"""

	left: ExprNode
	op: str
	right: ExprNode

	@override
	def precedence(self) -> int:
		return _PRECEDENCE.get(self.op, 0)

	@override
	def emit(self, out: list[str]) -> None:
		# Special: ** with unary +/- on left needs parens
		force_left = (
			self.op == "**"
			and isinstance(self.left, Unary)
			and self.left.op in {"-", "+"}
		)
		if force_left:
			out.append("(")
			self.left.emit(out)
			out.append(")")
		else:
			_emit_paren(self.left, self.op, "left", out)
		out.append(" ")
		out.append(self.op)
		out.append(" ")
		_emit_paren(self.right, self.op, "right", out)


@dataclass(slots=True)
class Ternary(ExprNode):
	"""JS ternary expression: cond ? a : b"""

	cond: ExprNode
	then: ExprNode
	else_: ExprNode

	@override
	def precedence(self) -> int:
		return _PRECEDENCE["?:"]

	@override
	def emit(self, out: list[str]) -> None:
		self.cond.emit(out)
		out.append(" ? ")
		self.then.emit(out)
		out.append(" : ")
		self.else_.emit(out)


@dataclass(slots=True)
class Arrow(ExprNode):
	"""JS arrow function: (x) => expr or (x) => { ... }"""

	params: Sequence[str]
	body: ExprNode

	@override
	def emit(self, out: list[str]) -> None:
		if len(self.params) == 1:
			out.append(self.params[0])
		else:
			out.append("(")
			out.append(", ".join(self.params))
			out.append(")")
		out.append(" => ")
		self.body.emit(out)


@dataclass(slots=True)
class Template(ExprNode):
	"""JS template literal: `hello ${name}`

	Parts alternate: [str, ExprNode, str, ExprNode, str, ...]
	Always starts and ends with a string (may be empty).
	"""

	parts: Sequence[str | ExprNode]  # alternating, starting with str

	@override
	def emit(self, out: list[str]) -> None:
		out.append("`")
		for p in self.parts:
			if isinstance(p, str):
				out.append(_escape_template(p))
			else:
				out.append("${")
				p.emit(out)
				out.append("}")
		out.append("`")


@dataclass(slots=True)
class Spread(ExprNode):
	"""JS spread: ...expr"""

	expr: ExprNode

	@override
	def emit(self, out: list[str]) -> None:
		out.append("...")
		self.expr.emit(out)


@dataclass(slots=True)
class New(ExprNode):
	"""JS new expression: new Ctor(args)"""

	ctor: ExprNode
	args: Sequence[ExprNode]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("new ")
		self.ctor.emit(out)
		out.append("(")
		for i, a in enumerate(self.args):
			if i > 0:
				out.append(", ")
			a.emit(out)
		out.append(")")


@dataclass(slots=True)
class Transformer(ExprNode):
	"""ExprNode that wraps a function transforming args to ExprNode output.

	Used for Python->JS transpilation of functions, builtins, and module attrs.
	The wrapped function receives args/kwargs and ctx, and returns an ExprNode.

	Example:
		emit_len = Transformer(lambda x, ctx: Member(ctx.emit_expr(x), "length"), name="len")
		# When called: emit_len.emit_call([some_expr], {}, ctx) -> Member(some_expr, "length")
	"""

	fn: TransformerFn
	name: str = ""  # For error messages

	@override
	def emit(self, out: list[str]) -> None:
		label = self.name or "Transformer"
		raise TypeError(f"{label} cannot be emitted directly - must be called")

	@override
	def emit_call(
		self,
		args: list[Any],
		kwargs: dict[str, Any],
		ctx: Transpiler,
	) -> ExprNode:
		if kwargs:
			return self.fn(*args, ctx=ctx, **kwargs)
		return self.fn(*args, ctx=ctx)

	@override
	def emit_getattr(self, attr: str, ctx: Transpiler) -> ExprNode:
		label = self.name or "Transformer"
		raise TypeError(f"{label} cannot have attributes")

	@override
	def emit_subscript(self, key: Any, ctx: Transpiler) -> ExprNode:
		label = self.name or "Transformer"
		raise TypeError(f"{label} cannot be subscripted")


@overload
def transformer(arg: str) -> Callable[[_F], _F]: ...


@overload
def transformer(arg: _F) -> _F: ...


def transformer(arg: str | _F) -> Callable[[_F], _F] | _F:
	"""Decorator/helper for Transformer.

	Usage:
		@transformer("len")
		def emit_len(x, *, ctx): ...
	or:
		emit_len = transformer(lambda x, *, ctx: ...)

	Returns a Transformer, but the type signature lies and preserves
	the original function type.
	"""
	if isinstance(arg, str):

		def decorator(fn: _F) -> _F:
			return cast(_F, Transformer(fn, name=arg))

		return decorator
	elif isfunction(arg):
		# Use empty name for lambdas, function name for named functions
		name = "" if arg.__name__ == "<lambda>" else arg.__name__
		return cast(_F, Transformer(arg, name=name))
	else:
		raise TypeError(
			"transformer expects a function or string (for decorator usage)"
		)


# =============================================================================
# Statement Nodes
# =============================================================================


@dataclass(slots=True)
class Return(StmtNode):
	"""JS return statement: return expr;"""

	value: ExprNode | None = None

	@override
	def emit(self, out: list[str]) -> None:
		out.append("return")
		if self.value is not None:
			out.append(" ")
			self.value.emit(out)
		out.append(";")


@dataclass(slots=True)
class If(StmtNode):
	"""JS if statement: if (cond) { ... } else { ... }"""

	cond: ExprNode
	then: Sequence[StmtNode]
	else_: Sequence[StmtNode] = ()

	@override
	def emit(self, out: list[str]) -> None:
		out.append("if (")
		self.cond.emit(out)
		out.append(") {\n")
		for stmt in self.then:
			stmt.emit(out)
			out.append("\n")
		out.append("}")
		if self.else_:
			out.append(" else {\n")
			for stmt in self.else_:
				stmt.emit(out)
				out.append("\n")
			out.append("}")


@dataclass(slots=True)
class ForOf(StmtNode):
	"""JS for-of loop: for (const x of iter) { ... }

	target can be a single name or array pattern for destructuring: [a, b]
	"""

	target: str
	iter: ExprNode
	body: Sequence[StmtNode]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("for (const ")
		out.append(self.target)
		out.append(" of ")
		self.iter.emit(out)
		out.append(") {\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")


@dataclass(slots=True)
class While(StmtNode):
	"""JS while loop: while (cond) { ... }"""

	cond: ExprNode
	body: Sequence[StmtNode]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("while (")
		self.cond.emit(out)
		out.append(") {\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")


@dataclass(slots=True)
class Break(StmtNode):
	"""JS break statement."""

	@override
	def emit(self, out: list[str]) -> None:
		out.append("break;")


@dataclass(slots=True)
class Continue(StmtNode):
	"""JS continue statement."""

	@override
	def emit(self, out: list[str]) -> None:
		out.append("continue;")


@dataclass(slots=True)
class Assign(StmtNode):
	"""JS assignment: let x = expr; or x = expr; or x += expr;

	declare: "let", "const", or None (reassignment)
	op: None for =, or "+", "-", etc. for augmented assignment
	"""

	target: str
	value: ExprNode
	declare: Lit["let", "const"] | None = None
	op: str | None = None  # For augmented: +=, -=, etc.

	@override
	def emit(self, out: list[str]) -> None:
		if self.declare:
			out.append(self.declare)
			out.append(" ")
		out.append(self.target)
		if self.op:
			out.append(" ")
			out.append(self.op)
			out.append("= ")
		else:
			out.append(" = ")
		self.value.emit(out)
		out.append(";")


@dataclass(slots=True)
class ExprStmt(StmtNode):
	"""JS expression statement: expr;"""

	expr: ExprNode

	@override
	def emit(self, out: list[str]) -> None:
		self.expr.emit(out)
		out.append(";")


@dataclass(slots=True)
class Block(StmtNode):
	"""JS block: { ... } - a sequence of statements."""

	body: Sequence[StmtNode]

	@override
	def emit(self, out: list[str]) -> None:
		out.append("{\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")


@dataclass(slots=True)
class Throw(StmtNode):
	"""JS throw statement: throw expr;"""

	value: ExprNode

	@override
	def emit(self, out: list[str]) -> None:
		out.append("throw ")
		self.value.emit(out)
		out.append(";")


@dataclass(slots=True)
class Function(ExprNode):
	"""JS function: function name(params) { ... } or async function ...

	For statement-bodied functions. Use Arrow for expression-bodied.
	"""

	params: Sequence[str]
	body: Sequence[StmtNode]
	name: str | None = None
	is_async: bool = False

	@override
	def emit(self, out: list[str]) -> None:
		if self.is_async:
			out.append("async ")
		out.append("function")
		if self.name:
			out.append(" ")
			out.append(self.name)
		out.append("(")
		out.append(", ".join(self.params))
		out.append(") {\n")
		for stmt in self.body:
			stmt.emit(out)
			out.append("\n")
		out.append("}")


Child: TypeAlias = Primitive | ExprNode | PulseNode
Prop: TypeAlias = Primitive | ExprNode


# =============================================================================
# Emit logic
# =============================================================================


def emit(node: Node) -> str:
	"""Emit a node as JavaScript/JSX code."""
	out: list[str] = []
	node.emit(out)
	return "".join(out)


# Operator precedence table (higher = binds tighter)
_PRECEDENCE: dict[str, int] = {
	# Primary
	".": 20,
	"[]": 20,
	"()": 20,
	# Unary
	"!": 17,
	"+u": 17,
	"-u": 17,
	"typeof": 17,
	"await": 17,
	# Exponentiation (right-assoc)
	"**": 16,
	# Multiplicative
	"*": 15,
	"/": 15,
	"%": 15,
	# Additive
	"+": 14,
	"-": 14,
	# Relational
	"<": 12,
	"<=": 12,
	">": 12,
	">=": 12,
	"===": 12,
	"!==": 12,
	"instanceof": 12,
	"in": 12,
	# Logical
	"&&": 7,
	"||": 6,
	"??": 6,
	# Ternary
	"?:": 4,
	# Comma
	",": 1,
}

_RIGHT_ASSOC = {"**"}


def _escape_string(s: str) -> str:
	"""Escape for double-quoted JS string literals."""
	return (
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


def _escape_template(s: str) -> str:
	"""Escape for template literal strings."""
	return (
		s.replace("\\", "\\\\")
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


def _escape_jsx_text(s: str) -> str:
	"""Escape text content for JSX."""
	return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_jsx_attr(s: str) -> str:
	"""Escape attribute value for JSX."""
	return s.replace("&", "&amp;").replace('"', "&quot;")


def _emit_paren(node: ExprNode, parent_op: str, side: str, out: list[str]) -> None:
	"""Emit child with parens if needed for precedence."""
	# Ternary as child of binary always needs parens
	needs_parens = False
	if isinstance(node, Ternary):
		needs_parens = True
	else:
		child_prec = node.precedence()
		parent_prec = _PRECEDENCE.get(parent_op, 0)
		if child_prec < parent_prec:
			needs_parens = True
		elif child_prec == parent_prec and isinstance(node, Binary):
			# Handle associativity
			if parent_op in _RIGHT_ASSOC:
				needs_parens = side == "left"
			else:
				needs_parens = side == "right"

	if needs_parens:
		out.append("(")
		node.emit(out)
		out.append(")")
	else:
		node.emit(out)


def _emit_primary(node: ExprNode, out: list[str]) -> None:
	"""Emit with parens if not primary precedence."""
	if node.precedence() < 20 or isinstance(node, Ternary):
		out.append("(")
		node.emit(out)
		out.append(")")
	else:
		node.emit(out)


def _emit_value(value: Any, out: list[str]) -> None:
	"""Emit a Python value as JavaScript literal."""
	if value is None:
		out.append("null")
	elif isinstance(value, bool):
		out.append("true" if value else "false")
	elif isinstance(value, str):
		out.append('"')
		out.append(_escape_string(value))
		out.append('"')
	elif isinstance(value, (int, float)):
		out.append(str(value))
	elif isinstance(value, dt.datetime):
		out.append("new Date(")
		out.append(str(int(value.timestamp() * 1000)))
		out.append(")")
	elif isinstance(value, list):
		out.append("[")
		for i, v in enumerate(value):  # pyright: ignore[reportUnknownArgumentType]
			if i > 0:
				out.append(", ")
			_emit_value(v, out)
		out.append("]")
	elif isinstance(value, dict):
		out.append("{")
		for i, (k, v) in enumerate(value.items()):  # pyright: ignore[reportUnknownArgumentType]
			if i > 0:
				out.append(", ")
			out.append('"')
			out.append(_escape_string(str(k)))  # pyright: ignore[reportUnknownArgumentType]
			out.append('": ')
			_emit_value(v, out)
		out.append("}")
	elif isinstance(value, set):
		out.append("new Set([")
		for i, v in enumerate(value):  # pyright: ignore[reportUnknownArgumentType]
			if i > 0:
				out.append(", ")
			_emit_value(v, out)
		out.append("])")
	else:
		raise TypeError(f"Cannot emit {type(value).__name__} as JavaScript")


def _emit_jsx_prop(name: str, value: Prop, out: list[str]) -> None:
	"""Emit a single JSX prop."""
	# Spread props
	if isinstance(value, Spread):
		out.append("{...")
		value.expr.emit(out)
		out.append("}")
		return
	# Expression nodes
	if isinstance(value, ExprNode):
		# String literals can use compact form
		if isinstance(value, Literal) and isinstance(value.value, str):
			out.append(name)
			out.append('="')
			out.append(_escape_jsx_attr(value.value))
			out.append('"')
		else:
			out.append(name)
			out.append("={")
			value.emit(out)
			out.append("}")
		return
	# Primitives
	if value is None:
		out.append(name)
		out.append("={null}")
		return
	if isinstance(value, bool):
		out.append(name)
		out.append("={true}" if value else "={false}")
		return
	if isinstance(value, str):
		out.append(name)
		out.append('="')
		out.append(_escape_jsx_attr(value))
		out.append('"')
		return
	if isinstance(value, (int, float)):
		out.append(name)
		out.append("={")
		out.append(str(value))
		out.append("}")
		return
	# ValueNode
	if isinstance(value, ValueNode):
		out.append(name)
		out.append("={")
		_emit_value(value.value, out)
		out.append("}")
		return
	# Nested ElementNode (render prop)
	if isinstance(value, ElementNode):
		out.append(name)
		out.append("={")
		value.emit(out)
		out.append("}")
		return
	# Callable - error
	if callable(value):
		raise TypeError("Cannot emit callable in transpile context")
	# Fallback for other data
	out.append(name)
	out.append("={")
	_emit_value(value, out)
	out.append("}")


def _emit_jsx_child(child: Child, out: list[str]) -> None:
	"""Emit a single JSX child."""
	# Primitives
	if child is None or isinstance(child, bool):
		return  # React ignores None/bool
	if isinstance(child, str):
		out.append(_escape_jsx_text(child))
		return
	if isinstance(child, (int, float)):
		out.append("{")
		out.append(str(child))
		out.append("}")
		return
	if isinstance(child, dt.datetime):
		out.append("{")
		_emit_value(child, out)
		out.append("}")
		return
	# PulseNode - error
	if isinstance(child, PulseNode):
		fn_name = getattr(child.fn, "__name__", "unknown")
		raise TypeError(
			f"Cannot transpile PulseNode '{fn_name}'. "
			+ "Server components must be rendered, not transpiled."
		)
	# ElementNode - recurse
	if isinstance(child, ElementNode):
		child.emit(out)
		return
	# ExprNode
	if isinstance(child, ExprNode):
		out.append("{")
		child.emit(out)
		out.append("}")
		return
	# ValueNode
	if isinstance(child, ValueNode):
		out.append("{")
		_emit_value(child.value, out)
		out.append("}")
		return
	raise TypeError(f"Cannot emit {type(child).__name__} as JSX child")
