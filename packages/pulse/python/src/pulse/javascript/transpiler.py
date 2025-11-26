"""
Minimal AST-to-JS transpiler for a restricted, pure subset of Python used to
define synchronous JavaScript callbacks in the Pulse UI runtime.

The goal is to translate small Python functions into compact
JavaScript functions that can be inlined on the client where a sync
callback is required (e.g., chart formatters, sorters, small mappers).

The subset of the language supported is intended to be:
- Primitives (int, float, str, bool, datetime, None) and their methods
- Lists, tuples, sets, dicts, their constructor, their expressions, and their methods
- Core statements: return, if, elif, else, for, while, break, continue,
- Unary and binary operations, assignments, `in` operator
- Collections unpacking and comprehensions
- F-strings and the formatting mini-language
- Print (converted to console.log)
- Arbitrary JS objects with property access, method calling, and unpacking
- Lambdas (necessary for certain operations like filter, map, etc...)
- Built-in functions like `min`, `max`, `any`, `filter`, `sorted`
- Math module (later)
- Helpers, like deep equality (later)

The `@javascript` decorator compiles a function at definition-time and stores
metadata on the Python callable so the reconciler can send the compiled code to
the client.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from typing import Any, Callable, cast

from pulse.javascript.format_spec import _apply_format_spec, _extract_formatspec_str

from .builtins import (
	BUILTINS,
	Builtin,
	BuiltinMethods,
	DictMethods,
	ListMethods,
	SetMethods,
	StringMethods,
)
from .nodes import (
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
	JSCompilationError,
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

###############################################################################
# Python AST -> JS AST
###############################################################################


class JsTranspiler(ast.NodeVisitor):
	"""AST visitor that builds a JS AST from a restricted Python subset.

	The visitor can be provided with:
	- predeclared: names that are already declared in the current scope (e.g.,
	  parameters). These will not be re-declared with 'let' on first assignment.
	- ref_table: mapping from Python identifier -> JSExpr to inline/rename
	  non-local/global references resolved by the orchestrator.
	"""

	def __init__(
		self,
		fndef: ast.FunctionDef,
		args: list[str],
		globals: list[str],
		builtins: dict[str, Builtin],
		rename: dict[str, str],
		module_builtins: dict[str, dict[str, Builtin]] | None = None,
	) -> None:
		self.fndef = fndef
		self.args = args
		self.globals = globals
		self.builtins = builtins
		self.rename = rename
		self.module_builtins = module_builtins or {}

		self.predeclared: set[str] = set(args) | set(globals)
		# Track locals for declaration decisions
		self.locals: set[str] = set(self.predeclared)
		self._lines: list[str] = []
		self._temp_counter: int = 0

	# -----------------------------
	# Builtin replacement helpers
	# -----------------------------

	def _build_function_call(self, node: ast.Call) -> JSExpr:
		# typing.cast: ignore first type argument and return the value unchanged
		if isinstance(node.func, ast.Name) and node.func.id == "cast":
			if len(node.args) >= 2:
				return self.emit_expr(node.args[1])
			raise JSCompilationError("typing.cast requires two arguments")
		args = [self.emit_expr(a) for a in node.args]
		# Build kw_map as JSExprs
		kwargs: dict[str, JSExpr] = {}
		for kw in node.keywords:
			if kw.arg is None:
				raise JSCompilationError("**kwargs not supported")
			kwargs[kw.arg] = self.emit_expr(kw.value)
		# Prefer declared/renamed identifiers over builtins to avoid collisions (e.g., svg tag 'g')
		if isinstance(node.func, ast.Name):
			ident = node.func.id
			if ident in self.rename or ident in self.locals:
				callee = self.emit_expr(node.func)
				if kwargs:
					raise JSCompilationError(
						"Keyword arguments are not supported for function calls (except Python builtins)"
					)
				return JSCall(callee, args)
		# Resolve builtins (only works for direct references)
		if isinstance(node.func, ast.Name) and node.func.id in self.builtins:
			return self.builtins[node.func.id](*args, **kwargs)

		# Generic path: allow any expression as callee, e.g. (a + b)(1)
		callee = self.emit_expr(node.func)
		if kwargs:
			raise JSCompilationError(
				"Keyword arguments are not supported for function calls (except Python builtins)"
			)
		return JSCall(callee, args)

	def _build_method_call(
		self,
		attr: str,
		obj: JSExpr,
		args: list[JSExpr],
	) -> JSExpr:
		# Generic dispatchers for known types
		expr = JSMemberCall(obj, attr, args)
		# Fast-path: if receiver is a known literal (string or array), apply
		# the specialized method directly without runtime type checks.
		if isinstance(obj, (JSString, JSTemplate)):
			if attr not in StringMethods.__methods__():
				raise JSCompilationError(f"Unsupported string method: {attr}")
			try:
				direct = getattr(StringMethods(obj), attr)(*args)
			except TypeError as e:
				raise JSCompilationError(
					f"Invalid arguments for string method '{attr}': {e}"
				) from e
			if direct is None:
				return expr
			return direct
		if isinstance(obj, JSArray):
			if attr not in ListMethods.__methods__():
				raise JSCompilationError(f"Unsupported list method: {attr}")
			try:
				direct = getattr(ListMethods(obj), attr)(*args)
			except TypeError as e:
				raise JSCompilationError(
					f"Invalid arguments for list method '{attr}': {e}"
				) from e
			if direct is None:
				return expr
			return direct
		# Fast-path: new Set(...) and new Map(...) constructors are known types
		if isinstance(obj, JSNew) and isinstance(obj.ctor, JSIdentifier):
			if obj.ctor.name == "Set":
				if attr not in SetMethods.__methods__():
					raise JSCompilationError(f"Unsupported set method: {attr}")
				try:
					direct = getattr(SetMethods(obj), attr)(*args)
				except TypeError as e:
					raise JSCompilationError(
						f"Invalid arguments for set method '{attr}': {e}"
					) from e
				if direct is None:
					return expr
				return direct
			if obj.ctor.name == "Map":
				if attr not in DictMethods.__methods__():
					raise JSCompilationError(f"Unsupported dict method: {attr}")
				try:
					direct = getattr(DictMethods(obj), attr)(*args)
				except TypeError as e:
					raise JSCompilationError(
						f"Invalid arguments for dict method '{attr}': {e}"
					) from e
				if direct is None:
					return expr
				return direct
		# Apply in increasing priority so that later (higher priority) wrappers
		# end up outermost in the final expression. We prefer string/list
		# semantics first, then set, then dict, to better match common Python
		# expectations for overlapping method names like pop/copy.
		builtins: list[type[BuiltinMethods]] = [
			DictMethods,
			SetMethods,
			ListMethods,
			StringMethods,
		]
		for cls in builtins:
			if attr in cls.__methods__():
				try:
					instance = cls(obj)
					dispatch_expr = getattr(instance, attr)(*args)
					if dispatch_expr is not None:
						expr = JSTertiary(
							cls.__runtime_check__(obj), dispatch_expr, expr
						)
				except TypeError:
					pass
		return expr

	# -----------------------------
	# JSX helpers (namespaced builtins via module alias)
	# -----------------------------

	def _attempt_jsx_call(self, node: ast.Call) -> JSExpr | None:
		# Detect ps.tag(...)
		if isinstance(node.func, ast.Attribute) and isinstance(
			node.func.value, ast.Name
		):
			mod_alias = node.func.value.id
			if mod_alias in self.module_builtins:
				attr = node.func.attr
				builtins_for_mod = self.module_builtins[mod_alias]
				if attr in builtins_for_mod:
					args = [self.emit_expr(a) for a in node.args]
					# Preserve props order and support **spread via ordered meta list
					ordered_props: list[
						tuple[str, str, JSExpr] | tuple[str, JSExpr]
					] = []
					plain_kwargs: dict[str, JSExpr] = {}
					for kw in node.keywords:
						if kw.arg is None:
							# **kwargs spread
							ordered_props.append(("spread", self.emit_expr(kw.value)))
						else:
							val = self.emit_expr(kw.value)
							ordered_props.append(("named", kw.arg, val))
							plain_kwargs[kw.arg] = val
					# Pass ordered list for JSX while also providing plain kwargs as fallback
					return builtins_for_mod[attr](
						*args, __ordered_props__=ordered_props, **plain_kwargs
					)
		return None

	def _attempt_jsx_subscript(self, node: ast.Subscript) -> JSExpr | None:
		# Detect ps.tag(...)[children]
		if (
			isinstance(node.value, ast.Call)
			and isinstance(node.value.func, ast.Attribute)
			and isinstance(node.value.func.value, ast.Name)
		):
			mod_alias = node.value.func.value.id
			attr = node.value.func.attr
			if (
				mod_alias in self.module_builtins
				and attr in self.module_builtins[mod_alias]
			):
				# Collect original call args/kwargs (children/props)
				base_args = [self.emit_expr(a) for a in node.value.args]
				base_kwargs: dict[str, JSExpr] = {}
				ordered_props: list[tuple[str, str, JSExpr] | tuple[str, JSExpr]] = []
				for kw in node.value.keywords:
					if kw.arg is None:
						ordered_props.append(("spread", self.emit_expr(kw.value)))
					else:
						val = self.emit_expr(kw.value)
						ordered_props.append(("named", kw.arg, val))
						base_kwargs[kw.arg] = val
				# Collect bracket-children from subscript slice
				slice_node = node.slice
				child_nodes: list[ast.expr] = []
				if isinstance(slice_node, ast.Tuple):
					child_nodes.extend(cast(list[ast.expr], slice_node.elts))
				elif isinstance(slice_node, ast.List):
					child_nodes.extend(cast(list[ast.expr], slice_node.elts))
				else:
					child_nodes.append(cast(ast.expr, slice_node))
				extra_children: list[JSExpr] = []
				for ch in child_nodes:
					if isinstance(ch, ast.Starred):
						extra_children.append(JSSpread(self.emit_expr(ch.value)))
					else:
						extra_children.append(self.emit_expr(ch))
				all_children = base_args + extra_children
				builtin_fn = self.module_builtins[mod_alias][attr]
				base_kwargs["__ordered_props__"] = ordered_props  # type: ignore[assignment]
				return builtin_fn(*all_children, **base_kwargs)
		return None

	def _arrow_param_from_target(self, target: ast.expr) -> tuple[str, list[str]]:
		if isinstance(target, ast.Name):
			return target.id, [target.id]
		if isinstance(target, ast.Tuple) and all(
			isinstance(e, ast.Name) for e in target.elts
		):
			names = [cast(ast.Name, e).id for e in target.elts]
			return f"([{', '.join(names)}])", names
		raise JSCompilationError(
			"Only name or 2-tuple targets supported in comprehensions"
		)

	def _build_comprehension_chain(
		self, generators: list[ast.comprehension], build_last: Callable[[], JSExpr]
	) -> JSExpr:
		"""Build a left-to-right flatMap/map chain for Python comprehensions.

		The provided build_last callback is invoked when the recursion reaches
		the innermost generator, and must return the mapped element expression
		(e.g., the `elt` for list/set comps or the `[key, value]` pair for
		dict comps). This helper snapshots and restores local scope so that
		comprehension-target variables do not leak to the outer scope.
		"""
		if len(generators) == 0:
			raise JSCompilationError("Empty comprehension")

		saved_locals = set(self.locals)

		def build_chain(gen_index: int) -> JSExpr:
			gen = generators[gen_index]
			if gen.is_async:
				raise JSCompilationError("Async comprehensions are not supported")
			iter_expr = self.emit_expr(gen.iter)
			param_code, names = self._arrow_param_from_target(gen.target)
			for nm in names:
				self.locals.add(nm)
			base: JSExpr = iter_expr
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

	# --- Entrypoints ---------------------------------------------------------
	def transpile(self) -> JSFunctionDef:
		stmts: list[JSStmt] = []
		# Reset temp counter per function emission
		self._temp_counter = 0
		for stmt in self.fndef.body:
			s = self.emit_stmt(stmt)
			if s is None:
				continue
			stmts.append(s)
		# Function expression
		return JSFunctionDef(self.args, stmts)

	# --- Statements ----------------------------------------------------------
	def emit_stmt(self, node: ast.stmt) -> JSStmt:
		"""Supported statements:
		- return
		- break
		- continue
		- assign (regular and augmented)
		- if, elif, else
		- for (iterables only)
		- while
		- regular expr
		"""
		if isinstance(node, ast.Return):
			return JSReturn(self.emit_expr(node.value))
		if isinstance(node, ast.Break):
			return JSBreak()
		if isinstance(node, ast.Continue):
			return JSContinue()
		if isinstance(node, ast.AugAssign):
			if not isinstance(node.target, ast.Name):
				raise JSCompilationError("Only simple augmented assignments supported.")
			target = _mangle_identifier(node.target.id)
			# Support only whitelisted binary ops via mapping
			op_type = type(node.op)
			if op_type not in ALLOWED_BINOPS:
				raise JSCompilationError("AugAssign operator not allowed")
			value_expr = self.emit_expr(node.value)
			return JSAugAssign(target, ALLOWED_BINOPS[op_type], value_expr)
		if isinstance(node, ast.Assign):
			if len(node.targets) != 1:
				raise JSCompilationError(
					"Multiple assignment targets are not supported"
				)
			target_node = node.targets[0]
			# Tuple/list unpacking of flat names only
			if isinstance(target_node, (ast.Tuple, ast.List)):
				elements = target_node.elts
				if not elements or not all(isinstance(e, ast.Name) for e in elements):
					raise JSCompilationError(
						"Unpacking is supported only for simple variables. Example: `a, b, c = [x for x in range(3)]`."
					)
				tmp_name = f"$tmp{self._temp_counter}"
				self._temp_counter += 1
				value_expr = self.emit_expr(node.value)
				stmts: list[JSStmt] = [
					JSConstAssign(tmp_name, value_expr),
				]
				for idx, e in enumerate(elements):
					name = cast(ast.Name, e).id
					ident = _mangle_identifier(name)
					index_expr = JSNumber(idx)
					sub = JSSubscript(JSIdentifier(tmp_name), index_expr)
					if name in self.locals:
						stmts.append(JSAssign(ident, sub, declare=False))
					else:
						self.locals.add(name)
						stmts.append(JSAssign(ident, sub, declare=True))
				return JSMultiStmt(stmts)
			if not isinstance(target_node, ast.Name):
				raise JSCompilationError(
					"Only simple assignments to local names are supported."
				)
			target = target_node.id
			target_ident = _mangle_identifier(target)
			value_expr = self.emit_expr(node.value)
			# Use 'let' only on first assignment to a local name. Parameters
			# are considered locals from the start and thus won't be re-declared.
			if target in self.locals:
				return JSAssign(target_ident, value_expr, declare=False)
			else:
				self.locals.add(target)
				return JSAssign(target_ident, value_expr, declare=True)
		if isinstance(node, ast.AnnAssign):
			if not isinstance(node.target, ast.Name):
				raise JSCompilationError("Only simple annotated assignments supported.")
			target = node.target.id
			target_ident = _mangle_identifier(target)
			value = JSNull() if node.value is None else self.emit_expr(node.value)
			if target in self.locals:
				return JSAssign(target_ident, value, declare=False)
			else:
				self.locals.add(target)
				return JSAssign(target_ident, value, declare=True)
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
			# orelse on Python while isn't supported; ignore if present (empty expected)
			return JSWhile(test, body)
		if isinstance(node, ast.For):
			# Only "for name in <iter>" supported
			if not isinstance(node.target, ast.Name):
				raise JSCompilationError(
					"Only simple name targets supported in for-loops"
				)
			target_ident = _mangle_identifier(node.target.id)
			# Loop variable is a new local; declare inside loop via const in JSForOf
			# (No redeclaration tracking needed as 'const' is per-iteration variable)
			# Track as local so references in the body are not considered freevars.
			self.locals.add(node.target.id)
			iter_expr = self.emit_expr(node.iter)
			body = [self.emit_stmt(s) for s in node.body]
			return JSForOf(target_ident, iter_expr, body)
		raise JSCompilationError(
			f"Unsupported statement: {ast.dump(node, include_attributes=False)}"
		)

	# --- Expressions ---------------------------------------------------------
	def emit_expr(self, node: ast.expr | None) -> JSExpr:
		"""Supported expressions:
		- None
		- Constants
		- Tuples
		- Lists
		- Dicts
		- Generators
		- Binary operation
		- Unary operation
		- Boolean operation
		- Compare (Q: diff w/ BoolOp?)
		- If expression
		- Function call (covers both method and function calls)
		- Attribute access
		- Indexing (called "subscript")
		- f-string (called "JoinedStr")

		TODO:
		- List/set/dict comprehensions
		- Generator expressions (they get converted to arrays)
		- Set expressions
		"""
		if node is None:
			return JSUndefined()

		if isinstance(node, ast.Constant):
			v = node.value
			if isinstance(v, str):
				return JSString(v)
			if v is None:
				return JSUndefined()
			if v is True:
				return JSBoolean(True)
			if v is False:
				return JSBoolean(False)
			return JSNumber(v)
		if isinstance(node, ast.Name):
			ident = node.id
			# Renames take precedence over predeclared locals/globals
			if ident in self.rename:
				return JSIdentifier(self.rename[ident])
			if ident in self.locals:
				return JSIdentifier(_mangle_identifier(ident))
			# Unresolved non-local
			raise JSCompilationError(f"Unbound name referenced: {ident}.")
		if isinstance(node, (ast.List, ast.Tuple)):
			list_parts: list[JSExpr] = []
			for e in node.elts:
				if isinstance(e, ast.Starred):
					list_parts.append(JSSpread(self.emit_expr(e.value)))
				else:
					list_parts.append(self.emit_expr(e))
			return JSArray(list_parts)
		if isinstance(node, ast.Dict):
			# Convert Python dict literal to new Map([...])
			entries: list[JSExpr] = []
			for k, v in zip(node.keys, node.values, strict=False):
				if k is None:
					# Spread merge: normalize to iterable of [k, v] pairs
					vexpr = self.emit_expr(v)
					is_map = JSBinary(vexpr, "instanceof", JSIdentifier("Map"))
					map_entries = JSMemberCall(vexpr, "entries", [])
					obj_entries = JSCall(
						JSMember(JSIdentifier("Object"), "entries"), [vexpr]
					)
					entries.append(
						JSSpread(JSTertiary(is_map, map_entries, obj_entries))
					)
					continue
				key_expr = self.emit_expr(k)
				val_expr = self.emit_expr(v)
				entries.append(JSArray([key_expr, val_expr]))
			return JSNew(JSIdentifier("Map"), [JSArray(entries)])
		if isinstance(node, ast.ListComp):
			return self._build_comprehension_chain(
				node.generators, lambda: self.emit_expr(node.elt)
			)
		if isinstance(node, ast.GeneratorExp):
			return self._build_comprehension_chain(
				node.generators, lambda: self.emit_expr(node.elt)
			)
		if isinstance(node, ast.SetComp):
			arr = self._build_comprehension_chain(
				node.generators, lambda: self.emit_expr(node.elt)
			)
			return JSNew(JSIdentifier("Set"), [arr])
		if isinstance(node, ast.DictComp):
			# {k: v for ...} -> new Map(chain.map(x => [k, v]))
			pairs = self._build_comprehension_chain(
				node.generators,
				lambda: JSArray(
					[
						self.emit_expr(node.key),
						self.emit_expr(node.value),
					]
				),
			)
			return JSNew(JSIdentifier("Map"), [pairs])
		if isinstance(node, ast.BinOp):
			op = type(node.op)
			if op not in ALLOWED_BINOPS:
				raise JSCompilationError(f"Operator not allowed: {op.__name__}")
			left = self.emit_expr(node.left)
			right = self.emit_expr(node.right)
			return JSBinary(left, ALLOWED_BINOPS[op], right)
		if isinstance(node, ast.UnaryOp):
			op = type(node.op)
			if op not in ALLOWED_UNOPS:
				raise JSCompilationError("Unsupported unary op")
			return JSUnary(ALLOWED_UNOPS[op], self.emit_expr(node.operand))
		if isinstance(node, ast.BoolOp):
			op = "&&" if isinstance(node.op, ast.And) else "||"
			return JSLogicalChain(op, [self.emit_expr(v) for v in node.values])
		if isinstance(node, ast.Compare):
			# Support chained comparisons, identity with None, and membership
			# Build sequential comparisons combined with &&
			operands: list[ast.expr] = [node.left, *node.comparators]
			exprs: list[JSExpr] = [self.emit_expr(e) for e in operands]
			cmp_parts: list[JSExpr] = []
			for i, op in enumerate(node.ops):
				left_node = operands[i]
				right_node = operands[i + 1]
				left_expr = exprs[i]
				right_expr = exprs[i + 1]
				cmp_parts.append(
					_build_comparison(left_expr, left_node, op, right_expr, right_node)
				)
			return JSLogicalChain("&&", cmp_parts)
		if isinstance(node, ast.IfExp):
			test = self.emit_expr(node.test)
			body = self.emit_expr(node.body)
			orelse = self.emit_expr(node.orelse)
			return JSTertiary(test, body, orelse)
		if isinstance(node, ast.Call):
			jsx = self._attempt_jsx_call(node)
			if jsx is not None:
				return jsx
			if isinstance(node.func, ast.Attribute):
				obj = self.emit_expr(node.func.value)
				attr = node.func.attr
				args = [self.emit_expr(a) for a in node.args]
				return self._build_method_call(attr, obj, args)
			return self._build_function_call(node)
		if isinstance(node, ast.Attribute):
			value = self.emit_expr(node.value)
			return JSMember(value, node.attr)
		if isinstance(node, ast.Subscript):
			jsx = self._attempt_jsx_subscript(node)
			if jsx is not None:
				return jsx
			value = self.emit_expr(node.value)
			# TODO: handle ast.Tuple for node.slice
			if isinstance(node.slice, ast.Tuple):
				raise JSCompilationError(
					"Slices with multiple arguments are not implemented yet."
				)
			# Slice handling
			if isinstance(node.slice, ast.Slice):
				if node.slice.step is not None:
					raise JSCompilationError("Slice steps are not implemented yet.")
				lower = node.slice.lower
				upper = node.slice.upper
				if lower is None and upper is None:
					# full slice -> copy
					return JSMemberCall(value, "slice", [])
				elif lower is None:
					start = JSNumber(0)
					end = self.emit_expr(upper)
					return JSMemberCall(value, "slice", [start, end])
				elif upper is None:
					start = self.emit_expr(lower)
					return JSMemberCall(value, "slice", [start])
				else:
					start = self.emit_expr(lower)
					end = self.emit_expr(upper)
					return JSMemberCall(value, "slice", [start, end])
			# Negative index single access -> at(), allow non-constant expression too
			if isinstance(node.slice, ast.UnaryOp) and isinstance(
				node.slice.op, ast.USub
			):
				idx_expr = self.emit_expr(node.slice.operand)
				return JSMemberCall(value, "at", [JSUnary("-", idx_expr)])
			index = self.emit_expr(node.slice)
			return JSSubscript(value, index)
		if isinstance(node, ast.JoinedStr):
			# General f-strings -> backtick template
			template_parts: list[str | JSExpr] = []
			for part in node.values:
				if isinstance(part, ast.Constant) and isinstance(part.value, str):
					template_parts.append(part.value)
				elif isinstance(part, ast.FormattedValue):
					expr = self.emit_expr(part.value)
					# Apply full format spec if provided
					if part.format_spec is not None:
						spec_str = _extract_formatspec_str(part.format_spec)
						expr = _apply_format_spec(expr, spec_str)
						# Special case: f-string with a single formatted value -> do not wrap in JS template
						if len(node.values) == 1:
							return expr
					template_parts.append(expr)
				else:
					raise JSCompilationError(
						f"Unsupported f-string component: {ast.dump(part, include_attributes=False)}"
					)
			return JSTemplate(template_parts)
		raise JSCompilationError(
			f"Unsupported expression: {ast.dump(node, include_attributes=False)}"
		)


###############################################################################
# JS codegen wrapper
###############################################################################


def compile_python_to_js(fn: Callable[..., Any]) -> tuple[str, int, str]:
	"""Compile a Python function to a JavaScript function expression.

	Returns (code, n_args, hash_prefix).
	"""
	# Allow JsFunction wrapper instances (unwrap to original Python callable)
	if hasattr(fn, "fn"):
		inner = getattr(fn, "fn", None)
		if callable(inner):
			fn = inner  # type: ignore[assignment]
	try:
		src = inspect.getsource(fn)
	except OSError as e:
		raise JSCompilationError(f"Cannot retrieve source for {fn}: {e}") from e

	src = textwrap.dedent(src)
	module = ast.parse(src)
	fndefs = [n for n in module.body if isinstance(n, ast.FunctionDef)]
	if not fndefs:
		raise JSCompilationError("No function definition found in source")
	# Choose the last function def in the block (common for decorators)
	fndef = fndefs[-1]

	arg_names = [arg.arg for arg in fndef.args.args]
	# Legacy compile uses bare transpiler with no refs/globals
	visitor = JsTranspiler(
		fndef, args=arg_names, globals=[], builtins=BUILTINS, rename={}
	)
	js_fn = visitor.transpile()
	code = js_fn.emit()
	n_args = len(arg_names)
	h = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
	return code, n_args, h


def _build_comparison(
	left_expr: JSExpr,
	left_node: ast.expr,
	op: ast.cmpop,
	right_expr: JSExpr,
	right_node: ast.expr,
) -> JSExpr:
	# Identity comparisons: treat as strict equality; special-case None to
	# output x == null to match both null and undefined.
	if isinstance(op, ast.Is) or isinstance(op, ast.IsNot):
		is_not = isinstance(op, ast.IsNot)
		if (isinstance(right_node, ast.Constant) and right_node.value is None) or (
			isinstance(left_node, ast.Constant) and left_node.value is None
		):
			# For None identity, allow null or undefined via loose equality
			expr = right_expr if isinstance(left_node, ast.Constant) else left_expr
			return JSBinary(expr, "!=" if is_not else "==", JSNull())
		# For non-None, use strict equality which matches desired semantics for our subset
		return JSBinary(left_expr, "!==" if is_not else "===", right_expr)
	# Membership
	if isinstance(op, ast.In) or isinstance(op, ast.NotIn):
		# arrays/strings: includes; objects: hasOwn
		is_string = StringMethods.__runtime_check__(right_expr)
		is_array = ListMethods.__runtime_check__(right_expr)
		is_set = SetMethods.__runtime_check__(right_expr)
		is_map = DictMethods.__runtime_check__(right_expr)
		is_array_or_string = JSLogicalChain("||", [is_array, is_string])
		is_set_or_map = JSLogicalChain("||", [is_set, is_map])
		has_array_or_string = JSMemberCall(right_expr, "includes", [left_expr])
		has_set_or_map = JSMemberCall(right_expr, "has", [left_expr])
		has_obj = JSBinary(left_expr, "in", right_expr)

		membership_expr = JSTertiary(
			is_array_or_string,
			has_array_or_string,
			JSTertiary(is_set_or_map, has_set_or_map, has_obj),
		)
		if isinstance(op, ast.NotIn):
			membership_expr = JSUnary("!", membership_expr)
		return membership_expr
	# Standard comparisons
	op_type = type(op)
	if op_type not in ALLOWED_CMPOPS:
		raise JSCompilationError("Comparison not allowed")
	return JSBinary(left_expr, ALLOWED_CMPOPS[op_type], right_expr)


def _mangle_identifier(name: str) -> str:
	# Keep simple characters; this can be expanded later if needed
	return name
