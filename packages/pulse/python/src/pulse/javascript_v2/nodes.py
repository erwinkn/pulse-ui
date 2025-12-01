from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, override

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
	@abstractmethod
	def emit(self) -> str:
		raise NotImplementedError


class JSExpr(JSNode, ABC):
	pass


class JSStmt(JSNode, ABC):
	pass


@dataclass
class JSIdentifier(JSExpr):
	name: str

	@override
	def emit(self) -> str:
		return self.name


@dataclass
class JSString(JSExpr):
	value: Any

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


@dataclass
class JSNumber(JSExpr):
	value: float

	@override
	def emit(self) -> str:
		return str(self.value)


@dataclass
class JSBoolean(JSExpr):
	value: bool

	@override
	def emit(self) -> str:
		return "true" if self.value else "false"


@dataclass
class JSNull(JSExpr):
	@override
	def emit(self) -> str:
		return "null"


@dataclass
class JSUndefined(JSExpr):
	@override
	def emit(self) -> str:
		return "undefined"


@dataclass
class JSArray(JSExpr):
	elements: Sequence[JSExpr]

	@override
	def emit(self) -> str:
		inner = ", ".join(e.emit() for e in self.elements)
		return f"[{inner}]"


@dataclass
class JSSpread(JSExpr):
	expr: JSExpr

	@override
	def emit(self) -> str:
		return f"...{self.expr.emit()}"


@dataclass
class JSProp(JSExpr):
	key: JSString
	value: JSExpr

	@override
	def emit(self) -> str:
		return f"{self.key.emit()}: {self.value.emit()}"


@dataclass
class JSComputedProp(JSExpr):
	key: JSExpr
	value: JSExpr

	@override
	def emit(self) -> str:
		return f"[{self.key.emit()}]: {self.value.emit()}"


@dataclass
class JSObjectExpr(JSExpr):
	props: Sequence[JSProp | JSComputedProp | JSSpread]

	@override
	def emit(self) -> str:
		inner = ", ".join(p.emit() for p in self.props)
		return "{" + inner + "}"


@dataclass
class JSUnary(JSExpr):
	op: str  # '-', '+', '!'
	operand: JSExpr

	@override
	def emit(self) -> str:
		operand_code = _emit_child_for_binary_like(
			self.operand, parent_op=self.op, side="unary"
		)
		if self.op == "typeof":
			return f"typeof {operand_code}"
		return f"{self.op}{operand_code}"


@dataclass
class JSBinary(JSExpr):
	left: JSExpr
	op: str
	right: JSExpr

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


@dataclass
class JSLogicalChain(JSExpr):
	op: str  # '&&' or '||'
	values: Sequence[JSExpr]

	# TODO: parenthesizing
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


@dataclass
class JSTertiary(JSExpr):
	test: JSExpr
	if_true: JSExpr
	if_false: JSExpr

	@override
	def emit(self) -> str:
		return f"{self.test.emit()} ? {self.if_true.emit()} : {self.if_false.emit()}"


@dataclass
class JSFunctionDef(JSExpr):
	params: Sequence[str]
	body: Sequence[JSStmt]

	@override
	def emit(self) -> str:
		params = ", ".join(self.params)
		body_code = "\n".join(s.emit() for s in self.body)
		return f"function({params}){{\n{body_code}\n}}"


@dataclass
class JSTemplate(JSExpr):
	# parts are either raw strings (literal text) or JSExpr instances which are
	# emitted inside ${...}
	parts: Sequence[str | JSExpr]

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


@dataclass
class JSMember(JSExpr):
	obj: JSExpr
	prop: str

	@override
	def emit(self) -> str:
		obj_code = _emit_child_for_primary(self.obj)
		return f"{obj_code}.{self.prop}"


@dataclass
class JSSubscript(JSExpr):
	obj: JSExpr
	index: JSExpr

	@override
	def emit(self) -> str:
		obj_code = _emit_child_for_primary(self.obj)
		return f"{obj_code}[{self.index.emit()}]"


@dataclass
class JSCall(JSExpr):
	callee: JSExpr  # typically JSIdentifier
	args: Sequence[JSExpr]

	@override
	def emit(self) -> str:
		fn = _emit_child_for_primary(self.callee)
		return f"{fn}({', '.join(a.emit() for a in self.args)})"


