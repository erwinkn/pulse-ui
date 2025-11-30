from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from typing import (
	Any,
	Callable,
	Generic,
	NamedTuple,
	TypeAlias,
	TypeVar,
	TypeVarTuple,
)

from .builtins import BUILTINS, TAG_BUILTINS, Builtin
from .nodes import (
	JSArray,
	JSBoolean,
	JSCompilationError,
	JSExpr,
	JSFunctionDef,
	JSIdentifier,
	JSImport,
	JSNew,
	JSNumber,
	JSString,
)
from .transpiler import JsTranspiler

R = TypeVar("R")
Args = TypeVarTuple("Args")

AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any,...], Any]"


class JsFunctionCode(NamedTuple):
	code: str
	hash: str


_JS_FUNCTION_CACHE: dict[Callable[..., object], AnyJsFunction] = {}


def _const_to_js_expr(value: object) -> JSExpr:
	if value is None:
		# Represent None as undefined for our JS subset
		return JSIdentifier("undefined")
	if isinstance(value, bool):
		return JSBoolean(value)
	if isinstance(value, (int, float)):
		return JSNumber(value)
	if isinstance(value, str):
		return JSString(value)
	if isinstance(value, (list, tuple)):
		return JSArray([_const_to_js_expr(v) for v in value])  # pyright: ignore[reportUnknownArgumentType]
	if isinstance(value, (set, frozenset)):
		return JSNew(
			JSIdentifier("Set"),
			[JSArray([_const_to_js_expr(v) for v in value])],  # pyright: ignore[reportUnknownArgumentType]
		)
	if isinstance(value, dict):
		# Normalize Python dict constants to Map semantics so methods like .get() work
		entries: list[JSExpr] = []
		for k, v in value.items():
			if not isinstance(k, str):
				raise JSCompilationError("Only string keys supported in constant dicts")
			entries.append(JSArray([JSString(k), _const_to_js_expr(v)]))  # pyright: ignore[reportUnknownArgumentType]
		return JSNew(JSIdentifier("Map"), [JSArray(entries)])
	raise JSCompilationError(f"Unsupported global constant: {type(value).__name__}")


class JsFunction(Generic[*Args, R]):
	js_name: str
	fn: Callable[[*Args], R]
	imports: list[JSImport]
	dependencies: dict[str, AnyJsFunction]
	globals: dict[str, JSExpr]
	_fndef: ast.FunctionDef
	_arg_names: list[str]
	_builtin_names: set[str]
	_module_builtins: dict[str, dict[str, Builtin]]

	def __init__(
		self,
		fn: Callable[[*Args], R],
	) -> None:
		self.fn = fn
		self.imports = []
		self.dependencies = {}
		self.globals = {}

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

		# Choose a stable JS name for this function
		try:
			own_src = inspect.getsource(fn)
		except OSError:
			own_src = fn.__name__
		h = hashlib.sha256(textwrap.dedent(own_src).encode("utf-8")).hexdigest()[:8]
		self.js_name = f"{fn.__name__}${h}"

		closure = inspect.getclosurevars(fn)

		# 1) Collect global functions and constants
		self.dependencies = {}
		self._module_builtins = {}
		for name, val in closure.globals.items():
			# Ignore typing helpers entirely (e.g., Any, cast)
			mod_of_val = getattr(val, "__module__", "")
			if mod_of_val in ("typing", "typing_extensions"):
				continue
			if inspect.isfunction(val):
				jf = _JS_FUNCTION_CACHE.get(val)
				if jf is None:
					jf = JsFunction(val)
					_JS_FUNCTION_CACHE[val] = jf
				self.dependencies[name] = jf
			elif inspect.ismodule(val):
				mod_name = getattr(val, "__name__", "")
				if mod_name == "pulse":
					self._module_builtins[name] = dict(TAG_BUILTINS)
			elif callable(val):
				raise JSCompilationError(
					f"Unsupported callable object in globals: {name} ({type(val).__name__}). Only plain functions are allowed."
				)
			else:
				self.globals[name] = _const_to_js_expr(val)
		# 2) Stash AST/transpile info for lazy transpile with rename later
		self._fndef = fndef
		self._arg_names = arg_names
		self._builtin_names = (
			set(closure.builtins) if hasattr(closure, "builtins") else set()
		)

	def _transpile(self, rename: dict[str, str]) -> JSFunctionDef:
		# Always include HTML tag builtins; filter the rest by closure builtins
		builtins = {
			name: fn for name, fn in BUILTINS.items() if name in self._builtin_names
		}
		for name in TAG_BUILTINS.keys():
			builtins[name] = BUILTINS[name]
		visitor = JsTranspiler(
			self._fndef,
			args=self._arg_names,
			rename=rename,
			globals=list(self.dependencies.keys() | self.globals.keys()),
			builtins=builtins,
			module_builtins=self._module_builtins,
		)
		return visitor.transpile()

	def _emit_named_function(self, allocated_name: str, js_fn_expr_code: str) -> str:
		# Convert `function(args){...}` into `function <allocated_name>(args){...}`
		prefix = "function("
		named_prefix = f"function {allocated_name}("
		if js_fn_expr_code.startswith(prefix):
			return named_prefix + js_fn_expr_code[len(prefix) :]
		# Fallback: if already arrow or otherwise, wrap as const binding with name
		return (
			f"function {allocated_name}{js_fn_expr_code[js_fn_expr_code.find('(') :]}"
		)

	def emit(self):
		code, names = emit_many([self])
		# Update js_name to the allocated emitted name for downstream consumers/tests
		try:
			self.js_name = names[self]
		except Exception:
			pass
		h = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
		return JsFunctionCode(code, h)

	def __call__(self, *args: *Args) -> R:
		return self.fn(*args)


