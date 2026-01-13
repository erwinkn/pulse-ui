"""Core infrastructure for JavaScript module bindings in transpiler.

JS modules are Python modules that map to JavaScript modules/builtins.
Registration is done by calling register_js_module() from within the module itself.
"""

from __future__ import annotations

import ast
import inspect
import sys
from dataclasses import dataclass, field
from typing import Any, Literal, override

from pulse.code_analysis import is_stub_function
from pulse.transpiler.errors import TranspileError
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import (
	Expr,
	Identifier,
	Jsx,
	Member,
	New,
)
from pulse.transpiler.transpiler import Transpiler
from pulse.transpiler.vdom import VDOMNode

_MODULE_DUNDERS = frozenset(
	{
		"__name__",
		"__file__",
		"__doc__",
		"__package__",
		"__path__",
		"__cached__",
		"__loader__",
		"__spec__",
		"__builtins__",
		"__annotations__",
	}
)


@dataclass(slots=True)
class Class(Expr):
	"""Expr wrapper that emits calls as `new ...(...)`.

	Must also behave like the wrapped expression for attribute access,
	so patterns like `Promise.resolve(...)` work even if `Promise(...)` emits
	as `new Promise(...)`.
	"""

	ctor: Expr
	name: str = ""

	@override
	def emit(self, out: list[str]) -> None:
		self.ctor.emit(out)

	@override
	def render(self) -> VDOMNode:
		return self.ctor.render()

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		if keywords:
			raise TranspileError("Keyword arguments not supported in constructor call")
		return New(self.ctor, [ctx.emit_expr(a) for a in args])

	@override
	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		# Convention: trailing underscore escapes Python keywords (e.g. from_ -> from, is_ -> is)
		js_attr = attr[:-1] if attr.endswith("_") else attr
		return Member(self.ctor, js_attr)


