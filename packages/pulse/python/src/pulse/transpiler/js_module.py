"""Core infrastructure for JavaScript module bindings in transpiler.

JS modules are Python modules that map to JavaScript modules/builtins.
Registration is done by calling register_js_module() from within the module itself.
"""

from __future__ import annotations

import ast
import inspect
import sys
from dataclasses import dataclass, field
from typing import Literal, override

from pulse.transpiler.errors import TranspileError
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import (
	Expr,
	Identifier,
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
		kwargs: dict[str, ast.expr],
		ctx: Transpiler,
	) -> Expr:
		if kwargs:
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
	"""

	name: str | None
	py_name: str = ""
	src: str | None = None
	kind: Literal["default", "namespace"] = "namespace"
	values: Literal["member", "named_import"] = "named_import"
	constructors: frozenset[str] = field(default_factory=frozenset)

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
		kwargs: dict[str, ast.expr],
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

	def get_value(self, name: str) -> Member | Class | Identifier | Import:
		"""Get a member of this module as an expression.

		For global-identifier modules (name=None): returns Identifier(name) directly (e.g., Set -> Set)
		For builtins: returns Member (e.g., Math.sin), or Identifier if name
			matches the module name (e.g., Set -> Set, not Set.Set)
		For external modules with "member" style: returns Member (e.g., React.useState)
		For external modules with "named_import" style: returns a named Import

		If name is in constructors, returns a Class that emits `new ...(...)`.
		"""
		# Convention: trailing underscore escapes Python keywords (e.g. from_ -> from, is_ -> is).
		# We keep the original `name` for constructor detection, but emit the JS name.
		js_name = name[:-1] if name.endswith("_") else name

		expr: Member | Identifier | Import
		if self.name is None:
			# No module expression: members are just identifiers, not members of a module
			expr = Identifier(js_name)
		elif self.src is None:
			# Builtins: use identifier when name matches module name (Set.Set -> Set)
			if name == self.name:
				expr = Identifier(js_name)
			else:
				expr = Member(Identifier(self.name), js_name)
		elif self.values == "named_import":
			expr = Import(js_name, self.src)
		else:
			expr = Member(self.to_expr(), js_name)

		if name in self.constructors:
			return Class(expr, name=name)
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
		# Get the calling module from the stack frame
		frame = inspect.currentframe()
		assert frame is not None and frame.f_back is not None
		module_name = frame.f_back.f_globals["__name__"]
		module = sys.modules[module_name]

		# Collect locally defined names and clean up module namespace
		constructors: set[str] = set()
		local_names: set[str] = set()

		for attr_name in list(vars(module)):
			if attr_name in _MODULE_DUNDERS:
				continue

			obj = getattr(module, attr_name)
			is_local = not hasattr(obj, "__module__") or obj.__module__ == module_name

			if is_local and not attr_name.startswith("_"):
				local_names.add(attr_name)
				if inspect.isclass(obj):
					constructors.add(attr_name)

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
		)
		# Register the module object itself so `import pulse.js.math as Math` resolves via EXPR_REGISTRY.
		Expr.register(module, js_module)

		def __getattr__(name: str) -> Member | Class | Identifier | Import:
			if name.startswith("_") or name not in local_names:
				raise AttributeError(name)
			return js_module.get_value(name)

		module.__getattr__ = __getattr__  # type: ignore[method-assign]
