from __future__ import annotations

import ast
import ctypes
import functools
import inspect
import textwrap
import types
from collections.abc import Callable, Sequence
from typing import Any, Literal, cast, override

from pulse.helpers import getsourcecode
from pulse.hooks.core import HookState, hooks
from pulse.transpiler.errors import TranspileError

# Storage keyed by (code object, lineno) of the `with ps.init()` call site.
_init_hook = hooks.create("init_storage", lambda: InitState())

_CAN_USE_CPYTHON = hasattr(ctypes.pythonapi, "PyFrame_LocalsToFast")
if _CAN_USE_CPYTHON:
	PyFrame_LocalsToFast = ctypes.pythonapi.PyFrame_LocalsToFast
	PyFrame_LocalsToFast.argtypes = [ctypes.py_object, ctypes.c_int]
	PyFrame_LocalsToFast.restype = None


def previous_frame() -> types.FrameType:
	"""Get the previous frame (caller's frame) with assertions.

	This skips the frame of this helper function and its immediate caller
	to return the actual previous frame.
	"""
	current = inspect.currentframe()
	assert current is not None, "currentframe() returned None"
	# Skip this helper function's frame
	caller = current.f_back
	assert caller is not None, "f_back is None"
	# Skip the caller's frame (e.g., __enter__) to get the actual previous frame
	frame = caller.f_back
	assert frame is not None, "f_back.f_back is None"
	return frame


class InitContext:
	"""Context manager for one-time initialization in components.

	Variables assigned inside the block persist across re-renders. On first render,
	the code inside runs normally and variables are captured. On subsequent renders,
	the block is skipped and variables are restored from storage.

	This class is returned by ``ps.init()`` and should be used as a context manager.

	Attributes:
		callsite: Tuple of (code object, line number) identifying the call site.
		frame: The stack frame where init was called.
		first_render: True if this is the first render cycle.
		pre_keys: Set of variable names that existed before entering the block.
		saved: Dictionary of captured variable values.

	Example:

	```python
	def my_component():
	    with ps.init():
	        counter = 0
	        api = ApiClient()
	        data = fetch_initial_data()
	    # counter, api, data retain their values across renders
	    return m.Text(f"Counter: {counter}")
	```
	"""

	callsite: tuple[Any, int] | None
	frame: types.FrameType | None
	first_render: bool
	pre_keys: set[str]
	saved: dict[str, Any]

	def __init__(self):
		self.callsite = None
		self.frame = None
		self.first_render = False
		self.pre_keys = set()
		self.saved = {}

	def __enter__(self):
		self.frame = previous_frame()
		self.pre_keys = set(self.frame.f_locals.keys())
		# Use code object to disambiguate identical line numbers in different fns.
		self.callsite = (self.frame.f_code, self.frame.f_lineno)

		storage = _init_hook().storage
		entry = storage.get(self.callsite)
		if entry is None:
			self.first_render = True
			self.saved = {}
		else:
			self.first_render = False
			self.saved = entry["vars"]
		return self

	def restore_variables(self):
		if self.first_render:
			return
		frame = self.frame if self.frame is not None else previous_frame()
		frame.f_locals.update(self.saved)
		PyFrame_LocalsToFast(frame, 1)

	def save(self, values: dict[str, Any]):
		self.saved = values
		assert self.callsite is not None, "callsite is None"
		storage = _init_hook().storage
		storage[self.callsite] = {"vars": values}

	def _capture_new_locals(self) -> dict[str, Any]:
		frame = self.frame
		assert frame is not None, "frame is None"
		captured = {}
		for name, value in frame.f_locals.items():
			if name in self.pre_keys:
				continue
			if value is self:
				continue
			captured[name] = value
		return captured

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		exc_tb: Any,
	) -> Literal[False]:
		if exc_type is None:
			captured = self._capture_new_locals()
			assert self.callsite is not None, "callsite  None"
			storage = _init_hook().storage
			storage[self.callsite] = {"vars": captured}
		self.frame = None
		return False