@dataclass
class JSMemberCall(JSExpr):
	obj: JSExpr
	method: str
	args: Sequence[JSExpr]

	@override
	def emit(self) -> str:
		obj_code = _emit_child_for_primary(self.obj)
		return f"{obj_code}.{self.method}({', '.join(a.emit() for a in self.args)})"


@dataclass
class JSNew(JSExpr):
	ctor: JSExpr
	args: Sequence[JSExpr]

	@override
	def emit(self) -> str:
		ctor_code = _emit_child_for_primary(self.ctor)
		return f"new {ctor_code}({', '.join(a.emit() for a in self.args)})"


@dataclass
class JSArrowFunction(JSExpr):
	params_code: str  # already formatted e.g. 'x' or '(a, b)' or '([k, v])'
	body: JSExpr | JSBlock

	@override
	def emit(self) -> str:
		return f"{self.params_code} => {self.body.emit()}"


@dataclass
class JSComma(JSExpr):
	values: Sequence[JSExpr]

	@override
	def emit(self) -> str:
		# Always wrap comma expressions in parentheses to avoid precedence surprises
		inner = ", ".join(v.emit() for v in self.values)
		return f"({inner})"


@dataclass
class JSReturn(JSStmt):
	value: JSExpr

	@override
	def emit(self) -> str:
		return f"return {self.value.emit()};"


@dataclass
class JSAssign(JSStmt):
	name: str
	value: JSExpr
	declare: bool = False  # when True emit 'let name = ...'

	@override
	def emit(self) -> str:
		if self.declare:
			return f"let {self.name} = {self.value.emit()};"
		return f"{self.name} = {self.value.emit()};"


@dataclass
class JSRaw(JSExpr):
	content: str

	@override
	def emit(self) -> str:
		return self.content


###############################################################################
# JSX AST (minimal)
###############################################################################


def _check_not_interpreted_mode(node_type: str) -> None:
	"""Raise an error if we're in interpreted mode - JSX can't be eval'd."""
	from pulse.javascript_v2.context import is_interpreted_mode

	if is_interpreted_mode():
		raise ValueError(
			f"{node_type} cannot be used in interpreted mode (as a prop or child value). "
			"JSX syntax requires transpilation and cannot be evaluated at runtime. "
			"Use standard VDOM elements (ps.div, ps.span, etc.) instead."
		)


def _escape_jsx_text(text: str) -> str:
	# Minimal escaping for text nodes
	return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class JSXProp(JSExpr):
	name: str
	value: JSExpr | None = None

	@override
	def emit(self) -> str:
		_check_not_interpreted_mode("JSXProp")
		if self.value is None:
			return self.name
		# Prefer compact string literal attribute when possible
		if isinstance(self.value, JSString):
			return f"{self.name}={self.value.emit()}"
		return self.name + "={" + self.value.emit() + "}"


@dataclass
class JSXSpreadProp(JSExpr):
	value: JSExpr

	@override
	def emit(self) -> str:
		_check_not_interpreted_mode("JSXSpreadProp")
		return f"{{...{self.value.emit()}}}"


@dataclass
class JSXElement(JSExpr):
	tag: str | JSExpr
	props: Sequence[JSXProp | JSXSpreadProp] = tuple()
	children: Sequence[str | JSExpr | "JSXElement"] = tuple()

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
			elif isinstance(c, JSXElement):
				child_parts.append(c.emit())
			else:
				child_parts.append("{" + c.emit() + "}")
		inner = "".join(child_parts)
		return f"{open_tag}{inner}</{tag_code}>"


@dataclass
class JSXFragment(JSExpr):
	children: Sequence[str | JSExpr | JSXElement] = tuple()

	@override
	def emit(self) -> str:
		_check_not_interpreted_mode("JSXFragment")
		if not self.children:
			return "<></>"
		parts: list[str] = []
		for c in self.children:
			if isinstance(c, str):
				parts.append(_escape_jsx_text(c))
			elif isinstance(c, JSXElement):
				parts.append(c.emit())
			else:
				parts.append("{" + c.emit() + "}")
		return "<>" + "".join(parts) + "</>"


