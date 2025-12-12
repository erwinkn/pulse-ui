"""
Python -> JavaScript transpiler using v2 nodes.

Transpiles a restricted subset of Python into a v2 Node AST.
Dependencies are resolved through a dict[str, Node] mapping.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from typing import Any

from pulse.transpiler_v2.builtins import BUILTINS, emit_method
from pulse.transpiler_v2.nodes import (
	Array,
	Arrow,
	Assign,
	Binary,
	Block,
	Break,
	Call,
	Continue,
	ExprNode,
	ExprStmt,
	ForOf,
	Function,
	Identifier,
	If,
	Literal,
	Member,
	Return,
	Spread,
	StmtNode,
	Subscript,
	Template,
	Ternary,
	Unary,
	While,
)

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


class TranspileError(Exception):
	"""Error during transpilation."""


class Transpiler:
	"""Transpile Python AST to v2 Node AST.

	Takes a function definition and a dictionary of dependencies.
	Dependencies are substituted when their names are referenced.

	Dependencies are ExprNode instances. ExprNode subclasses can override:
	- emit_call: custom call behavior (e.g., JSX components)
	- emit_getattr: custom attribute access
	- emit_subscript: custom subscript behavior
	"""

	fndef: ast.FunctionDef | ast.AsyncFunctionDef
	args: list[str]
	deps: Mapping[str, ExprNode]
	locals: set[str]
	_temp_counter: int

	def __init__(
		self,
		fndef: ast.FunctionDef | ast.AsyncFunctionDef,
		deps: Mapping[str, ExprNode],
	) -> None:
		self.fndef = fndef
		self.args = [arg.arg for arg in fndef.args.args]
		self.deps = deps
		self.locals = set(self.args)
		self._temp_counter = 0
		self.init_temp_counter()

	def init_temp_counter(self) -> None:
		"""Initialize temp counter to avoid collisions with args or globals."""
		all_names = set(self.args) | set(self.deps.keys())
		counter = 0
		while f"$tmp{counter}" in all_names:
			counter += 1
		self._temp_counter = counter

	def _fresh_temp(self) -> str:
		"""Generate a fresh temporary variable name."""
		name = f"$tmp{self._temp_counter}"
		self._temp_counter += 1
		return name

	# --- Entrypoint ---------------------------------------------------------

	def transpile(self) -> Function | Arrow:
		"""Transpile the function to a Function or Arrow node.

		For single-expression functions (or single return), produces Arrow:
			(params) => expr

		For multi-statement functions, produces Function:
			function(params) { ... }
		"""
		body = self.fndef.body

		# Skip docstrings
		if (
			body
			and isinstance(body[0], ast.Expr)
			and isinstance(body[0].value, ast.Constant)
			and isinstance(body[0].value.value, str)
		):
			body = body[1:]

		if not body:
			return Arrow(self.args, Literal(None))

		# Single expression or return statement -> expression-bodied arrow
		if len(body) == 1:
			stmt = body[0]
			if isinstance(stmt, ast.Return):
				expr = self.emit_expr(stmt.value)
				return Arrow(self.args, expr)
			if isinstance(stmt, ast.Expr):
				expr = self.emit_expr(stmt.value)
				return Arrow(self.args, expr)

		# Multi-statement: emit as Function
		stmts = [self.emit_stmt(s) for s in body]
		is_async = isinstance(self.fndef, ast.AsyncFunctionDef)
		return Function(self.args, stmts, is_async=is_async)

	# --- Statements ----------------------------------------------------------

	def emit_stmt(self, node: ast.stmt) -> StmtNode:
		"""Emit a statement."""
		if isinstance(node, ast.Return):
			value = self.emit_expr(node.value) if node.value else None
			return Return(value)

		if isinstance(node, ast.Break):
			return Break()

		if isinstance(node, ast.Continue):
			return Continue()

		if isinstance(node, ast.Pass):
			# Pass is a no-op, emit empty block
			return Block([])

		if isinstance(node, ast.AugAssign):
			if not isinstance(node.target, ast.Name):
				raise TranspileError("Only simple augmented assignments supported")
			target = node.target.id
			op_type = type(node.op)
			if op_type not in ALLOWED_BINOPS:
				raise TranspileError(
					f"Unsupported augmented assignment operator: {op_type.__name__}"
				)
			value_expr = self.emit_expr(node.value)
			return Assign(target, value_expr, op=ALLOWED_BINOPS[op_type])

		if isinstance(node, ast.Assign):
			if len(node.targets) != 1:
				raise TranspileError("Multiple assignment targets not supported")
			target_node = node.targets[0]

			# Tuple/list unpacking
			if isinstance(target_node, (ast.Tuple, ast.List)):
				return self._emit_unpacking_assign(target_node, node.value)

			if not isinstance(target_node, ast.Name):
				raise TranspileError("Only simple assignments to local names supported")

			target = target_node.id
			value_expr = self.emit_expr(node.value)

			if target in self.locals:
				return Assign(target, value_expr)
			else:
				self.locals.add(target)
				return Assign(target, value_expr, declare="let")

		if isinstance(node, ast.AnnAssign):
			if not isinstance(node.target, ast.Name):
				raise TranspileError("Only simple annotated assignments supported")
			target = node.target.id
			value = Literal(None) if node.value is None else self.emit_expr(node.value)
			if target in self.locals:
				return Assign(target, value)
			else:
				self.locals.add(target)
				return Assign(target, value, declare="let")

		if isinstance(node, ast.If):
			cond = self.emit_expr(node.test)
			then = [self.emit_stmt(s) for s in node.body]
			else_ = [self.emit_stmt(s) for s in node.orelse]
			return If(cond, then, else_)

		if isinstance(node, ast.Expr):
			expr = self.emit_expr(node.value)
			return ExprStmt(expr)

		if isinstance(node, ast.While):
			cond = self.emit_expr(node.test)
			body = [self.emit_stmt(s) for s in node.body]
			return While(cond, body)

		if isinstance(node, ast.For):
			return self._emit_for_loop(node)

		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			return self._emit_nested_function(node)

		raise TranspileError(f"Unsupported statement: {type(node).__name__}")

	def _emit_unpacking_assign(
		self, target: ast.Tuple | ast.List, value: ast.expr
	) -> StmtNode:
		"""Emit unpacking assignment: a, b, c = expr"""
		elements = target.elts
		if not elements or not all(isinstance(e, ast.Name) for e in elements):
			raise TranspileError("Unpacking only supported for simple variables")

		tmp_name = self._fresh_temp()
		value_expr = self.emit_expr(value)
		stmts: list[StmtNode] = [Assign(tmp_name, value_expr, declare="const")]

		for idx, e in enumerate(elements):
			assert isinstance(e, ast.Name)
			name = e.id
			sub = Subscript(Identifier(tmp_name), Literal(idx))
			if name in self.locals:
				stmts.append(Assign(name, sub))
			else:
				self.locals.add(name)
				stmts.append(Assign(name, sub, declare="let"))

		return Block(stmts)

	def _emit_for_loop(self, node: ast.For) -> StmtNode:
		"""Emit a for loop."""
		# Handle tuple unpacking in for target
		if isinstance(node.target, (ast.Tuple, ast.List)):
			names: list[str] = []
			for e in node.target.elts:
				if not isinstance(e, ast.Name):
					raise TranspileError(
						"Only simple name targets supported in for-loop unpacking"
					)
				names.append(e.id)
				self.locals.add(e.id)
			iter_expr = self.emit_expr(node.iter)
			body = [self.emit_stmt(s) for s in node.body]
			# Use array pattern for destructuring
			target = f"[{', '.join(names)}]"
			return ForOf(target, iter_expr, body)

		if not isinstance(node.target, ast.Name):
			raise TranspileError("Only simple name targets supported in for-loops")

		target = node.target.id
		self.locals.add(target)
		iter_expr = self.emit_expr(node.iter)
		body = [self.emit_stmt(s) for s in node.body]
		return ForOf(target, iter_expr, body)

	def _emit_nested_function(
		self, node: ast.FunctionDef | ast.AsyncFunctionDef
	) -> StmtNode:
		"""Emit a nested function definition."""
		name = node.name
		params = [arg.arg for arg in node.args.args]

		# Save current locals and extend with params
		saved_locals = set(self.locals)
		self.locals.update(params)

		# Skip docstrings and emit body
		body_stmts = node.body
		if (
			body_stmts
			and isinstance(body_stmts[0], ast.Expr)
			and isinstance(body_stmts[0].value, ast.Constant)
			and isinstance(body_stmts[0].value.value, str)
		):
			body_stmts = body_stmts[1:]

		stmts: list[StmtNode] = [self.emit_stmt(s) for s in body_stmts]

		# Restore outer locals and add function name
		self.locals = saved_locals
		self.locals.add(name)

		is_async = isinstance(node, ast.AsyncFunctionDef)
		fn = Function(params, stmts, is_async=is_async)
		return Assign(name, fn, declare="const")

	# --- Expressions ---------------------------------------------------------

	def emit_expr(self, node: ast.expr | None) -> ExprNode:
		"""Emit an expression."""
		if node is None:
			return Literal(None)

		if isinstance(node, ast.Constant):
			return self._emit_constant(node)

		if isinstance(node, ast.Name):
			return self._emit_name(node)

		if isinstance(node, (ast.List, ast.Tuple)):
			return self._emit_list_or_tuple(node)

		if isinstance(node, ast.Dict):
			return self._emit_dict(node)

		if isinstance(node, ast.Set):
			return Call(
				Identifier("Set"),
				[Array([self.emit_expr(e) for e in node.elts])],
			)

		if isinstance(node, ast.BinOp):
			return self._emit_binop(node)

		if isinstance(node, ast.UnaryOp):
			return self._emit_unaryop(node)

		if isinstance(node, ast.BoolOp):
			return self._emit_boolop(node)

		if isinstance(node, ast.Compare):
			return self._emit_compare(node)

		if isinstance(node, ast.IfExp):
			return Ternary(
				self.emit_expr(node.test),
				self.emit_expr(node.body),
				self.emit_expr(node.orelse),
			)

		if isinstance(node, ast.Call):
			return self._emit_call(node)

		if isinstance(node, ast.Attribute):
			return self._emit_attribute(node)

		if isinstance(node, ast.Subscript):
			return self._emit_subscript(node)

		if isinstance(node, ast.JoinedStr):
			return self._emit_fstring(node)

		if isinstance(node, ast.ListComp):
			return self._emit_comprehension_chain(
				node.generators, lambda: self.emit_expr(node.elt)
			)

		if isinstance(node, ast.GeneratorExp):
			return self._emit_comprehension_chain(
				node.generators, lambda: self.emit_expr(node.elt)
			)

		if isinstance(node, ast.SetComp):
			arr = self._emit_comprehension_chain(
				node.generators, lambda: self.emit_expr(node.elt)
			)
			return Call(Identifier("Set"), [arr])

		if isinstance(node, ast.DictComp):
			pairs = self._emit_comprehension_chain(
				node.generators,
				lambda: Array([self.emit_expr(node.key), self.emit_expr(node.value)]),
			)
			return Call(Identifier("Map"), [pairs])

		if isinstance(node, ast.Lambda):
			return self._emit_lambda(node)

		if isinstance(node, ast.Starred):
			return Spread(self.emit_expr(node.value))

		if isinstance(node, ast.Await):
			return Unary("await", self.emit_expr(node.value))

		raise TranspileError(f"Unsupported expression: {type(node).__name__}")

	def _emit_constant(self, node: ast.Constant) -> ExprNode:
		"""Emit a constant value."""
		v = node.value
		if isinstance(v, str):
			# Use template literals for strings with Unicode line separators
			if "\u2028" in v or "\u2029" in v:
				return Template([v])
			return Literal(v)
		if v is None:
			return Literal(None)
		if isinstance(v, bool):
			return Literal(v)
		if isinstance(v, (int, float)):
			return Literal(v)
		raise TranspileError(f"Unsupported constant type: {type(v).__name__}")

	def _emit_name(self, node: ast.Name) -> ExprNode:
		"""Emit a name reference."""
		name = node.id

		# Check deps first
		if name in self.deps:
			return self.deps[name]

		# Local variable
		if name in self.locals:
			return Identifier(name)

		# Check builtins
		if name in BUILTINS:
			return BUILTINS[name]

		raise TranspileError(f"Unbound name referenced: {name}")

	def _emit_list_or_tuple(self, node: ast.List | ast.Tuple) -> ExprNode:
		"""Emit a list or tuple literal."""
		parts: list[ExprNode] = []
		for e in node.elts:
			if isinstance(e, ast.Starred):
				parts.append(Spread(self.emit_expr(e.value)))
			else:
				parts.append(self.emit_expr(e))
		return Array(parts)

	def _emit_dict(self, node: ast.Dict) -> ExprNode:
		"""Emit a dict literal as new Map([...])."""
		entries: list[ExprNode] = []
		for k, v in zip(node.keys, node.values, strict=False):
			if k is None:
				# Spread merge
				vexpr = self.emit_expr(v)
				is_map = Binary(vexpr, "instanceof", Identifier("Map"))
				map_entries = Call(Member(vexpr, "entries"), [])
				obj_entries = Call(Member(Identifier("Object"), "entries"), [vexpr])
				entries.append(Spread(Ternary(is_map, map_entries, obj_entries)))
				continue
			key_expr = self.emit_expr(k)
			val_expr = self.emit_expr(v)
			entries.append(Array([key_expr, val_expr]))
		return Call(Identifier("Map"), [Array(entries)])

	def _emit_binop(self, node: ast.BinOp) -> ExprNode:
		"""Emit a binary operation."""
		op = type(node.op)
		if op not in ALLOWED_BINOPS:
			raise TranspileError(f"Unsupported binary operator: {op.__name__}")
		left = self.emit_expr(node.left)
		right = self.emit_expr(node.right)
		return Binary(left, ALLOWED_BINOPS[op], right)

	def _emit_unaryop(self, node: ast.UnaryOp) -> ExprNode:
		"""Emit a unary operation."""
		op = type(node.op)
		if op not in ALLOWED_UNOPS:
			raise TranspileError(f"Unsupported unary operator: {op.__name__}")
		return Unary(ALLOWED_UNOPS[op], self.emit_expr(node.operand))

	def _emit_boolop(self, node: ast.BoolOp) -> ExprNode:
		"""Emit a boolean operation (and/or chain)."""
		op = "&&" if isinstance(node.op, ast.And) else "||"
		values = [self.emit_expr(v) for v in node.values]
		# Build binary chain: a && b && c -> Binary(Binary(a, &&, b), &&, c)
		result = values[0]
		for v in values[1:]:
			result = Binary(result, op, v)
		return result

	def _emit_compare(self, node: ast.Compare) -> ExprNode:
		"""Emit a comparison expression."""
		operands: list[ast.expr] = [node.left, *node.comparators]
		exprs: list[ExprNode] = [self.emit_expr(e) for e in operands]
		cmp_parts: list[ExprNode] = []

		for i, op in enumerate(node.ops):
			left_node = operands[i]
			right_node = operands[i + 1]
			left_expr = exprs[i]
			right_expr = exprs[i + 1]
			cmp_parts.append(
				self._build_comparison(left_expr, left_node, op, right_expr, right_node)
			)

		if len(cmp_parts) == 1:
			return cmp_parts[0]

		# Chain with &&
		result = cmp_parts[0]
		for v in cmp_parts[1:]:
			result = Binary(result, "&&", v)
		return result

	def _build_comparison(
		self,
		left_expr: ExprNode,
		left_node: ast.expr,
		op: ast.cmpop,
		right_expr: ExprNode,
		right_node: ast.expr,
	) -> ExprNode:
		"""Build a single comparison."""
		# Identity comparisons
		if isinstance(op, (ast.Is, ast.IsNot)):
			is_not = isinstance(op, ast.IsNot)
			# Special case for None identity
			if (isinstance(right_node, ast.Constant) and right_node.value is None) or (
				isinstance(left_node, ast.Constant) and left_node.value is None
			):
				expr = right_expr if isinstance(left_node, ast.Constant) else left_expr
				return Binary(expr, "!=" if is_not else "==", Literal(None))
			return Binary(left_expr, "!==" if is_not else "===", right_expr)

		# Membership tests
		if isinstance(op, (ast.In, ast.NotIn)):
			return self._build_membership_test(
				left_expr, right_expr, isinstance(op, ast.NotIn)
			)

		# Standard comparisons
		op_type = type(op)
		if op_type not in ALLOWED_CMPOPS:
			raise TranspileError(f"Unsupported comparison operator: {op_type.__name__}")
		return Binary(left_expr, ALLOWED_CMPOPS[op_type], right_expr)

	def _build_membership_test(
		self, item: ExprNode, container: ExprNode, negate: bool
	) -> ExprNode:
		"""Build a membership test (in / not in)."""
		is_string = Binary(Unary("typeof", container), "===", Literal("string"))
		is_array = Call(Member(Identifier("Array"), "isArray"), [container])
		is_set = Binary(container, "instanceof", Identifier("Set"))
		is_map = Binary(container, "instanceof", Identifier("Map"))

		is_array_or_string = Binary(is_array, "||", is_string)
		is_set_or_map = Binary(is_set, "||", is_map)

		has_array_or_string = Call(Member(container, "includes"), [item])
		has_set_or_map = Call(Member(container, "has"), [item])
		has_obj = Binary(item, "in", container)

		membership_expr = Ternary(
			is_array_or_string,
			has_array_or_string,
			Ternary(is_set_or_map, has_set_or_map, has_obj),
		)

		if negate:
			return Unary("!", membership_expr)
		return membership_expr

	def _emit_call(self, node: ast.Call) -> ExprNode:
		"""Emit a function call."""
		# Resolve callee to ExprNode
		callee = self.emit_expr(node.func)

		# Collect args and kwargs as raw AST values
		args_raw = list(node.args)
		kwargs_raw: dict[str, Any] = {}
		for kw in node.keywords:
			if kw.arg is None:
				raise TranspileError(
					"Spread props (**kwargs) not yet supported in v2 transpiler"
				)
			kwargs_raw[kw.arg] = kw.value

		# Try custom emit_call on the callee
		try:
			return callee.emit_call(args_raw, kwargs_raw, self)
		except NotImplementedError:
			pass

		# Emit args
		args: list[ExprNode] = [self.emit_expr(a) for a in args_raw]

		# Emit kwargs
		kwargs: dict[str, ExprNode] = {
			k: self.emit_expr(v) for k, v in kwargs_raw.items()
		}

		# Method call: obj.method(args) - try builtin method dispatch
		if isinstance(node.func, ast.Attribute):
			obj = self.emit_expr(node.func.value)
			method = node.func.attr

			# Try builtin method handling with runtime checks
			result = emit_method(obj, method, args, kwargs)
			if result is not None:
				return result

			# Default method call - kwargs not supported for unknown methods
			if kwargs:
				raise TranspileError(
					f"Keyword arguments not supported for method '{method}'"
				)
			# IMPORTANT: derive callee via emit_getattr so non-emittable module refs work.
			return Call(obj.emit_getattr(method, self), args)

		# Function call - kwargs not supported
		if kwargs:
			raise TranspileError("Keyword arguments not yet supported in v2 transpiler")
		return Call(callee, args)

	def _emit_attribute(self, node: ast.Attribute) -> ExprNode:
		"""Emit an attribute access."""
		value = self.emit_expr(node.value)
		# Delegate to ExprNode.emit_getattr (default returns Member)
		return value.emit_getattr(node.attr, self)

	def _emit_subscript(self, node: ast.Subscript) -> ExprNode:
		"""Emit a subscript expression."""
		value = self.emit_expr(node.value)

		# Slice handling
		if isinstance(node.slice, ast.Slice):
			return self._emit_slice(value, node.slice)

		# Negative index: use .at()
		if isinstance(node.slice, ast.UnaryOp) and isinstance(node.slice.op, ast.USub):
			idx_expr = self.emit_expr(node.slice.operand)
			return Call(Member(value, "at"), [Unary("-", idx_expr)])

		# Standard subscript
		if isinstance(node.slice, ast.Tuple):
			# Multiple indices not typically supported in JS
			raise TranspileError("Multiple indices not supported in subscript")

		# Delegate to ExprNode.emit_subscript (default returns Subscript)
		return value.emit_subscript(node.slice, self)

	def _emit_slice(self, value: ExprNode, slice_node: ast.Slice) -> ExprNode:
		"""Emit a slice operation."""
		if slice_node.step is not None:
			raise TranspileError("Slice steps are not supported")

		lower = slice_node.lower
		upper = slice_node.upper

		if lower is None and upper is None:
			return Call(Member(value, "slice"), [])
		elif lower is None:
			return Call(Member(value, "slice"), [Literal(0), self.emit_expr(upper)])
		elif upper is None:
			return Call(Member(value, "slice"), [self.emit_expr(lower)])
		else:
			return Call(
				Member(value, "slice"), [self.emit_expr(lower), self.emit_expr(upper)]
			)

	def _emit_fstring(self, node: ast.JoinedStr) -> ExprNode:
		"""Emit an f-string as a template literal."""
		parts: list[str | ExprNode] = []
		for part in node.values:
			if isinstance(part, ast.Constant) and isinstance(part.value, str):
				parts.append(part.value)
			elif isinstance(part, ast.FormattedValue):
				expr = self.emit_expr(part.value)
				# Handle conversion flags: !s, !r, !a
				if part.conversion == ord("s"):
					expr = Call(Identifier("String"), [expr])
				elif part.conversion == ord("r"):
					expr = Call(Member(Identifier("JSON"), "stringify"), [expr])
				elif part.conversion == ord("a"):
					expr = Call(Member(Identifier("JSON"), "stringify"), [expr])
				# Handle format_spec
				if part.format_spec is not None:
					if not isinstance(part.format_spec, ast.JoinedStr):
						raise TranspileError("Format spec must be a JoinedStr")
					expr = self._apply_format_spec(expr, part.format_spec)
				parts.append(expr)
			else:
				raise TranspileError(
					f"Unsupported f-string component: {type(part).__name__}"
				)
		return Template(parts)

	def _apply_format_spec(
		self, expr: ExprNode, format_spec: ast.JoinedStr
	) -> ExprNode:
		"""Apply a Python format spec to an expression."""
		if len(format_spec.values) != 1:
			raise TranspileError("Dynamic format specs not supported")
		spec_part = format_spec.values[0]
		if not isinstance(spec_part, ast.Constant) or not isinstance(
			spec_part.value, str
		):
			raise TranspileError("Dynamic format specs not supported")

		spec = spec_part.value
		return self._parse_and_apply_format(expr, spec)

	def _parse_and_apply_format(self, expr: ExprNode, spec: str) -> ExprNode:
		"""Parse a format spec string and apply it to expr."""
		if not spec:
			return expr

		# Parse Python format spec
		pattern = r"^([^<>=^]?[<>=^])?([+\- ])?([#])?(0)?(\d+)?([,_])?(\.(\d+))?([bcdeEfFgGnosxX%])?$"
		match = re.match(pattern, spec)
		if not match:
			raise TranspileError(f"Unsupported format spec: {spec!r}")

		align_part = match.group(1) or ""
		sign = match.group(2) or ""
		alt_form = match.group(3)
		zero_pad = match.group(4)
		width_str = match.group(5)
		precision_str = match.group(8)
		type_char = match.group(9) or ""

		width = int(width_str) if width_str else None
		precision = int(precision_str) if precision_str else None

		# Determine fill and alignment
		if len(align_part) == 2:
			fill = align_part[0]
			align = align_part[1]
		elif len(align_part) == 1:
			fill = " "
			align = align_part[0]
		else:
			fill = " "
			align = ""

		# Handle type conversions first
		if type_char in ("f", "F"):
			prec = precision if precision is not None else 6
			expr = Call(Member(expr, "toFixed"), [Literal(prec)])
			if sign == "+":
				expr = Ternary(
					Binary(expr, ">=", Literal(0)),
					Binary(Literal("+"), "+", expr),
					expr,
				)
		elif type_char == "d":
			if width is not None:
				expr = Call(Identifier("String"), [expr])
		elif type_char == "x":
			base_expr = Call(Member(expr, "toString"), [Literal(16)])
			if alt_form:
				expr = Binary(Literal("0x"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "X":
			base_expr = Call(
				Member(Call(Member(expr, "toString"), [Literal(16)]), "toUpperCase"), []
			)
			if alt_form:
				expr = Binary(Literal("0x"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "o":
			base_expr = Call(Member(expr, "toString"), [Literal(8)])
			if alt_form:
				expr = Binary(Literal("0o"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "b":
			base_expr = Call(Member(expr, "toString"), [Literal(2)])
			if alt_form:
				expr = Binary(Literal("0b"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "e":
			prec = precision if precision is not None else 6
			expr = Call(Member(expr, "toExponential"), [Literal(prec)])
		elif type_char == "E":
			prec = precision if precision is not None else 6
			expr = Call(
				Member(
					Call(Member(expr, "toExponential"), [Literal(prec)]), "toUpperCase"
				),
				[],
			)
		elif type_char == "s" or type_char == "":
			if type_char == "s" or (width is not None and align):
				expr = Call(Identifier("String"), [expr])

		# Apply width/padding
		if width is not None:
			fill_str = Literal(fill)
			width_num = Literal(width)

			if zero_pad and not align:
				expr = Call(
					Member(Call(Identifier("String"), [expr]), "padStart"),
					[width_num, Literal("0")],
				)
			elif align == "<":
				expr = Call(Member(expr, "padEnd"), [width_num, fill_str])
			elif align == ">":
				expr = Call(Member(expr, "padStart"), [width_num, fill_str])
			elif align == "^":
				# Center align
				expr = Call(
					Member(
						Call(
							Member(expr, "padStart"),
							[
								Binary(
									Binary(
										Binary(width_num, "+", Member(expr, "length")),
										"/",
										Literal(2),
									),
									"|",
									Literal(0),
								),
								fill_str,
							],
						),
						"padEnd",
					),
					[width_num, fill_str],
				)
			elif align == "=":
				expr = Call(Member(expr, "padStart"), [width_num, fill_str])
			elif zero_pad:
				expr = Call(
					Member(Call(Identifier("String"), [expr]), "padStart"),
					[width_num, Literal("0")],
				)

		return expr

	def _emit_lambda(self, node: ast.Lambda) -> ExprNode:
		"""Emit a lambda expression as an arrow function."""
		params = [arg.arg for arg in node.args.args]

		# Add params to locals temporarily
		saved_locals = set(self.locals)
		self.locals.update(params)

		body = self.emit_expr(node.body)

		self.locals = saved_locals

		return Arrow(params, body)

	def _emit_comprehension_chain(
		self,
		generators: list[ast.comprehension],
		build_last: Callable[[], ExprNode],
	) -> ExprNode:
		"""Build a flatMap/map chain for comprehensions."""
		if len(generators) == 0:
			raise TranspileError("Empty comprehension")

		saved_locals = set(self.locals)

		def build_chain(gen_index: int) -> ExprNode:
			gen = generators[gen_index]
			if gen.is_async:
				raise TranspileError("Async comprehensions are not supported")

			iter_expr = self.emit_expr(gen.iter)

			# Get parameter and variable names from target
			if isinstance(gen.target, ast.Name):
				params = [gen.target.id]
				names = [gen.target.id]
			elif isinstance(gen.target, ast.Tuple) and all(
				isinstance(e, ast.Name) for e in gen.target.elts
			):
				names = [e.id for e in gen.target.elts if isinstance(e, ast.Name)]
				# For destructuring, use array pattern as single param: [a, b]
				params = [f"[{', '.join(names)}]"]
			else:
				raise TranspileError(
					"Only name or tuple targets supported in comprehensions"
				)

			for nm in names:
				self.locals.add(nm)

			base = iter_expr

			# Apply filters
			if gen.ifs:
				conds = [self.emit_expr(test) for test in gen.ifs]
				cond = conds[0]
				for c in conds[1:]:
					cond = Binary(cond, "&&", c)
				base = Call(Member(base, "filter"), [Arrow(params, cond)])

			is_last = gen_index == len(generators) - 1
			if is_last:
				elt_expr = build_last()
				return Call(Member(base, "map"), [Arrow(params, elt_expr)])

			inner = build_chain(gen_index + 1)
			return Call(Member(base, "flatMap"), [Arrow(params, inner)])

		try:
			return build_chain(0)
		finally:
			self.locals = saved_locals


def transpile(
	fndef: ast.FunctionDef | ast.AsyncFunctionDef,
	deps: Mapping[str, ExprNode] | None = None,
) -> Function | Arrow:
	"""Transpile a Python function to a v2 Function or Arrow node.

	Args:
		fndef: The function definition AST node
		deps: Dictionary mapping global names to ExprNode instances

	Returns:
		Arrow for single-expression functions, Function for multi-statement
	"""
	return Transpiler(fndef, deps or {}).transpile()