def init() -> InitContext:
	"""Context manager for one-time initialization in components.

	Variables assigned inside the block persist across re-renders. Uses AST
	rewriting to transform the code at decoration time.

	Returns:
		InitContext: Context manager that captures and restores variables.

	Example:

	```python
	def my_component():
	    with ps.init():
	        counter = 0
	        api = ApiClient()
	        data = fetch_initial_data()
	    # counter, api, data retain their values across renders
	    return m.Text(f"Counter: {counter}")
	```

	Rules:
		- Can only be used once per component
		- Must be at the top level of the component function (not inside
		  conditionals, loops, or nested functions)
		- Cannot contain control flow (if, for, while, try, with, match)
		- Cannot use ``as`` binding (``with ps.init() as ctx:`` not allowed)
		- Variables are restored from first render on subsequent renders

	Notes:
		If you encounter issues with ``ps.init()`` (e.g., source code not
		available in some deployment environments), use ``ps.setup()`` instead.
		It provides the same functionality without AST rewriting.
	"""
	return InitContext()


# ---------------------------- AST rewriting -------------------------------


class InitCPythonRewriter(ast.NodeTransformer):
	counter: int
	_init_names: set[str]
	_init_modules: set[str]

	def __init__(self, init_names: set[str], init_modules: set[str]):
		super().__init__()
		self.counter = 0
		self._init_names = init_names
		self._init_modules = init_modules

	@override
	def visit_With(self, node: ast.With):
		node = cast(ast.With, self.generic_visit(node))
		if not node.items:
			return node

		item = node.items[0]
		if self.is_init_call(item.context_expr):
			ctx_name = f"_init_ctx_{self.counter}"
			self.counter += 1
			new_item = ast.withitem(
				context_expr=item.context_expr,
				optional_vars=ast.Name(id=ctx_name, ctx=ast.Store()),
			)

			restore_call = ast.Expr(
				value=ast.Call(
					func=ast.Attribute(
						value=ast.Name(id=ctx_name, ctx=ast.Load()),
						attr="restore_variables",
						ctx=ast.Load(),
					),
					args=[],
					keywords=[],
				)
			)

			new_if = ast.If(
				test=ast.Attribute(
					value=ast.Name(id=ctx_name, ctx=ast.Load()),
					attr="first_render",
					ctx=ast.Load(),
				),
				body=node.body,
				orelse=[restore_call],
			)

			return ast.With(
				items=[new_item],
				body=[new_if],
				type_comment=getattr(node, "type_comment", None),
			)

		return node

	def is_init_call(self, expr: ast.AST) -> bool:
		if not isinstance(expr, ast.Call):
			return False
		func = expr.func
		if isinstance(func, ast.Name) and func.id in self._init_names:
			return True
		if (
			isinstance(func, ast.Attribute)
			and isinstance(func.value, ast.Name)
			and func.value.id in self._init_modules
			and func.attr == "init"
		):
			return True
		return False


class InitFallbackRewriter(ast.NodeTransformer):
	"""Rewrite using explicit rebinding (portable, no LocalsToFast)."""

	counter: int
	_init_names: set[str]
	_init_modules: set[str]

	def __init__(self, init_names: set[str], init_modules: set[str]):
		super().__init__()
		self.counter = 0
		self._init_names = init_names
		self._init_modules = init_modules

	@override
	def visit_With(self, node: ast.With):
		node = cast(ast.With, self.generic_visit(node))
		if not node.items:
			return node

		item = node.items[0]
		if not self.is_init_call(item.context_expr):
			return node

		ctx_name = f"_init_ctx_{self.counter}"
		self.counter += 1
		new_item = ast.withitem(
			context_expr=item.context_expr,
			optional_vars=ast.Name(id=ctx_name, ctx=ast.Store()),
		)

		assigned = _collect_assigned_names(node.body)

		save_call = ast.Expr(
			value=ast.Call(
				func=ast.Attribute(
					value=ast.Name(id=ctx_name, ctx=ast.Load()),
					attr="save",
					ctx=ast.Load(),
				),
				args=[
					ast.Dict(
						keys=[ast.Constant(n) for n in assigned],
						values=[ast.Name(id=n, ctx=ast.Load()) for n in assigned],
					)
				],
				keywords=[],
			)
		)

		restore_assigns: Sequence[ast.stmt] = [
			ast.Assign(
				targets=[ast.Name(id=name, ctx=ast.Store())],
				value=ast.Subscript(
					value=ast.Attribute(
						value=ast.Name(id=ctx_name, ctx=ast.Load()),
						attr="saved",
						ctx=ast.Load(),
					),
					slice=ast.Constant(name),
					ctx=ast.Load(),
				),
			)
			for name in assigned
		]

		new_if = ast.If(
			test=ast.Attribute(
				value=ast.Name(id=ctx_name, ctx=ast.Load()),
				attr="first_render",
				ctx=ast.Load(),
			),
			body=node.body + [save_call],
			orelse=list(restore_assigns),
		)

		return ast.With(
			items=[new_item],
			body=[new_if],
			type_comment=getattr(node, "type_comment", None),
		)

	def is_init_call(self, expr: ast.AST) -> bool:
		if not isinstance(expr, ast.Call):
			return False
		func = expr.func
		if isinstance(func, ast.Name) and func.id in self._init_names:
			return True
		if (
			isinstance(func, ast.Attribute)
			and isinstance(func.value, ast.Name)
			and func.value.id in self._init_modules
			and func.attr == "init"
		):
			return True
		return False