@dataclass
class JSImport:
	src: str
	default: str | None = None
	# Either the name or (name, alias)
	named: list[str | tuple[str, str]] = field(default_factory=list)

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
	if op == "typeof":
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
	from pulse.javascript_v2.imports import Import

	if isinstance(e, JSBinary):
		return op_precedence(e.op)
	if isinstance(e, JSUnary):
		# Distinguish unary + and - from binary precedence table by tag
		tag = "+u" if e.op == "+" else ("-u" if e.op == "-" else e.op)
		return op_precedence(tag)
	if isinstance(e, JSTertiary):
		return op_precedence("?:")
	if isinstance(e, JSLogicalChain):
		return op_precedence(e.op)
	if isinstance(e, JSComma):
		return op_precedence(",")
	# Nullish now represented as JSBinary with op "??"; precedence resolved below
	if isinstance(e, (JSMember, JSSubscript, JSCall, JSMemberCall, JSNew)):
		return op_precedence(".")
	# Treat primitives and containers as primary
	if isinstance(
		e,
		(
			JSIdentifier,
			JSString,
			JSNumber,
			JSBoolean,
			JSNull,
			JSUndefined,
			JSArray,
			JSObjectExpr,
			JSTemplate,
			JSRaw,
			JSXElement,
			JSXFragment,
			Import,
		),
	):
		return PRIMARY_PRECEDENCE
	return 0


@dataclass
class JSBlock(JSStmt):
	body: Sequence[JSStmt]

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		return f"{{\n{body_code}\n}}"


@dataclass
class JSAugAssign(JSStmt):
	name: str
	op: str
	value: JSExpr

	@override
	def emit(self) -> str:
		return f"{self.name} {self.op}= {self.value.emit()};"


@dataclass
class JSConstAssign(JSStmt):
	name: str
	value: JSExpr

	@override
	def emit(self) -> str:
		return f"const {self.name} = {self.value.emit()};"


@dataclass
class JSSingleStmt(JSStmt):
	expr: JSExpr

	@override
	def emit(self) -> str:
		return f"{self.expr.emit()};"


@dataclass
class JSMultiStmt(JSStmt):
	stmts: Sequence[JSStmt]

	@override
	def emit(self) -> str:
		return "\n".join(s.emit() for s in self.stmts)


@dataclass
class JSIf(JSStmt):
	test: JSExpr
	body: Sequence[JSStmt]
	orelse: Sequence[JSStmt]

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		if not self.orelse:
			return f"if ({self.test.emit()}){{\n{body_code}\n}}"
		else_code = "\n".join(s.emit() for s in self.orelse)
		return f"if ({self.test.emit()}){{\n{body_code}\n}} else {{\n{else_code}\n}}"


@dataclass
class JSForOf(JSStmt):
	target: str | list[str]
	iter_expr: JSExpr
	body: Sequence[JSStmt]

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		target = self.target
		if not isinstance(target, str):
			target = f"[{', '.join(x for x in target)}]"
		return f"for (const {target} of {self.iter_expr.emit()}){{\n{body_code}\n}}"


@dataclass
class JSWhile(JSStmt):
	test: JSExpr
	body: Sequence[JSStmt]

	@override
	def emit(self) -> str:
		body_code = "\n".join(s.emit() for s in self.body)
		return f"while ({self.test.emit()}){{\n{body_code}\n}}"


class JSBreak(JSStmt):
	@override
	def emit(self) -> str:
		return "break;"


class JSContinue(JSStmt):
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


def to_js_expr(value: object) -> JSExpr:
	"""Convert a Python value to a JSExpr.

	Handles:
	- JSExpr: returned as-is
	- Import (including CssModule): wrapped in _ImportExpr
	- str: JSString
	- int/float: JSNumber
	- bool: JSBoolean
	- None: JSNull
	- list/tuple: JSArray (recursively converted)
	- dict: JSObjectExpr (recursively converted)
	"""
	# Already a JSExpr
	if isinstance(value, JSExpr):
		return value

	# Primitives
	if isinstance(value, str):
		return JSString(value)
	if isinstance(value, bool):  # Must check before int since bool is subclass of int
		return JSBoolean(value)
	if isinstance(value, (int, float)):
		return JSNumber(value)
	if value is None:
		return JSNull()

	# Collections
	if isinstance(value, (list, tuple)):
		return JSArray([to_js_expr(v) for v in value])
	if isinstance(value, dict):
		props = [JSProp(JSString(str(k)), to_js_expr(v)) for k, v in value.items()]
		return JSObjectExpr(props)

	raise TypeError(f"Cannot convert {type(value).__name__} to JSExpr")