@dataclass(frozen=True)
class JsModule(Expr):
	"""Expr representing a JavaScript module binding.

	Attributes:
		name: The JavaScript identifier for the module binding (e.g., "Math", "React"),
			or None for "global identifier" modules with no module expression.
		py_name: Python module name for error messages (e.g., "pulse.js.math")
		src: Import source path. None for builtins.
		kind: Import kind - "default" or "namespace"
		values: How attribute access is expressed:
			- "member": Access as property (e.g., React.useState)
			- "named_import": Each attribute is a named import (e.g., import { useState } from "react")
		constructors: Set of names that are constructors (emit with 'new')
		components: Set of names that are components (wrapped with Jsx)
	"""

	name: str | None
	py_name: str = ""
	src: str | None = None
	kind: Literal["default", "namespace"] = "namespace"
	values: Literal["member", "named_import"] = "named_import"
	constructors: frozenset[str] = field(default_factory=frozenset)
	components: frozenset[str] = field(default_factory=frozenset)

	@override
	def emit(self, out: list[str]) -> None:
		label = self.py_name or self.name or "JsModule"
		raise TypeError(f"{label} cannot be emitted directly - access an attribute")

	@override
	def render(self) -> VDOMNode:
		label = self.py_name or self.name or "JsModule"
		raise TypeError(f"{label} cannot be rendered directly - access an attribute")

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		label = self.py_name or self.name or "JsModule"
		raise TypeError(f"{label} cannot be called directly - access an attribute")

	@override
	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		return self.get_value(attr)

	@override
	def transpile_subscript(self, key: ast.expr, ctx: Transpiler) -> Expr:
		label = self.py_name or self.name or "JsModule"
		raise TypeError(f"{label} cannot be subscripted")

	@property
	def is_builtin(self) -> bool:
		return self.src is None

	def to_expr(self) -> Identifier | Import:
		"""Generate the appropriate Expr for this module.

		Returns Identifier for builtins, Import for external modules.

		Raises TranspileError if name is None (module imports are disallowed).
		"""
		if self.name is None:
			label = self.py_name or "JS global module"
			# If a module has no JS module expression, importing it as a module value is meaningless.
			# Users should import members from the Python module instead.
			if self.py_name:
				msg = (
					f"Cannot import module '{label}' directly. "
					+ f"Use 'from {self.py_name} import ...' instead."
				)
			else:
				msg = f"Cannot import module '{label}' directly."
			raise TranspileError(msg)

		if self.src is None:
			return Identifier(self.name)

		import_kind = "default" if self.kind == "default" else "named"
		return Import(self.name, self.src, kind=import_kind)

	def get_value(self, name: str) -> Member | Class | Jsx | Identifier | Import:
		"""Get a member of this module as an expression.

		For global-identifier modules (name=None): returns Identifier directly (e.g., Set -> Set)
			These are "virtual" Python modules exposing JS globals - no actual JS module exists.
		For builtin namespaces (src=None): returns Member (e.g., Math.floor)
		For external modules with "member" style: returns Member (e.g., React.useState)
		For external modules with "named_import" style: returns a named Import

		If name is in constructors, returns a Class that emits `new ...(...)`.
		If name is in components, returns a Jsx-wrapped expression.
		"""
		# Convention: trailing underscore escapes Python keywords (e.g. from_ -> from, is_ -> is).
		# We keep the original `name` for constructor detection, but emit the JS name.
		js_name = name[:-1] if name.endswith("_") else name

		expr: Member | Identifier | Import
		if self.name is None:
			# Virtual module exposing JS globals - members are just identifiers
			expr = Identifier(js_name)
		elif self.src is None:
			# Builtin namespace (Math, console, etc.) - members accessed as properties
			expr = Member(Identifier(self.name), js_name)
		elif self.values == "named_import":
			expr = Import(js_name, self.src)
		else:
			expr = Member(self.to_expr(), js_name)

		if name in self.constructors:
			return Class(expr, name=name)
		if name in self.components:
			return Jsx(expr)
		return expr

	@override
	@staticmethod
	def register(  # pyright: ignore[reportIncompatibleMethodOverride]
		*,
		name: str | None,
		src: str | None = None,
		kind: Literal["default", "namespace"] = "namespace",
		values: Literal["member", "named_import"] = "named_import",
	) -> None:
		"""Register the calling Python module as a JavaScript module binding.

			Must be called from within the module being registered. The module is
			automatically detected from the call stack.

			This function sets up __getattr__ on the module for dynamic attribute access,
			and registers the module object in EXPR_REGISTRY so it can be used as a
			dependency (e.g., `import pulse.js.math as Math`) during transpilation.

			Args:
				name: The JavaScript identifier for the module binding (e.g., "Math"), or None
					for modules that expose only global identifiers and cannot be imported as a whole.
				src: Import source path. None for builtins.
				kind: Import kind - "default" or "namespace"
				values: How attribute access works:
					- "member": Access as property (e.g., Math.sin, React.useState)
					- "named_import": Each attribute is a named import

		Example (inside pulse/js/math.py):
			JsModule.register(name="Math")  # builtin

		Example (inside pulse/js/react.py):
			JsModule.register(name="React", src="react")  # namespace + named imports

		Example (inside pulse/js/set.py):
			JsModule.register(name=None)  # global identifier builtin (no module binding)
		"""
		from pulse.component import Component  # Import here to avoid cycles

		# Get the calling module from the stack frame
		frame = inspect.currentframe()
		assert frame is not None and frame.f_back is not None
		module_name = frame.f_back.f_globals["__name__"]
		module = sys.modules[module_name]

		# Collect locally defined names and clean up module namespace.
		# Priority order for categorization:
		#   1. Overrides: real functions (with body), Exprs, real @components → returned directly
		#   2. Components: stub @component functions → wrapped as Jsx(Import(...))
		#   3. Constructors: classes → emitted with 'new' keyword
		#   4. Regular imports: stub functions → standard named imports
		constructors: set[str] = set()
		components: set[str] = set()
		local_names: set[str] = set()
		overrides: dict[str, Any] = {}

		for attr_name in list(vars(module)):
			if attr_name in _MODULE_DUNDERS or attr_name.startswith("_"):
				continue

			obj = getattr(module, attr_name)

			# Component-wrapped function - check the raw function's module
			if isinstance(obj, Component):
				raw_fn = obj._raw_fn  # pyright: ignore[reportPrivateUsage]
				fn_module = getattr(raw_fn, "__module__", None)
				if fn_module != module_name:
					delattr(module, attr_name)
					continue
				if is_stub_function(raw_fn):
					# Stub component → becomes Jsx(Import(...))
					components.add(attr_name)
					local_names.add(attr_name)
				else:
					# Real component → preserve as override
					overrides[attr_name] = obj
				delattr(module, attr_name)
				continue

			is_local = not hasattr(obj, "__module__") or obj.__module__ == module_name
			if not is_local:
				delattr(module, attr_name)
				continue

			# Existing Expr (e.g., manually created Jsx)
			if isinstance(obj, Expr):
				overrides[attr_name] = obj
				delattr(module, attr_name)
				continue

			# Real function with body → preserve as override
			if inspect.isfunction(obj) and not is_stub_function(obj):
				overrides[attr_name] = obj
				delattr(module, attr_name)
				continue

			# Class → constructor (existing behavior)
			if inspect.isclass(obj):
				constructors.add(attr_name)
				local_names.add(attr_name)
				delattr(module, attr_name)
				continue

			# Stub function → regular import (existing behavior)
			local_names.add(attr_name)
			delattr(module, attr_name)

		# Add annotated constants to local_names
		if hasattr(module, "__annotations__"):
			for ann_name in module.__annotations__:
				if not ann_name.startswith("_"):
					local_names.add(ann_name)
			module.__annotations__.clear()

		# Invariants: a module without a JS module binding cannot be imported from a JS source.
		if name is None and src is not None:
			raise ValueError("name=None is only supported for builtins (src=None)")

		js_module = JsModule(
			name=name,
			py_name=module.__name__,
			src=src,
			kind=kind,
			values=values,
			constructors=frozenset(constructors),
			components=frozenset(components),
		)
		# Register the module object itself so `import pulse.js.math as Math` resolves via EXPR_REGISTRY.
		Expr.register(module, js_module)

		def __getattr__(name: str) -> Member | Class | Jsx | Identifier | Import | Any:
			if name in overrides:
				return overrides[name]
			if name.startswith("_") or name not in local_names:
				raise AttributeError(name)
			return js_module.get_value(name)

		module.__getattr__ = __getattr__  # type: ignore[method-assign]