def _collect_assigned_names(body: list[ast.stmt]) -> list[str]:
	names: set[str] = set()

	def add_target(target: ast.AST):
		if isinstance(target, ast.Name):
			names.add(target.id)
		elif isinstance(target, (ast.Tuple, ast.List)):
			for elt in target.elts:
				add_target(elt)

	for stmt in body:
		if isinstance(stmt, ast.Assign):
			for target in stmt.targets:
				add_target(target)
		elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
			names.add(stmt.target.id)
		elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			names.add(stmt.name)
	return list(names)


def rewrite_init_blocks(func: Callable[..., Any]) -> Callable[..., Any]:
	"""Rewrite `with ps.init()` blocks in the provided function, if present."""

	source = textwrap.dedent(getsourcecode(func))  # raises immediately if missing
	try:
		source_start_line = inspect.getsourcelines(func)[1]
	except (OSError, TypeError):
		source_start_line = None

	if "init" not in source:  # quick prefilter, allow alias detection later
		return func

	tree = ast.parse(source)

	init_names, init_modules = _resolve_init_bindings(func)

	target_def: ast.FunctionDef | ast.AsyncFunctionDef | None = None
	# Remove decorators so the re-exec'd function isn't double-wrapped.
	for node in ast.walk(tree):
		if (
			isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
			and node.name == func.__name__
		):
			node.decorator_list = []
			target_def = node

	if target_def is None:
		return func

	if not _contains_ps_init(tree, init_names, init_modules):
		return func

	init_items = _find_init_items(target_def.body, init_names, init_modules)
	if len(init_items) > 1:
		try:
			filename = inspect.getsourcefile(func) or inspect.getfile(func)
		except (TypeError, OSError):
			filename = None
		raise TranspileError(
			"ps.init may only be used once per component render",
			node=init_items[1].context_expr,
			source=source,
			filename=filename,
			func_name=func.__name__,
			source_start_line=source_start_line,
		) from None

	if init_items and init_items[0].optional_vars is not None:
		try:
			filename = inspect.getsourcefile(func) or inspect.getfile(func)
		except (TypeError, OSError):
			filename = None
		raise TranspileError(
			"ps.init does not support 'as' bindings",
			node=init_items[0].optional_vars,
			source=source,
			filename=filename,
			func_name=func.__name__,
			source_start_line=source_start_line,
		) from None

	disallowed = _find_disallowed_control_flow(
		target_def.body, init_names, init_modules
	)
	if disallowed is not None:
		try:
			filename = inspect.getsourcefile(func) or inspect.getfile(func)
		except (TypeError, OSError):
			filename = None
		raise TranspileError(
			"ps.init blocks cannot contain control flow (if/for/while/try/with/match)",
			node=disallowed,
			source=source,
			filename=filename,
			func_name=func.__name__,
			source_start_line=source_start_line,
		) from None

	rewriter: ast.NodeTransformer
	if _CAN_USE_CPYTHON:
		rewriter = InitCPythonRewriter(init_names, init_modules)
	else:
		rewriter = InitFallbackRewriter(init_names, init_modules)

	tree = rewriter.visit(tree)
	ast.fix_missing_locations(tree)

	filename = inspect.getsourcefile(func) or "<rewrite>"
	compiled = compile(tree, filename=filename, mode="exec")

	global_ns = dict(func.__globals__)
	closure_vars = inspect.getclosurevars(func)
	global_ns.update(closure_vars.nonlocals)
	# Ensure `ps` resolves during exec.
	if "ps" not in global_ns:
		try:
			import pulse as ps

			global_ns["ps"] = ps
		except Exception:
			pass
	local_ns: dict[str, Any] = {}
	exec(compiled, global_ns, local_ns)
	rewritten = local_ns.get(func.__name__) or global_ns[func.__name__]
	functools.update_wrapper(rewritten, func)
	return rewritten


def _contains_ps_init(
	tree: ast.AST, init_names: set[str], init_modules: set[str]
) -> bool:
	checker = _InitCallChecker(init_names, init_modules)
	return checker.contains_init(tree)


