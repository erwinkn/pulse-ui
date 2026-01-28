"""
Python -> JavaScript transpiler using v2 nodes.

Transpiles a restricted subset of Python into v2 Expr/Stmt AST nodes.
Dependencies are resolved through a dict[str, Expr] mapping.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, override

from pulse.transpiler.builtins import BUILTINS, emit_method
from pulse.transpiler.errors import TranspileError
from pulse.transpiler.nodes import (
	Array,
	Arrow,
	Assign,
	Binary,
	Block,
	Break,
	Call,
	Continue,
	Expr,
	ExprStmt,
	ForOf,
	Function,
	Identifier,
	If,
	LetDecl,
	Literal,
	Member,
	New,
	Return,
	Spread,
	Stmt,
	StmtSequence,
	Subscript,
	Template,
	Ternary,
	Throw,
	TryStmt,
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
	# Bitwise operators
	ast.BitAnd: "&",
	ast.BitOr: "|",
	ast.BitXor: "^",
	ast.LShift: "<<",
	ast.RShift: ">>",
}

ALLOWED_UNOPS: dict[type[ast.unaryop], str] = {
	ast.UAdd: "+",
	ast.USub: "-",
	ast.Not: "!",
	ast.Invert: "~",  # Bitwise NOT
}

ALLOWED_CMPOPS: dict[type[ast.cmpop], str] = {
	ast.Eq: "===",
	ast.NotEq: "!==",
	ast.Lt: "<",
	ast.LtE: "<=",
	ast.Gt: ">",
	ast.GtE: ">=",
}


def _collect_param_names(args: ast.arguments) -> list[str]:
	"""Collect argument names (regular, vararg, kwonly, kwarg)."""
	names: list[str] = [arg.arg for arg in args.args]
	if args.vararg:
		names.append(args.vararg.arg)
	names.extend(arg.arg for arg in args.kwonlyargs)
	if args.kwarg:
		names.append(args.kwarg.arg)
	return names


@dataclass(slots=True)
class Scope:
	locals: set[str]
	params: set[str]
	parent: "Scope | None" = None


class ScopeAnalyzer(ast.NodeVisitor):
	"""Collect locals per scope (function/lambda/comprehension)."""

	_scopes: dict[ast.AST, Scope]
	_stack: list[Scope]

	def __init__(self) -> None:
		self._scopes = {}
		self._stack = []

	def analyze(
		self, node: ast.FunctionDef | ast.AsyncFunctionDef
	) -> dict[ast.AST, Scope]:
		scope = self._new_scope(node, _collect_param_names(node.args), parent=None)
		self._stack.append(scope)
		self._visit_defaults(node.args)
		for stmt in node.body:
			self.visit(stmt)
		self._stack.pop()
		return self._scopes

	def _new_scope(
		self,
		node: ast.AST,
		params: list[str],
		*,
		parent: Scope | None,
	) -> Scope:
		param_set = set(params)
		scope = Scope(locals=set(param_set), params=param_set, parent=parent)
		self._scopes[node] = scope
		return scope

	def _current_scope(self) -> Scope:
		return self._stack[-1]

	def _add_local(self, name: str) -> None:
		self._current_scope().locals.add(name)

	def _add_targets(self, target: ast.expr) -> None:
		if isinstance(target, ast.Name):
			self._add_local(target.id)
			return
		if isinstance(target, (ast.Tuple, ast.List)):
			for elt in target.elts:
				if isinstance(elt, ast.Name):
					self._add_local(elt.id)

	def _visit_target_expr(self, target: ast.expr) -> None:
		if isinstance(target, (ast.Tuple, ast.List)):
			for elt in target.elts:
				self._visit_target_expr(elt)
			return
		self.visit(target)

	def _analyze_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
		scope = self._new_scope(
			node,
			_collect_param_names(node.args),
			parent=self._current_scope(),
		)
		self._stack.append(scope)
		self._visit_defaults(node.args)
		for stmt in node.body:
			self.visit(stmt)
		self._stack.pop()

	def _visit_defaults(self, args: ast.arguments) -> None:
		for default in args.defaults:
			self.visit(default)
		for default in args.kw_defaults:
			if default is not None:
				self.visit(default)

	@override
	def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
		self._add_local(node.name)
		self._analyze_function(node)

	@override
	def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
		self._add_local(node.name)
		self._analyze_function(node)

	@override
	def visit_Lambda(self, node: ast.Lambda) -> None:
		scope = self._new_scope(
			node,
			_collect_param_names(node.args),
			parent=self._current_scope(),
		)
		self._stack.append(scope)
		self.visit(node.body)
		self._stack.pop()

	def _visit_comprehension(
		self,
		node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
		*,
		elt: ast.expr,
		key: ast.expr | None = None,
	) -> None:
		scope = self._new_scope(node, [], parent=self._current_scope())
		self._stack.append(scope)
		if key is not None:
			self.visit(key)
		self.visit(elt)
		for gen in node.generators:
			self.visit(gen.iter)
			for if_node in gen.ifs:
				self.visit(if_node)
		self._stack.pop()

	@override
	def visit_ListComp(self, node: ast.ListComp) -> None:
		self._visit_comprehension(node, elt=node.elt)

	@override
	def visit_SetComp(self, node: ast.SetComp) -> None:
		self._visit_comprehension(node, elt=node.elt)

	@override
	def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
		self._visit_comprehension(node, elt=node.elt)

	@override
	def visit_DictComp(self, node: ast.DictComp) -> None:
		self._visit_comprehension(node, elt=node.value, key=node.key)

	@override
	def visit_Assign(self, node: ast.Assign) -> None:
		for target in node.targets:
			if isinstance(target, (ast.Name, ast.Tuple, ast.List)):
				self._add_targets(target)
			self._visit_target_expr(target)
		self.visit(node.value)

	@override
	def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
		if isinstance(node.target, (ast.Name, ast.Tuple, ast.List)):
			self._add_targets(node.target)
		self._visit_target_expr(node.target)
		if node.value is not None:
			self.visit(node.value)

	@override
	def visit_AugAssign(self, node: ast.AugAssign) -> None:
		if isinstance(node.target, (ast.Name, ast.Tuple, ast.List)):
			self._add_targets(node.target)
		self._visit_target_expr(node.target)
		self.visit(node.value)

	@override
	def visit_For(self, node: ast.For) -> None:
		if isinstance(node.target, (ast.Name, ast.Tuple, ast.List)):
			self._add_targets(node.target)
		self._visit_target_expr(node.target)
		self.visit(node.iter)
		for stmt in node.body:
			self.visit(stmt)
		for stmt in node.orelse:
			self.visit(stmt)

	@override
	def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
		if node.name:
			self._add_local(node.name)
		if node.type is not None:
			self.visit(node.type)
		for stmt in node.body:
			self.visit(stmt)

	@override
	def visit_With(self, node: ast.With) -> None:
		for item in node.items:
			if item.optional_vars and isinstance(
				item.optional_vars, (ast.Name, ast.Tuple, ast.List)
			):
				self._add_targets(item.optional_vars)
			if item.optional_vars is not None:
				self._visit_target_expr(item.optional_vars)
			self.visit(item.context_expr)
		for stmt in node.body:
			self.visit(stmt)

	@override
	def visit_Global(self, node: ast.Global) -> None:
		raise TranspileError("global is not supported", node=node)

	@override
	def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
		raise TranspileError("nonlocal is not supported", node=node)


class Transpiler:
	"""Transpile Python AST to v2 Expr/Stmt AST nodes.

	Takes a function definition and a dictionary of dependencies.
	Dependencies are substituted when their names are referenced.

	Dependencies are Expr instances. Expr subclasses can override:
	- transpile_call: custom call behavior (e.g., JSX components)
	- transpile_getattr: custom attribute access
	- transpile_subscript: custom subscript behavior
	"""

	fndef: ast.FunctionDef | ast.AsyncFunctionDef
	args: list[str]
	deps: Mapping[str, Expr]
	jsx: bool
	source_file: Path | None
	_temp_counter: int
	_scope_map: dict[ast.AST, Scope]
	_scope_stack: list[Scope]

	def __init__(
		self,
		fndef: ast.FunctionDef | ast.AsyncFunctionDef,
		deps: Mapping[str, Expr],
		*,
		jsx: bool = False,
		source_file: Path | None = None,
	) -> None:
		self.fndef = fndef
		self.source_file = source_file
		# Collect all argument names (regular, vararg, kwonly, kwarg)
		self.args = _collect_param_names(fndef.args)
		self.deps = deps
		self.jsx = jsx
		self._temp_counter = 0
		self._scope_map = ScopeAnalyzer().analyze(fndef)
		self._scope_stack = [self._scope_map[fndef]]
		self.init_temp_counter()

	def init_temp_counter(self) -> None:
		"""Initialize temp counter to avoid collisions with args or globals."""
		all_names = set(self.deps.keys())
		for scope in self._scope_map.values():
			all_names.update(scope.locals)
		counter = 0
		while f"$tmp{counter}" in all_names:
			counter += 1
		self._temp_counter = counter

	def _fresh_temp(self) -> str:
		"""Generate a fresh temporary variable name."""
		name = f"$tmp{self._temp_counter}"
		self._temp_counter += 1
		return name

	def _current_scope(self) -> Scope:
		return self._scope_stack[-1]

	def _push_scope(self, node: ast.AST) -> None:
		self._scope_stack.append(self._scope_map[node])

	def _pop_scope(self) -> None:
		self._scope_stack.pop()

	def _is_local_here(self, name: str) -> bool:
		return name in self._current_scope().locals

	def _is_local(self, name: str) -> bool:
		scope: Scope | None = self._current_scope()
		while scope is not None:
			if name in scope.locals:
				return True
			scope = scope.parent
		return False

	def _require_local(
		self, name: str, *, node: ast.expr | ast.stmt | ast.excepthandler
	) -> None:
		if not self._is_local_here(name):
			raise TranspileError(f"Assignment to unknown local: {name}", node=node)

	def _function_prelude(self, scope: Scope) -> list[Stmt]:
		names = sorted(scope.locals - scope.params)
		if not names:
			return []
		return [LetDecl(names)]

	# --- Entrypoint ---------------------------------------------------------

	def transpile(self) -> Function | Arrow:
		"""Transpile the function to a Function or Arrow node.

		For single-expression functions (or single return), produces Arrow:
			(params) => expr

		For multi-statement functions, produces Function:
			function(params) { ... }

		For JSX functions, produces Function with destructured props parameter:
			function({param1, param2 = default}) { ... }
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

		# Arrow optimizations (only for non-JSX)
		if not self.jsx:
			if not body:
				return Arrow(self.args, Literal(None))

			if len(body) == 1:
				stmt = body[0]
				if isinstance(stmt, ast.Return):
					expr = self.emit_expr(stmt.value)
					return Arrow(self.args, expr)
				if isinstance(stmt, ast.Expr):
					expr = self.emit_expr(stmt.value)
					return Arrow(self.args, expr)

		# General case: Function (for JSX or multi-statement)
		prelude = self._function_prelude(self._current_scope())
		stmts = prelude + [self.emit_stmt(s) for s in body]
		is_async = isinstance(self.fndef, ast.AsyncFunctionDef)
		args = [self._jsx_args()] if self.jsx else self.args
		return Function(args, stmts, is_async=is_async)

	def _jsx_args(self) -> str:
		"""Build a destructured props parameter for JSX functions.

		React components receive a single props object, so parameters
		are emitted as a destructuring pattern: {param1, param2 = default, ...}
		"""
		args = self.fndef.args
		destructure_parts: list[str] = []
		default_out: list[str] = []

		# Regular arguments (may have defaults at the end)
		num_defaults = len(args.defaults)
		num_args = len(args.args)
		for i, arg in enumerate(args.args):
			param_name = arg.arg
			# Defaults align to the right: if we have 3 args and 1 default,
			# the default is for args[2], not args[0]
			default_idx = i - (num_args - num_defaults)
			if default_idx >= 0:
				# Has a default value
				default_node = args.defaults[default_idx]
				default_expr = self.emit_expr(default_node)
				default_out.clear()
				default_expr.emit(default_out)
				destructure_parts.append(f"{param_name} = {''.join(default_out)}")
			else:
				# No default
				destructure_parts.append(param_name)

		# *args (VAR_POSITIONAL)
		if args.vararg:
			destructure_parts.append(args.vararg.arg)

		# Keyword-only arguments
		for i, arg in enumerate(args.kwonlyargs):
			param_name = arg.arg
			default_node = args.kw_defaults[i]
			if default_node is not None:
				# Has a default value
				default_expr = self.emit_expr(default_node)
				default_out.clear()
				default_expr.emit(default_out)
				destructure_parts.append(f"{param_name} = {''.join(default_out)}")
			else:
				# No default
				destructure_parts.append(param_name)

		# **kwargs (VAR_KEYWORD)
		if args.kwarg:
			destructure_parts.append(f"...{args.kwarg.arg}")

		return "{" + ", ".join(destructure_parts) + "}"

	# --- Statements ----------------------------------------------------------

	def emit_stmt(self, node: ast.stmt) -> Stmt:
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
			if isinstance(node.target, ast.Subscript):
				return self._emit_augmented_subscript_assign(node)
			if isinstance(node.target, ast.Attribute):
				return self._emit_augmented_attribute_assign(node)
			if not isinstance(node.target, ast.Name):
				raise TranspileError(
					"Only simple augmented assignments supported", node=node
				)
			target = node.target.id
			self._require_local(target, node=node)
			op_type = type(node.op)
			if op_type not in ALLOWED_BINOPS:
				raise TranspileError(
					f"Unsupported augmented assignment operator: {op_type.__name__}",
					node=node,
				)
			value_expr = self.emit_expr(node.value)
			return Assign(target, value_expr, op=ALLOWED_BINOPS[op_type])

		if isinstance(node, ast.Assign):
			if len(node.targets) != 1:
				raise TranspileError(
					"Multiple assignment targets not supported", node=node
				)
			target_node = node.targets[0]

			# Tuple/list unpacking
			if isinstance(target_node, (ast.Tuple, ast.List)):
				return self._emit_unpacking_assign(target_node, node.value)

			if isinstance(target_node, ast.Subscript):
				return self._emit_subscript_assign(target_node, node.value)

			if isinstance(target_node, ast.Attribute):
				return self._emit_attribute_assign(target_node, node.value)

			if not isinstance(target_node, ast.Name):
				raise TranspileError(
					"Only simple assignments to local names supported", node=node
				)

			target = target_node.id
			value_expr = self.emit_expr(node.value)

			self._require_local(target, node=node)
			return Assign(target, value_expr)

		if isinstance(node, ast.AnnAssign):
			if not isinstance(node.target, ast.Name):
				raise TranspileError("Only simple annotated assignments supported")
			target = node.target.id
			value = Literal(None) if node.value is None else self.emit_expr(node.value)
			self._require_local(target, node=node)
			return Assign(target, value)

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

		if isinstance(node, ast.Try):
			return self._emit_try(node)

		if isinstance(node, ast.Raise):
			return self._emit_raise(node)

		raise TranspileError(f"Unsupported statement: {type(node).__name__}", node=node)

	def _emit_unpacking_assign(
		self, target: ast.Tuple | ast.List, value: ast.expr
	) -> Stmt:
		"""Emit unpacking assignment: a, b, c = expr"""
		elements = target.elts
		if not elements or not all(isinstance(e, ast.Name) for e in elements):
			raise TranspileError("Unpacking only supported for simple variables")

		tmp_name = self._fresh_temp()
		value_expr = self.emit_expr(value)
		stmts: list[Stmt] = [Assign(tmp_name, value_expr, declare="const")]

		for idx, e in enumerate(elements):
			assert isinstance(e, ast.Name)
			name = e.id
			sub = Subscript(Identifier(tmp_name), Literal(idx))
			self._require_local(name, node=target)
			stmts.append(Assign(name, sub))

		return StmtSequence(stmts)

	def _emit_subscript_assign(self, target: ast.Subscript, value: ast.expr) -> Stmt:
		"""Emit subscript assignment: obj[key] = value"""
		if isinstance(target.slice, ast.Tuple):
			raise TranspileError(
				"Multiple indices not supported in subscript", node=target.slice
			)
		if isinstance(target.slice, ast.Slice):
			raise TranspileError("Slice assignment not supported", node=target.slice)
		obj_expr = self.emit_expr(target.value)
		target_expr = obj_expr.transpile_subscript(target.slice, self)
		if not isinstance(target_expr, (Identifier, Member, Subscript)):
			raise TranspileError(
				"Only simple subscript assignments supported", node=target
			)
		value_expr = self.emit_expr(value)
		return Assign(target_expr, value_expr)

	def _emit_attribute_assign(self, target: ast.Attribute, value: ast.expr) -> Stmt:
		"""Emit attribute assignment: obj.attr = value"""
		obj_expr = self.emit_expr(target.value)
		value_expr = self.emit_expr(value)
		target_expr = obj_expr.transpile_getattr(target.attr, self)
		if not isinstance(target_expr, (Identifier, Member, Subscript)):
			raise TranspileError(
				"Only simple attribute assignments supported", node=target
			)
		return Assign(target_expr, value_expr)

	def _emit_augmented_subscript_assign(self, node: ast.AugAssign) -> Stmt:
		"""Emit augmented subscript assignment: arr[i] += x"""
		target = node.target
		assert isinstance(target, ast.Subscript)

		if isinstance(target.slice, ast.Tuple):
			raise TranspileError(
				"Multiple indices not supported in subscript", node=target.slice
			)
		if isinstance(target.slice, ast.Slice):
			raise TranspileError("Slice assignment not supported", node=target.slice)

		obj_expr = self.emit_expr(target.value)
		op_type = type(node.op)
		if op_type not in ALLOWED_BINOPS:
			raise TranspileError(
				f"Unsupported augmented assignment operator: {op_type.__name__}",
				node=node,
			)
		target_expr = obj_expr.transpile_subscript(target.slice, self)
		if not isinstance(target_expr, (Identifier, Member, Subscript)):
			raise TranspileError(
				"Only simple subscript assignments supported", node=target
			)
		value_expr = self.emit_expr(node.value)
		return Assign(target_expr, value_expr, op=ALLOWED_BINOPS[op_type])

	def _emit_augmented_attribute_assign(self, node: ast.AugAssign) -> Stmt:
		"""Emit augmented attribute assignment: obj.attr += x"""
		target = node.target
		assert isinstance(target, ast.Attribute)

		obj_expr = self.emit_expr(target.value)
		op_type = type(node.op)
		if op_type not in ALLOWED_BINOPS:
			raise TranspileError(
				f"Unsupported augmented assignment operator: {op_type.__name__}",
				node=node,
			)

		target_expr = obj_expr.transpile_getattr(target.attr, self)
		if not isinstance(target_expr, (Identifier, Member, Subscript)):
			raise TranspileError(
				"Only simple attribute assignments supported", node=target
			)
		value_expr = self.emit_expr(node.value)
		return Assign(target_expr, value_expr, op=ALLOWED_BINOPS[op_type])

	def _emit_for_loop(self, node: ast.For) -> Stmt:
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
				self._require_local(e.id, node=node)
			iter_expr = self.emit_expr(node.iter)
			body = [self.emit_stmt(s) for s in node.body]
			# Use array pattern for destructuring
			target = f"[{', '.join(names)}]"
			return ForOf(target, iter_expr, body)

		if not isinstance(node.target, ast.Name):
			raise TranspileError("Only simple name targets supported in for-loops")

		target = node.target.id
		self._require_local(target, node=node)
		iter_expr = self.emit_expr(node.iter)
		body = [self.emit_stmt(s) for s in node.body]
		return ForOf(target, iter_expr, body)

	def _emit_nested_function(
		self, node: ast.FunctionDef | ast.AsyncFunctionDef
	) -> Stmt:
		"""Emit a nested function definition."""
		name = node.name
		params = _collect_param_names(node.args)
		self._require_local(name, node=node)

		self._push_scope(node)
		try:
			# Skip docstrings and emit body
			body_stmts = node.body
			if (
				body_stmts
				and isinstance(body_stmts[0], ast.Expr)
				and isinstance(body_stmts[0].value, ast.Constant)
				and isinstance(body_stmts[0].value.value, str)
			):
				body_stmts = body_stmts[1:]

			prelude = self._function_prelude(self._current_scope())
			stmts: list[Stmt] = prelude + [self.emit_stmt(s) for s in body_stmts]
		finally:
			self._pop_scope()

		is_async = isinstance(node, ast.AsyncFunctionDef)
		fn = Function(params, stmts, is_async=is_async)
		return Assign(name, fn)

	def _emit_try(self, node: ast.Try) -> Stmt:
		"""Emit a try/except/finally statement."""
		body = [self.emit_stmt(s) for s in node.body]

		# Handle except handlers - JS only supports single catch
		catch_param: str | None = None
		catch_body: list[Stmt] | None = None

		if node.handlers:
			if len(node.handlers) > 1:
				raise TranspileError(
					"Multiple except clauses not supported; JS only has one catch block",
					node=node.handlers[1],
				)
			handler = node.handlers[0]
			if handler.name:
				catch_param = handler.name
			catch_body = [self.emit_stmt(s) for s in handler.body]

		# Handle finally
		finally_body: list[Stmt] | None = None
		if node.finalbody:
			finally_body = [self.emit_stmt(s) for s in node.finalbody]

		return TryStmt(body, catch_param, catch_body, finally_body)

	def _emit_raise(self, node: ast.Raise) -> Stmt:
		"""Emit a raise statement as throw."""
		if node.exc is None:
			raise TranspileError(
				"Bare raise not supported; use explicit 'raise e' instead", node=node
			)

		return Throw(self.emit_expr(node.exc))

	# --- Expressions ---------------------------------------------------------

	def emit_expr(self, node: ast.expr | None) -> Expr:
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
			return New(
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
				node, lambda: self.emit_expr(node.elt)
			)

		if isinstance(node, ast.GeneratorExp):
			return self._emit_comprehension_chain(
				node, lambda: self.emit_expr(node.elt)
			)

		if isinstance(node, ast.SetComp):
			arr = self._emit_comprehension_chain(node, lambda: self.emit_expr(node.elt))
			return New(Identifier("Set"), [arr])

		if isinstance(node, ast.DictComp):
			pairs = self._emit_comprehension_chain(
				node,
				lambda: Array([self.emit_expr(node.key), self.emit_expr(node.value)]),
			)
			return New(Identifier("Map"), [pairs])

		if isinstance(node, ast.Lambda):
			return self._emit_lambda(node)

		if isinstance(node, ast.Starred):
			return Spread(self.emit_expr(node.value))

		if isinstance(node, ast.Await):
			return Unary("await", self.emit_expr(node.value))

		raise TranspileError(
			f"Unsupported expression: {type(node).__name__}", node=node
		)

	def _emit_constant(self, node: ast.Constant) -> Expr:
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

	def _emit_name(self, node: ast.Name) -> Expr:
		"""Emit a name reference."""
		name = node.id

		# Local variable (current or enclosing scope)
		if self._is_local(name):
			return Identifier(name)

		# Check deps
		if name in self.deps:
			return self.deps[name]

		# Check builtins
		if name in BUILTINS:
			return BUILTINS[name]

		raise TranspileError(f"Unbound name referenced: {name}", node=node)

	def _emit_list_or_tuple(self, node: ast.List | ast.Tuple) -> Expr:
		"""Emit a list or tuple literal."""
		parts: list[Expr] = []
		for e in node.elts:
			if isinstance(e, ast.Starred):
				parts.append(Spread(self.emit_expr(e.value)))
			else:
				parts.append(self.emit_expr(e))
		return Array(parts)

	def _emit_dict(self, node: ast.Dict) -> Expr:
		"""Emit a dict literal as new Map([...])."""
		entries: list[Expr] = []
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
		return New(Identifier("Map"), [Array(entries)])

	def _emit_binop(self, node: ast.BinOp) -> Expr:
		"""Emit a binary operation."""
		op = type(node.op)

		# Special case: floor division -> Math.floor(x / y)
		if op is ast.FloorDiv:
			left = self.emit_expr(node.left)
			right = self.emit_expr(node.right)
			return Call(
				Member(Identifier("Math"), "floor"),
				[Binary(left, "/", right)],
			)

		if op not in ALLOWED_BINOPS:
			raise TranspileError(
				f"Unsupported binary operator: {op.__name__}", node=node
			)
		left = self.emit_expr(node.left)
		right = self.emit_expr(node.right)
		return Binary(left, ALLOWED_BINOPS[op], right)

	def _emit_unaryop(self, node: ast.UnaryOp) -> Expr:
		"""Emit a unary operation."""
		op = type(node.op)
		if op not in ALLOWED_UNOPS:
			raise TranspileError(
				f"Unsupported unary operator: {op.__name__}", node=node
			)
		return Unary(ALLOWED_UNOPS[op], self.emit_expr(node.operand))

	def _emit_boolop(self, node: ast.BoolOp) -> Expr:
		"""Emit a boolean operation (and/or chain)."""
		op = "&&" if isinstance(node.op, ast.And) else "||"
		values = [self.emit_expr(v) for v in node.values]
		# Build binary chain: a && b && c -> Binary(Binary(a, &&, b), &&, c)
		result = values[0]
		for v in values[1:]:
			result = Binary(result, op, v)
		return result

	def _emit_compare(self, node: ast.Compare) -> Expr:
		"""Emit a comparison expression."""
		operands: list[ast.expr] = [node.left, *node.comparators]
		exprs: list[Expr] = [self.emit_expr(e) for e in operands]
		cmp_parts: list[Expr] = []

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
		left_expr: Expr,
		left_node: ast.expr,
		op: ast.cmpop,
		right_expr: Expr,
		right_node: ast.expr,
	) -> Expr:
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

	def _build_membership_test(self, item: Expr, container: Expr, negate: bool) -> Expr:
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

	def _emit_call(self, node: ast.Call) -> Expr:
		"""Emit a function call."""
		# Method call: obj.method(args) - try builtin method dispatch
		if isinstance(node.func, ast.Attribute):
			# Check for spreads - if present, skip builtin method handling
			# (let transpile_call decide on spread support)
			has_spread = any(kw.arg is None for kw in node.keywords)

			obj = self.emit_expr(node.func.value)
			method = node.func.attr

			# Try builtin method handling only if no spreads
			if not has_spread:
				# Safe to cast: has_spread=False means all kw.arg are str (not None)
				kwargs_raw: dict[str, Any] = {
					cast(str, kw.arg): kw.value for kw in node.keywords
				}
				args: list[Expr] = [self.emit_expr(a) for a in node.args]
				kwargs: dict[str, Expr] = {
					k: self.emit_expr(v) for k, v in kwargs_raw.items()
				}
				result = emit_method(obj, method, args, kwargs)
				if result is not None:
					return result

			# IMPORTANT: derive method expr via transpile_getattr
			method_expr = obj.transpile_getattr(method, self)
			return method_expr.transpile_call(
				list(node.args), list(node.keywords), self
			)

		# Function call - pass raw keywords (let callee decide on spread support)
		callee = self.emit_expr(node.func)
		return callee.transpile_call(list(node.args), list(node.keywords), self)

	def _emit_attribute(self, node: ast.Attribute) -> Expr:
		"""Emit an attribute access."""
		value = self.emit_expr(node.value)
		# Delegate to Expr.transpile_getattr (default returns Member)
		return value.transpile_getattr(node.attr, self)

	def _emit_subscript(self, node: ast.Subscript) -> Expr:
		"""Emit a subscript expression."""
		value = self.emit_expr(node.value)

		# Slice handling
		if isinstance(node.slice, ast.Slice):
			return self._emit_slice(value, node.slice)

		# Delegate to Expr.transpile_subscript (default returns Subscript)
		return value.transpile_subscript(node.slice, self)

	def _emit_slice(self, value: Expr, slice_node: ast.Slice) -> Expr:
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

	def _emit_fstring(self, node: ast.JoinedStr) -> Expr:
		"""Emit an f-string as a template literal."""
		parts: list[str | Expr] = []
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

	def _apply_format_spec(self, expr: Expr, format_spec: ast.JoinedStr) -> Expr:
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

	def _parse_and_apply_format(self, expr: Expr, spec: str) -> Expr:
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
		grouping = match.group(6) or ""
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
		elif type_char == "g":
			# General format: uses toPrecision
			prec = precision if precision is not None else 6
			expr = Call(Member(expr, "toPrecision"), [Literal(prec)])
		elif type_char == "G":
			# General format uppercase
			prec = precision if precision is not None else 6
			expr = Call(
				Member(
					Call(Member(expr, "toPrecision"), [Literal(prec)]), "toUpperCase"
				),
				[],
			)
		elif type_char == "%":
			# Percentage: multiply by 100, format as fixed, append %
			prec = precision if precision is not None else 6
			multiplied = Binary(expr, "*", Literal(100))
			fixed = Call(Member(multiplied, "toFixed"), [Literal(prec)])
			expr = Binary(fixed, "+", Literal("%"))
		elif type_char == "c":
			# Character: convert code point to character
			expr = Call(Member(Identifier("String"), "fromCharCode"), [expr])
		elif type_char == "n":
			# Locale-aware number format
			expr = Call(Member(expr, "toLocaleString"), [])
		elif type_char == "s" or type_char == "":
			if type_char == "s" or (width is not None and align):
				expr = Call(Identifier("String"), [expr])

		# Apply thousand separator grouping
		if grouping == ",":
			# Use toLocaleString with en-US to get comma separators
			expr = Call(Member(expr, "toLocaleString"), [Literal("en-US")])
		elif grouping == "_":
			# Use toLocaleString then replace commas with underscores
			locale_expr = Call(Member(expr, "toLocaleString"), [Literal("en-US")])
			expr = Call(
				Member(locale_expr, "replace"), [Identifier(r"/,/g"), Literal("_")]
			)

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

	def _emit_lambda(self, node: ast.Lambda) -> Expr:
		"""Emit a lambda expression as an arrow function."""
		params = _collect_param_names(node.args)

		self._push_scope(node)
		try:
			body = self.emit_expr(node.body)
		finally:
			self._pop_scope()

		return Arrow(params, body)

	def _emit_comprehension_chain(
		self,
		node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
		build_last: Callable[[], Expr],
	) -> Expr:
		"""Build a flatMap/map chain for comprehensions."""
		generators = node.generators
		if len(generators) == 0:
			raise TranspileError("Empty comprehension")

		def build_chain(gen_index: int) -> Expr:
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
				params = [f"([{', '.join(names)}])"]
			else:
				raise TranspileError(
					"Only name or tuple targets supported in comprehensions"
				)

			for nm in names:
				self._current_scope().locals.add(nm)

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

		self._push_scope(node)
		try:
			return build_chain(0)
		finally:
			self._pop_scope()


def transpile(
	fndef: ast.FunctionDef | ast.AsyncFunctionDef,
	deps: Mapping[str, Expr] | None = None,
) -> Function | Arrow:
	"""Transpile a Python function to a v2 Function or Arrow node.

	Args:
		fndef: The function definition AST node
		deps: Dictionary mapping global names to Expr instances

	Returns:
		Arrow for single-expression functions, Function for multi-statement
	"""
	return Transpiler(fndef, deps or {}).transpile()
