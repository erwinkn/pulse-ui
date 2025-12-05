"""Core infrastructure for JavaScript module bindings.

JS modules are Python modules that map to JavaScript modules/builtins.
Registration is done by calling register_js_module() from within the module itself.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from types import FunctionType, ModuleType
from typing import Literal, TypeVar, override

from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import JSExpr, JSIdentifier, JSMember, JSNew

# Track functions marked as constructors (by id, since we delete them)
CONSTRUCTORS: set[int] = set()

F = TypeVar("F", bound=Callable[..., object])


# def constructor(fn: F) -> F:
# 	"""Mark a function stub as a JavaScript constructor.

# 	When called, this will emit 'new Ctor(...)' instead of 'Ctor(...)'.

# 	Usage:
# 		@constructor
# 		def Set(iterable: list[object] | None = None) -> object: ...
# 	"""
# 	CONSTRUCTORS.add(id(fn))
# 	return fn


@dataclass(frozen=True)
class JsModule:
	"""Configuration for a JavaScript module binding.

	Attributes:
		name: The JavaScript identifier (e.g., "Math", "lodash")
		src: Import source path. None for builtins.
		kind: Import kind - "default" or "namespace"
		values: How attribute access is expressed:
			- "member": Access as property (e.g., React.useState)
			- "named_import": Each attribute is a named import (e.g., import { useState } from "react")
		constructors: Set of names that are constructors (emit with 'new')
		global_scope: If True, members are registered in global scope. Module imports are disallowed.
	"""

	name: str
	src: str | None = None
	kind: Literal["default", "namespace"] = "namespace"
	values: Literal["member", "named_import"] = "named_import"
	constructors: frozenset[str] = field(default_factory=frozenset)
	global_scope: bool = False

	@property
	def is_builtin(self) -> bool:
		return self.src is None

	def to_js_expr(self) -> JSIdentifier | Import:
		"""Generate the appropriate JSExpr for this module.

		Returns JSIdentifier for builtins, Import for external modules.

		Raises JSCompilationError if global_scope=True (module imports are disallowed).
		"""
		if self.global_scope:
			module_name_lower = self.name.lower()
			msg = (
				f"Cannot import module '{self.name}' directly. "
				+ f"Use 'from pulse.js.{module_name_lower} import ...' instead."
			)
			raise JSCompilationError(msg)

		if self.src is None:
			return JSIdentifier(self.name)

		if self.kind == "default":
			return Import.default(self.name, self.src)
		return Import.namespace(self.name, self.src)

	def get_value(self, name: str) -> JSMember | JSConstructor | JSIdentifier | Import:
		"""Get a member of this module as a JS expression.

		For global_scope modules: returns JSIdentifier(name) directly (e.g., Set -> Set)
		For builtins: returns JSMember (e.g., Math.sin), or JSIdentifier if name
			matches the module name (e.g., Set -> Set, not Set.Set)
		For external modules with "member" style: returns JSMember (e.g., React.useState)
		For external modules with "named_import" style: returns a named Import (e.g., import { useState } from "react")

		If name is in constructors, wraps the result in JSConstructor.
		"""
		expr: JSMember | JSIdentifier | Import
		if self.global_scope:
			# Global scope: members are just identifiers, not members of a module
			expr = JSIdentifier(name)
		elif self.src is None:
			# Builtins: use identifier when name matches module name (Set.Set -> Set)
			if name == self.name:
				expr = JSIdentifier(name)
			else:
				expr = JSMember(JSIdentifier(self.name), name)
		elif self.values == "named_import":
			expr = Import.named(name, self.src)
		else:
			expr = JSMember(self.to_js_expr(), name)

		if name in self.constructors:
			return JSConstructor(expr)
		return expr


@dataclass
class JSConstructor(JSExpr):
	"""Wrapper that emits constructor calls with 'new' keyword.

	When this expression is called, it produces JSNew instead of JSCall.
	"""

	ctor: JSExpr
	is_primary: bool = True

	@override
	def emit(self) -> str:
		return self.ctor.emit()

	@override
	def emit_call(self, args: list[JSExpr], kwargs: dict[str, JSExpr]) -> JSExpr:
		if kwargs:
			raise JSCompilationError(
				"Keyword arguments not supported in constructor call"
			)
		return JSNew(self.ctor, args)


# Registry: Python module -> JsModule config
JS_MODULES: dict[ModuleType, JsModule] = {}