class _NameAllocator:
	def __init__(self) -> None:
		self.used: set[str] = set()
		self.counts: dict[str, int] = {}

	def reserve(self, name: str) -> None:
		self.used.add(name)

	def alloc(self, base: str) -> str:
		if base not in self.used:
			self.used.add(base)
			self.counts.setdefault(base, 1)
			return base
		# bump counter
		idx = self.counts.get(base, 1) + 1
		while True:
			candidate = f"{base}{idx}"
			if candidate not in self.used:
				self.used.add(candidate)
				self.counts[base] = idx
				return candidate
			idx += 1


def emit_many(roots: list[AnyJsFunction]) -> tuple[str, dict[AnyJsFunction, str]]:
	# Build union DAG
	visited: set[AnyJsFunction] = set()
	temp: set[AnyJsFunction] = set()
	order: list[AnyJsFunction] = []

	def dfs(node: AnyJsFunction):
		if node in temp:
			raise JSCompilationError("Cycle detected in function dependencies")
		if node in visited:
			return
		temp.add(node)
		for child in node.dependencies.values():
			dfs(child)
		temp.remove(node)
		visited.add(node)
		order.append(node)

	for r in roots:
		dfs(r)

	# Name allocator across the whole graph
	allocator = _NameAllocator()

	# Allocate function names deterministically by base python name
	fn_names: dict[AnyJsFunction, str] = {}
	for node in order:
		base = node.fn.__name__
		fn_names[node] = allocator.alloc(base)

	# Allocate constants with dedup by emitted code
	const_code_to_name: dict[str, str] = {}
	const_alloc_per_node: dict[AnyJsFunction, dict[str, str]] = {}
	for node in order:
		mapping: dict[str, str] = {}
		for cname, cexpr in node.globals.items():
			code = cexpr.emit()
			existing = const_code_to_name.get(code)
			if existing is not None:
				mapping[cname] = existing
				continue
			# allocate new based on cname, may need suffix
			allocated = allocator.alloc(cname)
			const_code_to_name[code] = allocated
			mapping[cname] = allocated
		const_alloc_per_node[node] = mapping

	# Build rename maps per node
	rename_per_node: dict[AnyJsFunction, dict[str, str]] = {}
	for node in order:
		ren: dict[str, str] = {}
		# functions referenced by their original global names
		for ref_name, child in node.dependencies.items():
			ren[ref_name] = fn_names[child]
		# constants
		ren.update(const_alloc_per_node.get(node, {}))
		rename_per_node[node] = ren

	# Emit: all function declarations (deps first, roots last), then constants
	lines: list[str] = []
	for node in order:
		js_fn_expr = node._transpile(rename_per_node[node]).emit()  # pyright: ignore[reportPrivateUsage]
		lines.append(node._emit_named_function(fn_names[node], js_fn_expr))  # pyright: ignore[reportPrivateUsage]

	# Emit constants after functions (function declarations are hoisted)
	for code, name in sorted(
		((code, name) for code, name in const_code_to_name.items()), key=lambda x: x[1]
	):
		lines.append(f"const {name} = {code};")

	return "\n\n".join(lines), {r: fn_names[r] for r in roots}


class ExternalJsFunction(Generic[*Args, R]):
	name: str
	src: str
	is_default: bool
	hint: Callable[[*Args], R]

	def __init__(
		self, name: str, src: str, is_default: bool, hint: Callable[[*Args], R]
	) -> None:
		self.name = name
		self.src = src
		self.is_default = is_default
		self.hint = hint

	def __call__(self, *args: *Args) -> R: ...


def external_javascript(name: str, src: str, is_default: bool = False):
	def decorator(fn: Callable[[*Args], R]):
		return ExternalJsFunction(name=name, src=src, is_default=is_default, hint=fn)

	return decorator


def javascript(fn: Callable[[*Args], R]):
	"""Decorator that compiles a Python function into JavaScript and stores
	metadata on the function object for the reconciler.

	Usage:
	    @javascript
	    def formatter(x):
	        return f"{x:.2f}"
	"""

	def decorator(inner: Callable[[*Args], R]):
		return JsFunction(inner)

	if fn is not None:
		return decorator(fn)
	return decorator
