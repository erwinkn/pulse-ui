"""
Python -> JavaScript transpiler for pure functions.

Transpiles a restricted subset of Python into JavaScript. Handles:
- Pure functions (no global state mutation)
- Python syntax -> JS syntax conversion
- Python builtin functions -> JS equivalents
- Python builtin methods (str, list, dict, set) -> JS equivalents

This transpiler is designed for use with @javascript decorated functions.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable

from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.nodes import (
	ALLOWED_BINOPS,
	ALLOWED_CMPOPS,
	ALLOWED_UNOPS,
	JSArray,
	JSArrowFunction,
	JSAssign,
	JSAugAssign,
	JSBinary,
	JSBoolean,
	JSBreak,
	JSCall,
	JSConstAssign,
	JSContinue,
	JSExpr,
	JSForOf,
	JSFunctionDef,
	JSIdentifier,
	JSIf,
	JSLogicalChain,
	JSMember,
	JSMemberCall,
	JSMultiStmt,
	JSNew,
	JSNull,
	JSNumber,
	JSReturn,
	JSSingleStmt,
	JSSpread,
	JSStmt,
	JSString,
	JSSubscript,
	JSTemplate,
	JSTertiary,
	JSUnary,
	JSUndefined,
	JSWhile,
)


class JsTranspiler(ast.NodeVisitor):
	"""AST visitor that builds a JS AST from a restricted Python subset.

	The visitor receives a deps dictionary mapping names to JSExpr values.
	Behavior is encoded in JSExpr subclass hooks (emit_call, emit_getattr, emit_subscript).
	"""

	fndef: ast.FunctionDef
	args: list[str]
	deps: dict[str, JSExpr]
	locals: set[str]
	_temp_counter: int

	def __init__(
		self,
		fndef: ast.FunctionDef,
		args: list[str],
		deps: dict[str, JSExpr],
	) -> None:
		self.fndef = fndef
		self.args = args
		self.deps = deps
		# Track locals for declaration decisions (args are predeclared)
		self.locals = set(args)
		self._temp_counter = 0

	def _fresh_temp(self) -> str:
		"""Generate a fresh temporary variable name."""
		name = f"$tmp{self._temp_counter}"
		self._temp_counter += 1
		return name

	def _is_string_expr(self, expr: JSExpr) -> bool:
		"""Check if an expression is known to produce a string."""
		# Check common patterns that produce strings
		if isinstance(expr, JSString):
			return True
		if isinstance(expr, JSCall) and isinstance(expr.callee, JSIdentifier):
			return expr.callee.name == "String"
		if isinstance(expr, JSMemberCall):
			# Methods that return strings
			return expr.method in (
				"toFixed",
				"toExponential",
				"toString",
				"toUpperCase",
				"toLowerCase",
				"trim",
				"padStart",
				"padEnd",
			)
		return False

	# --- Entrypoint ---------------------------------------------------------
	def transpile(self, name: str | None = None) -> JSFunctionDef:
		"""Transpile the function definition to a JS function.

		Args:
			name: Optional function name to emit. If None, emits anonymous function.
		"""
		stmts: list[JSStmt] = []
		self._temp_counter = 0
		for i, stmt in enumerate(self.fndef.body):
			# Skip docstrings (first statement that's a string constant expression)
			if (
				i == 0
				and isinstance(stmt, ast.Expr)
				and isinstance(stmt.value, ast.Constant)
				and isinstance(stmt.value.value, str)
			):
				continue
			s = self.emit_stmt(stmt)
			stmts.append(s)
		return JSFunctionDef(self.args, stmts, name=name)

	# --- Statements ----------------------------------------------------------
	def emit_stmt(self, node: ast.stmt) -> JSStmt:
		"""Emit a statement."""
		if isinstance(node, ast.Return):
			return JSReturn(self.emit_expr(node.value))

		if isinstance(node, ast.Break):
			return JSBreak()

		if isinstance(node, ast.Continue):
			return JSContinue()

		if isinstance(node, ast.Pass):
			# Pass is a no-op, emit empty statement
			return JSMultiStmt([])

		if isinstance(node, ast.AugAssign):
			if not isinstance(node.target, ast.Name):
				raise JSCompilationError("Only simple augmented assignments supported")
			target = node.target.id
			op_type = type(node.op)
			if op_type not in ALLOWED_BINOPS:
				raise JSCompilationError(
					f"Unsupported augmented assignment operator: {op_type.__name__}"
				)
			value_expr = self.emit_expr(node.value)
			return JSAugAssign(target, ALLOWED_BINOPS[op_type], value_expr)

		if isinstance(node, ast.Assign):
			if len(node.targets) != 1:
				raise JSCompilationError(
					"Multiple assignment targets are not supported"
				)
			target_node = node.targets[0]

			# Tuple/list unpacking
			if isinstance(target_node, (ast.Tuple, ast.List)):
				return self._emit_unpacking_assign(target_node, node.value)

			if not isinstance(target_node, ast.Name):
				raise JSCompilationError(
					"Only simple assignments to local names are supported"
				)

			target = target_node.id
			value_expr = self.emit_expr(node.value)

			if target in self.locals:
				return JSAssign(target, value_expr, declare=False)
			else:
				self.locals.add(target)
				return JSAssign(target, value_expr, declare=True)

		if isinstance(node, ast.AnnAssign):
			if not isinstance(node.target, ast.Name):
				raise JSCompilationError("Only simple annotated assignments supported")
			target = node.target.id
			value = JSUndefined() if node.value is None else self.emit_expr(node.value)
			if target in self.locals:
				return JSAssign(target, value, declare=False)
			else:
				self.locals.add(target)
				return JSAssign(target, value, declare=True)

		if isinstance(node, ast.If):
			test = self.emit_expr(node.test)
			body = [self.emit_stmt(s) for s in node.body]
			orelse = [self.emit_stmt(s) for s in node.orelse]
			return JSIf(test, body, orelse)

		if isinstance(node, ast.Expr):
			return JSSingleStmt(self.emit_expr(node.value))

		if isinstance(node, ast.While):
			test = self.emit_expr(node.test)
			body = [self.emit_stmt(s) for s in node.body]
			return JSWhile(test, body)

		if isinstance(node, ast.For):
			return self._emit_for_loop(node)

		raise JSCompilationError(f"Unsupported statement: {type(node).__name__}")

	def _emit_unpacking_assign(
		self, target: ast.Tuple | ast.List, value: ast.expr
	) -> JSStmt:
		"""Emit unpacking assignment: a, b, c = expr"""
		elements = target.elts
		if not elements or not all(isinstance(e, ast.Name) for e in elements):
			raise JSCompilationError("Unpacking is only supported for simple variables")

		tmp_name = self._fresh_temp()
		value_expr = self.emit_expr(value)
		stmts: list[JSStmt] = [JSConstAssign(tmp_name, value_expr)]

		for idx, e in enumerate(elements):
			assert isinstance(e, ast.Name)
			name = e.id
			sub = JSSubscript(JSIdentifier(tmp_name), JSNumber(idx))
			if name in self.locals:
				stmts.append(JSAssign(name, sub, declare=False))
			else:
				self.locals.add(name)
				stmts.append(JSAssign(name, sub, declare=True))

		return JSMultiStmt(stmts)

	def _emit_for_loop(self, node: ast.For) -> JSStmt:
		"""Emit a for loop."""
		# Handle tuple unpacking in for target
		if isinstance(node.target, (ast.Tuple, ast.List)):
			names: list[str] = []
			for e in node.target.elts:
				if not isinstance(e, ast.Name):
					raise JSCompilationError(
						"Only simple name targets supported in for-loop unpacking"
					)
				names.append(e.id)
				self.locals.add(e.id)
			iter_expr = self.emit_expr(node.iter)
			body = [self.emit_stmt(s) for s in node.body]
			return JSForOf(names, iter_expr, body)

		if not isinstance(node.target, ast.Name):
			raise JSCompilationError("Only simple name targets supported in for-loops")

		target = node.target.id
		self.locals.add(target)
		iter_expr = self.emit_expr(node.iter)
		body = [self.emit_stmt(s) for s in node.body]
		return JSForOf(target, iter_expr, body)

	# --- Expressions ---------------------------------------------------------
	def emit_expr(self, node: ast.expr | None) -> JSExpr:
		"""Emit an expression."""
		if node is None:
			return JSUndefined()

		if isinstance(node, ast.Constant):
			return self._emit_constant(node)

		if isinstance(node, ast.Name):
			return self._emit_name(node)

		if isinstance(node, (ast.List, ast.Tuple)):
			return self._emit_list_or_tuple(node)

		if isinstance(node, ast.Dict):
			return self._emit_dict(node)

		if isinstance(node, ast.Set):
			return JSNew(
				JSIdentifier("Set"), [JSArray([self.emit_expr(e) for e in node.elts])]
			)

		if isinstance(node, ast.BinOp):
			return self._emit_binop(node)

		if isinstance(node, ast.UnaryOp):
			return self._emit_unaryop(node)

		if isinstance(node, ast.BoolOp):
			op = "&&" if isinstance(node.op, ast.And) else "||"
			return JSLogicalChain(op, [self.emit_expr(v) for v in node.values])

		if isinstance(node, ast.Compare):
			return self._emit_compare(node)

		if isinstance(node, ast.IfExp):
			test = self.emit_expr(node.test)
			body = self.emit_expr(node.body)
			orelse = self.emit_expr(node.orelse)
			return JSTertiary(test, body, orelse)

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
			return JSNew(JSIdentifier("Set"), [arr])

		if isinstance(node, ast.DictComp):
			pairs = self._emit_comprehension_chain(
				node.generators,
				lambda: JSArray([self.emit_expr(node.key), self.emit_expr(node.value)]),
			)
			return JSNew(JSIdentifier("Map"), [pairs])

		if isinstance(node, ast.Lambda):
			return self._emit_lambda(node)

		if isinstance(node, ast.Starred):
			return JSSpread(self.emit_expr(node.value))

		raise JSCompilationError(f"Unsupported expression: {type(node).__name__}")

	def _emit_constant(self, node: ast.Constant) -> JSExpr:
		"""Emit a constant value."""
		v = node.value
		if isinstance(v, str):
			# Use template literals for strings with Unicode line separators
			if "\u2028" in v or "\u2029" in v:
				return JSTemplate([v])
			return JSString(v)
		if v is None:
			return JSUndefined()
		if v is True:
			return JSBoolean(True)
		if v is False:
			return JSBoolean(False)
		if isinstance(v, (int, float)):
			return JSNumber(v)
		raise JSCompilationError(f"Unsupported constant type: {type(v).__name__}")

	def _emit_name(self, node: ast.Name) -> JSExpr:
		"""Emit a name reference.

		All dependencies are JSExpr subclasses. Behavior is encoded in hooks.
		"""
		name = node.id

		# Check deps first - all are JSExpr
		if name in self.deps:
			return self.deps[name]

		# Local variable
		if name in self.locals:
			return JSIdentifier(name)

		raise JSCompilationError(f"Unbound name referenced: {name}")

	def _emit_list_or_tuple(self, node: ast.List | ast.Tuple) -> JSExpr:
		"""Emit a list or tuple literal."""
		parts: list[JSExpr] = []
		for e in node.elts:
			if isinstance(e, ast.Starred):
				parts.append(JSSpread(self.emit_expr(e.value)))
			else:
				parts.append(self.emit_expr(e))
		return JSArray(parts)

	def _emit_dict(self, node: ast.Dict) -> JSExpr:
		"""Emit a dict literal as new Map([...])."""
		entries: list[JSExpr] = []
		for k, v in zip(node.keys, node.values, strict=False):
			if k is None:
				# Spread merge
				vexpr = self.emit_expr(v)
				is_map = JSBinary(vexpr, "instanceof", JSIdentifier("Map"))
				map_entries = JSMemberCall(vexpr, "entries", [])
				obj_entries = JSCall(
					JSMember(JSIdentifier("Object"), "entries"), [vexpr]
				)
				entries.append(JSSpread(JSTertiary(is_map, map_entries, obj_entries)))
				continue
			key_expr = self.emit_expr(k)
			val_expr = self.emit_expr(v)
			entries.append(JSArray([key_expr, val_expr]))
		return JSNew(JSIdentifier("Map"), [JSArray(entries)])

	def _emit_binop(self, node: ast.BinOp) -> JSExpr:
		"""Emit a binary operation."""
		op = type(node.op)
		if op not in ALLOWED_BINOPS:
			raise JSCompilationError(f"Unsupported binary operator: {op.__name__}")
		left = self.emit_expr(node.left)
		right = self.emit_expr(node.right)
		return JSBinary(left, ALLOWED_BINOPS[op], right)

	def _emit_unaryop(self, node: ast.UnaryOp) -> JSExpr:
		"""Emit a unary operation."""
		op = type(node.op)
		if op not in ALLOWED_UNOPS:
			raise JSCompilationError(f"Unsupported unary operator: {op.__name__}")
		return JSUnary(ALLOWED_UNOPS[op], self.emit_expr(node.operand))

	def _emit_compare(self, node: ast.Compare) -> JSExpr:
		"""Emit a comparison expression."""
		operands: list[ast.expr] = [node.left, *node.comparators]
		exprs: list[JSExpr] = [self.emit_expr(e) for e in operands]
		cmp_parts: list[JSExpr] = []

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
		return JSLogicalChain("&&", cmp_parts)

	def _build_comparison(
		self,
		left_expr: JSExpr,
		left_node: ast.expr,
		op: ast.cmpop,
		right_expr: JSExpr,
		right_node: ast.expr,
	) -> JSExpr:
		"""Build a single comparison."""
		# Identity comparisons
		if isinstance(op, (ast.Is, ast.IsNot)):
			is_not = isinstance(op, ast.IsNot)
			# Special case for None identity
			if (isinstance(right_node, ast.Constant) and right_node.value is None) or (
				isinstance(left_node, ast.Constant) and left_node.value is None
			):
				expr = right_expr if isinstance(left_node, ast.Constant) else left_expr
				return JSBinary(expr, "!=" if is_not else "==", JSNull())
			return JSBinary(left_expr, "!==" if is_not else "===", right_expr)

		# Membership tests
		if isinstance(op, (ast.In, ast.NotIn)):
			return self._build_membership_test(
				left_expr, right_expr, isinstance(op, ast.NotIn)
			)

		# Standard comparisons
		op_type = type(op)
		if op_type not in ALLOWED_CMPOPS:
			raise JSCompilationError(
				f"Unsupported comparison operator: {op_type.__name__}"
			)
		return JSBinary(left_expr, ALLOWED_CMPOPS[op_type], right_expr)

	def _build_membership_test(
		self, item: JSExpr, container: JSExpr, negate: bool
	) -> JSExpr:
		"""Build a membership test (in / not in)."""
		is_string = JSBinary(JSUnary("typeof", container), "===", JSString("string"))
		is_array = JSMemberCall(JSIdentifier("Array"), "isArray", [container])
		is_set = JSBinary(container, "instanceof", JSIdentifier("Set"))
		is_map = JSBinary(container, "instanceof", JSIdentifier("Map"))

		is_array_or_string = JSLogicalChain("||", [is_array, is_string])
		is_set_or_map = JSLogicalChain("||", [is_set, is_map])

		has_array_or_string = JSMemberCall(container, "includes", [item])
		has_set_or_map = JSMemberCall(container, "has", [item])
		has_obj = JSBinary(item, "in", container)

		membership_expr = JSTertiary(
			is_array_or_string,
			has_array_or_string,
			JSTertiary(is_set_or_map, has_set_or_map, has_obj),
		)

		if negate:
			return JSUnary("!", membership_expr)
		return membership_expr

	def _emit_call(self, node: ast.Call) -> JSExpr:
		"""Emit a function call.

		All behavior is encoded in JSExpr.emit_call hooks.
		"""
		# Handle typing.cast: ignore type argument, return value unchanged
		if isinstance(node.func, ast.Name) and node.func.id == "cast":
			if len(node.args) >= 2:
				return self.emit_expr(node.args[1])
			raise JSCompilationError("typing.cast requires two arguments")

		args = [self.emit_expr(a) for a in node.args]
		kwargs = self._build_kwargs(node)

		# Method call: obj.method(args) -> obj.emit_getattr(method).emit_call(args)
		if isinstance(node.func, ast.Attribute):
			obj = self.emit_expr(node.func.value)
			method_expr = obj.emit_getattr(node.func.attr)
			return method_expr.emit_call(args, kwargs)

		# Function call
		callee = self.emit_expr(node.func)
		return callee.emit_call(args, kwargs)

	def _build_kwargs(self, node: ast.Call) -> dict[str, JSExpr]:
		"""Build kwargs dict from AST Call node.

		Returns a dict mapping:
		- "propName" -> JSExpr for named kwargs
		- "$spread{N}" -> JSSpread(expr) for **spread kwargs

		Dict order is preserved (Python 3.7+), so iteration order matches source order.
		Uses $ prefix for spreads since it's not a valid Python identifier.
		"""
		kwargs: dict[str, JSExpr] = {}
		spread_count = 0

		for kw in node.keywords:
			if kw.arg is None:
				# **kwargs spread - use invalid Python identifier to avoid conflicts
				kwargs[f"$spread{spread_count}"] = JSSpread(self.emit_expr(kw.value))
				spread_count += 1
			else:
				kwargs[kw.arg] = self.emit_expr(kw.value)
		return kwargs

	def _emit_attribute(self, node: ast.Attribute) -> JSExpr:
		"""Emit an attribute access.

		All behavior is encoded in JSExpr.emit_getattr hooks.
		"""
		value = self.emit_expr(node.value)
		return value.emit_getattr(node.attr)

	def _emit_subscript(self, node: ast.Subscript) -> JSExpr:
		"""Emit a subscript expression."""
		value = self.emit_expr(node.value)

		# Slice handling (not passed through emit_subscript hook)
		if isinstance(node.slice, ast.Slice):
			return self._emit_slice(value, node.slice)

		# Negative index: use .at() (not passed through emit_subscript hook)
		if isinstance(node.slice, ast.UnaryOp) and isinstance(node.slice.op, ast.USub):
			idx_expr = self.emit_expr(node.slice.operand)
			return JSMemberCall(value, "at", [JSUnary("-", idx_expr)])

		# Collect indices - tuple means multiple indices like x[a, b, c]
		if isinstance(node.slice, ast.Tuple):
			indices = [self.emit_expr(e) for e in node.slice.elts]
		else:
			indices = [self.emit_expr(node.slice)]

		# Use emit_subscript hook for extensibility
		return value.emit_subscript(indices)

	def _emit_slice(self, value: JSExpr, slice_node: ast.Slice) -> JSExpr:
		"""Emit a slice operation."""
		if slice_node.step is not None:
			raise JSCompilationError("Slice steps are not supported")

		lower = slice_node.lower
		upper = slice_node.upper

		if lower is None and upper is None:
			return JSMemberCall(value, "slice", [])
		elif lower is None:
			return JSMemberCall(value, "slice", [JSNumber(0), self.emit_expr(upper)])
		elif upper is None:
			return JSMemberCall(value, "slice", [self.emit_expr(lower)])
		else:
			return JSMemberCall(
				value, "slice", [self.emit_expr(lower), self.emit_expr(upper)]
			)

	def _emit_fstring(self, node: ast.JoinedStr) -> JSExpr:
		"""Emit an f-string as a template literal."""
		parts: list[str | JSExpr] = []
		for part in node.values:
			if isinstance(part, ast.Constant) and isinstance(part.value, str):
				parts.append(part.value)
			elif isinstance(part, ast.FormattedValue):
				expr = self.emit_expr(part.value)
				# Handle conversion flags: !s, !r, !a
				if part.conversion == ord("s"):
					expr = JSCall(JSIdentifier("String"), [expr])
				elif part.conversion == ord("r"):
					expr = JSCall(JSMember(JSIdentifier("JSON"), "stringify"), [expr])
				elif part.conversion == ord("a"):
					# !a is ASCII repr - approximate with JSON.stringify
					expr = JSCall(JSMember(JSIdentifier("JSON"), "stringify"), [expr])
				# Handle format_spec (it's always a JoinedStr in practice)
				if part.format_spec is not None:
					if not isinstance(part.format_spec, ast.JoinedStr):
						raise JSCompilationError("Format spec must be a JoinedStr")
					expr = self._apply_format_spec(expr, part.format_spec)
				parts.append(expr)
			else:
				raise JSCompilationError(
					f"Unsupported f-string component: {type(part).__name__}"
				)
		return JSTemplate(parts)

	def _apply_format_spec(self, expr: JSExpr, format_spec: ast.JoinedStr) -> JSExpr:
		"""Apply a Python format spec to an expression.

		Supports common format specs:
		- .Nf: N decimal places (float) -> .toFixed(N)
		- 0Nd: zero-padded integer, width N -> String(...).padStart(N, '0')
		- >N: right-align, width N -> String(...).padStart(N)
		- <N: left-align, width N -> String(...).padEnd(N)
		- ^N: center, width N -> custom centering
		- #x, #o, #b: hex/octal/binary with prefix
		- +.Nf: with sign prefix
		"""
		# Extract the format spec string (it's a JoinedStr but usually just one constant)
		if len(format_spec.values) != 1:
			raise JSCompilationError("Dynamic format specs not supported")
		spec_part = format_spec.values[0]
		if not isinstance(spec_part, ast.Constant) or not isinstance(
			spec_part.value, str
		):
			raise JSCompilationError("Dynamic format specs not supported")

		spec = spec_part.value
		return self._parse_and_apply_format(expr, spec)

	def _parse_and_apply_format(self, expr: JSExpr, spec: str) -> JSExpr:
		"""Parse a format spec string and apply it to expr."""
		if not spec:
			return expr

		# Parse Python format spec: [[fill]align][sign][#][0][width][,][.precision][type]
		pattern = r"^([^<>=^]?[<>=^])?([+\- ])?([#])?(0)?(\d+)?([,_])?(\.(\d+))?([bcdeEfFgGnosxX%])?$"
		match = re.match(pattern, spec)
		if not match:
			raise JSCompilationError(f"Unsupported format spec: {spec!r}")

		align_part = match.group(1) or ""
		sign = match.group(2) or ""
		alt_form = match.group(3)  # '#'
		zero_pad = match.group(4)  # '0'
		width_str = match.group(5)
		# thousands_sep = match.group(6)  # ',' or '_' - not commonly needed
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
			# Float with precision
			prec = precision if precision is not None else 6
			expr = JSMemberCall(expr, "toFixed", [JSNumber(prec)])
			if sign == "+":
				# Add sign prefix for positive numbers
				expr = JSTertiary(
					JSBinary(expr, ">=", JSNumber(0)),
					JSBinary(JSString("+"), "+", expr),
					expr,
				)
		elif type_char == "d":
			# Integer - convert to string for padding (only if we need padding later)
			if width is not None:
				expr = JSCall(JSIdentifier("String"), [expr])
		elif type_char == "x":
			# Hex lowercase
			base_expr = JSMemberCall(expr, "toString", [JSNumber(16)])
			if alt_form:
				expr = JSBinary(JSString("0x"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "X":
			# Hex uppercase
			base_expr = JSMemberCall(
				JSMemberCall(expr, "toString", [JSNumber(16)]), "toUpperCase", []
			)
			if alt_form:
				expr = JSBinary(JSString("0x"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "o":
			# Octal
			base_expr = JSMemberCall(expr, "toString", [JSNumber(8)])
			if alt_form:
				expr = JSBinary(JSString("0o"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "b":
			# Binary
			base_expr = JSMemberCall(expr, "toString", [JSNumber(2)])
			if alt_form:
				expr = JSBinary(JSString("0b"), "+", base_expr)
			else:
				expr = base_expr
		elif type_char == "e":
			# Exponential notation lowercase
			prec = precision if precision is not None else 6
			expr = JSMemberCall(expr, "toExponential", [JSNumber(prec)])
		elif type_char == "E":
			# Exponential notation uppercase
			prec = precision if precision is not None else 6
			expr = JSMemberCall(
				JSMemberCall(expr, "toExponential", [JSNumber(prec)]), "toUpperCase", []
			)
		elif type_char == "s" or type_char == "":
			# String - convert to string if not already
			if type_char == "s" or (width is not None and align):
				expr = JSCall(JSIdentifier("String"), [expr])

		# Apply width/padding
		if width is not None:
			fill_str = JSString(fill)
			width_num = JSNumber(width)

			if zero_pad and not align:
				# Zero padding (e.g., 05d) - pad start with zeros
				# If expr is not already a string, wrap it
				if not self._is_string_expr(expr):
					expr = JSCall(JSIdentifier("String"), [expr])
				expr = JSMemberCall(
					expr,
					"padStart",
					[width_num, JSString("0")],
				)
			elif align == "<":
				# Left align -> padEnd
				expr = JSMemberCall(expr, "padEnd", [width_num, fill_str])
			elif align == ">":
				# Right align -> padStart
				expr = JSMemberCall(expr, "padStart", [width_num, fill_str])
			elif align == "^":
				# Center align - needs custom logic
				# JS: s.padStart((width + s.length) / 2).padEnd(width)
				expr = JSMemberCall(
					JSMemberCall(
						expr,
						"padStart",
						[
							JSBinary(
								JSBinary(
									JSBinary(width_num, "+", JSMember(expr, "length")),
									"/",
									JSNumber(2),
								),
								"|",
								JSNumber(0),
							),
							fill_str,
						],
					),
					"padEnd",
					[width_num, fill_str],
				)
			elif align == "=":
				# Pad after sign - not commonly used, treat as right align
				expr = JSMemberCall(expr, "padStart", [width_num, fill_str])
			elif zero_pad:
				# Just 0N without explicit align means zero-pad from start
				expr = JSMemberCall(
					JSCall(JSIdentifier("String"), [expr]),
					"padStart",
					[width_num, JSString("0")],
				)

		return expr

	def _emit_lambda(self, node: ast.Lambda) -> JSExpr:
		"""Emit a lambda expression as an arrow function."""
		# Get parameter names
		params = [arg.arg for arg in node.args.args]
		# Add params to locals temporarily
		saved_locals = set(self.locals)
		self.locals.update(params)

		body = self.emit_expr(node.body)

		self.locals = saved_locals

		if len(params) == 0:
			return JSArrowFunction("()", body)
		elif len(params) == 1:
			return JSArrowFunction(params[0], body)
		else:
			return JSArrowFunction(f"({', '.join(params)})", body)

	def _emit_comprehension_chain(
		self,
		generators: list[ast.comprehension],
		build_last: Callable[[], JSExpr],
	) -> JSExpr:
		"""Build a flatMap/map chain for comprehensions."""
		if len(generators) == 0:
			raise JSCompilationError("Empty comprehension")

		saved_locals = set(self.locals)

		def build_chain(gen_index: int) -> JSExpr:
			gen = generators[gen_index]
			if gen.is_async:
				raise JSCompilationError("Async comprehensions are not supported")

			iter_expr = self.emit_expr(gen.iter)
			# Get arrow function parameter code and variable names from a target
			if isinstance(gen.target, ast.Name):
				param_code = gen.target.id
				names = [gen.target.id]
			elif isinstance(gen.target, ast.Tuple) and all(
				isinstance(e, ast.Name) for e in gen.target.elts
			):
				names = [e.id for e in gen.target.elts if isinstance(e, ast.Name)]
				param_code = f"([{', '.join(names)}])"
			else:
				raise JSCompilationError(
					"Only name or tuple targets supported in comprehensions"
				)
			for nm in names:
				self.locals.add(nm)

			base = iter_expr

			# Apply filters
			if gen.ifs:
				conds = [self.emit_expr(test) for test in gen.ifs]
				cond = JSLogicalChain("&&", conds) if len(conds) > 1 else conds[0]
				base = JSMemberCall(base, "filter", [JSArrowFunction(param_code, cond)])

			is_last = gen_index == len(generators) - 1
			if is_last:
				elt_expr = build_last()
				return JSMemberCall(
					base, "map", [JSArrowFunction(param_code, elt_expr)]
				)

			inner = build_chain(gen_index + 1)
			return JSMemberCall(base, "flatMap", [JSArrowFunction(param_code, inner)])

		try:
			return build_chain(0)
		finally:
			self.locals = saved_locals