def register_js_module(
	*,
	name: str,
	src: str | None = None,
	kind: Literal["default", "namespace"] = "namespace",
	values: Literal["member", "named_import"] = "named_import",
	global_scope: bool = False,
) -> None:
	"""Register the calling Python module as a JavaScript module binding.

	Must be called from within the module being registered. The module is
	automatically detected from the call stack.

	This function:
	1. Creates a JsModule config and adds it to JS_MODULES
	2. Sets up __getattr__ on the module for dynamic attribute access

	Args:
		name: The JavaScript identifier (e.g., "Math")
		src: Import source path. None for builtins.
		kind: Import kind - "default" or "namespace"
		values: How attribute access works:
			- "member": Access as property (e.g., Math.sin, React.useState)
			- "named_import": Each attribute is a named import (e.g., import { useState } from "react")
		global_scope: If True, members are registered in global scope. Module imports
			(e.g., `import pulse.js.set as Set`) are disallowed. Members are transpiled
			as direct identifiers (e.g., `Set` -> `Set`, not `Set.Set`).

	Example (inside pulse/js/math.py):
		register_js_module(name="Math")  # builtin

	Example (inside pulse/js/react.py):
		register_js_module(name="React", src="react")  # namespace + named imports (default)

	Example (inside pulse/js/set.py):
		register_js_module(name="Set", global_scope=True)  # global scope builtin
	"""
	# Get the calling module from the stack frame
	frame = inspect.currentframe()
	assert frame is not None and frame.f_back is not None
	module_name = frame.f_back.f_globals["__name__"]
	module = sys.modules[module_name]

	# Collect constructor names before deleting functions/classes
	# Classes are automatically treated as constructors
	# Only items defined in this module are considered (not imported ones)
	# Track locally defined names so __getattr__ can distinguish them from imported ones

	def is_defined_in_module(obj: object) -> bool:
		"""Check if an object is defined in the current module (not imported)."""
		return hasattr(obj, "__module__") and obj.__module__ == module_name

	ctor_names: set[str] = set()
	locally_defined_names: set[str] = set()

	for attr_name in list(vars(module)):
		# Skip special module attributes
		if attr_name in (
			"__name__",
			"__file__",
			"__doc__",
			"__package__",
			"__path__",
			"__cached__",
			"__loader__",
			"__spec__",
		):
			continue
		attr = getattr(module, attr_name)
		# Check if this is an imported name (has __module__ that doesn't match)
		is_imported = hasattr(attr, "__module__") and attr.__module__ != module_name
		if isinstance(attr, FunctionType):
			# Functions without __module__ are assumed to be locally defined (stub functions)
			if not is_imported and (
				not hasattr(attr, "__module__") or is_defined_in_module(attr)
			):
				# Only track non-underscore-prefixed names for exports
				if not attr_name.startswith("_"):
					locally_defined_names.add(attr_name)
					if id(attr) in CONSTRUCTORS:
						ctor_names.add(attr_name)
				delattr(module, attr_name)
			else:
				# Delete imported functions (including underscore-prefixed)
				delattr(module, attr_name)
		elif inspect.isclass(attr):
			# Only consider classes defined in this module (not imported)
			if not is_imported and is_defined_in_module(attr):
				# Only track non-underscore-prefixed names for exports
				if not attr_name.startswith("_"):
					locally_defined_names.add(attr_name)
					ctor_names.add(attr_name)
				delattr(module, attr_name)
			else:
				# Delete imported classes (including underscore-prefixed)
				delattr(module, attr_name)
		elif is_imported:
			# Delete all imported objects (TypeVar, Generic, etc.) including underscore-prefixed
			delattr(module, attr_name)
		else:
			# For objects without __module__, assume they're locally defined
			# (constants, etc.) - but constants are usually just annotations
			# so they won't be in vars(module) anyway
			if not attr_name.startswith("_"):
				locally_defined_names.add(attr_name)
			delattr(module, attr_name)

	# Collect constant names from annotations (constants are just type annotations)
	# before clearing them
	constant_names: set[str] = set()
	if hasattr(module, "__annotations__"):
		for ann_name in module.__annotations__:
			if not ann_name.startswith("_") and ann_name not in locally_defined_names:
				constant_names.add(ann_name)
		# Clear annotations (they're just for IDE hints, not runtime values)
		module.__annotations__.clear()

	js_module = JsModule(
		name=name,
		src=src,
		kind=kind,
		values=values,
		constructors=frozenset(ctor_names),
		global_scope=global_scope,
	)
	JS_MODULES[module] = js_module

	# Include constants in locally_defined_names so they're accessible via __getattr__
	locally_defined_names.update(constant_names)

	# Set up __getattr__ - all attribute access now goes through here
	# Capture locally_defined_names in closure
	_defined_names = locally_defined_names

	def __getattr__(name: str) -> JSMember | JSConstructor | JSIdentifier | Import:
		if name.startswith("_"):
			raise AttributeError(name)
		# Only allow access to locally defined names (functions, classes, constants)
		if name not in _defined_names:
			raise AttributeError(name)
		return js_module.get_value(name)

	module.__getattr__ = __getattr__  # type: ignore[method-assign]