def _find_disallowed_control_flow(
	body: Sequence[ast.stmt], init_names: set[str], init_modules: set[str]
) -> ast.stmt | None:
	disallowed: tuple[type[ast.AST], ...] = (
		ast.If,
		ast.For,
		ast.AsyncFor,
		ast.While,
		ast.Try,
		ast.With,
		ast.AsyncWith,
		ast.Match,
	)
	checker = _InitCallChecker(init_names, init_modules)

	class _Finder(ast.NodeVisitor):
		found: ast.stmt | None

		def __init__(self) -> None:
			self.found = None

		@override
		def visit(self, node: ast.AST) -> Any:  # type: ignore[override]
			if self.found is not None:
				return None
			if isinstance(node, disallowed):
				self.found = cast(ast.stmt, node)
				return None
			return super().visit(node)

		@override
		def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
			return None

		@override
		def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
			return None

		@override
		def visit_ClassDef(self, node: ast.ClassDef) -> Any:
			return None

	finder = _Finder()

	class _WithFinder(ast.NodeVisitor):
		@override
		def visit_With(self, node: ast.With) -> Any:  # type: ignore[override]
			first = node.items[0] if node.items else None
			if first and checker.is_init_call(first.context_expr):
				for stmt in node.body:
					finder.visit(stmt)
					if finder.found is not None:
						return None
			self.generic_visit(node)

		@override
		def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:  # type: ignore[override]
			first = node.items[0] if node.items else None
			if first and checker.is_init_call(first.context_expr):
				for stmt in node.body:
					finder.visit(stmt)
					if finder.found is not None:
						return None
			self.generic_visit(node)

		@override
		def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
			return None

		@override
		def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
			return None

		@override
		def visit_ClassDef(self, node: ast.ClassDef) -> Any:
			return None

	with_finder = _WithFinder()
	for stmt in body:
		with_finder.visit(stmt)
		if finder.found is not None:
			return finder.found
	return None


def _find_init_items(
	body: Sequence[ast.stmt], init_names: set[str], init_modules: set[str]
) -> list[ast.withitem]:
	checker = _InitCallChecker(init_names, init_modules)
	items: list[ast.withitem] = []

	class _Finder(ast.NodeVisitor):
		@override
		def visit_With(self, node: ast.With) -> Any:  # type: ignore[override]
			first = node.items[0] if node.items else None
			if first and checker.is_init_call(first.context_expr):
				items.append(first)
			self.generic_visit(node)

		@override
		def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:  # type: ignore[override]
			first = node.items[0] if node.items else None
			if first and checker.is_init_call(first.context_expr):
				items.append(first)
			self.generic_visit(node)

		@override
		def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
			return None

		@override
		def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
			return None

		@override
		def visit_ClassDef(self, node: ast.ClassDef) -> Any:
			return None

	finder = _Finder()
	for stmt in body:
		finder.visit(stmt)
	return items


class _InitCallChecker:
	init_names: set[str]
	init_modules: set[str]

	def __init__(self, init_names: set[str], init_modules: set[str]):
		self.init_names = init_names
		self.init_modules = init_modules

	def is_init_call(self, expr: ast.AST) -> bool:
		if not isinstance(expr, ast.Call):
			return False
		func = expr.func
		if isinstance(func, ast.Name) and func.id in self.init_names:
			return True
		if (
			isinstance(func, ast.Attribute)
			and isinstance(func.value, ast.Name)
			and func.value.id in self.init_modules
			and func.attr == "init"
		):
			return True
		return False

	def contains_init(self, tree: ast.AST) -> bool:
		for node in ast.walk(tree):
			if self.is_init_call(node):
				return True
		return False


def _resolve_init_bindings(func: Callable[..., Any]) -> tuple[set[str], set[str]]:
	"""Find names/modules that resolve to pulse.init in the function scope."""

	init_names: set[str] = set()
	init_modules: set[str] = set()

	closure = inspect.getclosurevars(func)
	scopes = [func.__globals__, closure.nonlocals, closure.globals]

	for scope in scopes:
		for name, val in scope.items():
			if val is init:
				init_names.add(name)
			try:
				if getattr(val, "init", None) is init:
					init_modules.add(name)
			except Exception:
				continue

	return init_names, init_modules


class InitState(HookState):
	def __init__(self) -> None:
		self.storage: dict[tuple[Any, int], dict[str, Any]] = {}

	@override
	def dispose(self) -> None:
		self.storage.clear()
