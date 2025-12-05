"""Core infrastructure for JavaScript module bindings.

JS modules are Python modules that map to JavaScript modules/builtins.
Registration is done by calling register_js_module() from within the module itself.
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Literal

from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import JSIdentifier, JSMember


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
	"""

	name: str
	src: str | None = None
	kind: Literal["default", "namespace"] = "namespace"
	values: Literal["member", "named_import"] = "named_import"

	@property
	def is_builtin(self) -> bool:
		return self.src is None

	def to_js_expr(self) -> JSIdentifier | Import:
		"""Generate the appropriate JSExpr for this module.

		Returns JSIdentifier for builtins, Import for external modules.
		"""
		if self.src is None:
			return JSIdentifier(self.name)

		if self.kind == "default":
			return Import.default(self.name, self.src)
		return Import.namespace(self.name, self.src)

	def get_value(self, name: str) -> JSMember | Import:
		"""Get a member of this module as a JS expression.

		For builtins: always returns JSMember (e.g., Math.sin)
		For external modules with "member" style: returns JSMember (e.g., React.useState)
		For external modules with "named_import" style: returns a named Import (e.g., import { useState } from "react")
		"""
		# Builtins always use member access (kind/values are ignored)
		if self.src is None:
			return JSMember(JSIdentifier(self.name), name)
		if self.values == "named_import":
			return Import.named(name, self.src)
		return JSMember(self.to_js_expr(), name)


# Registry: Python module -> JsModule config
JS_MODULES: dict[ModuleType, JsModule] = {}


def register_js_module(
	*,
	name: str,
	src: str | None = None,
	kind: Literal["default", "namespace"] = "namespace",
	values: Literal["member", "named_import"] = "named_import",
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

	Example (inside pulse/js/math.py):
		register_js_module(name="Math")  # builtin

	Example (inside pulse/js/react.py):
		register_js_module(name="React", src="react")  # namespace + named imports (default)
	"""
	# Get the calling module from the stack frame
	frame = inspect.currentframe()
	assert frame is not None and frame.f_back is not None
	module_name = frame.f_back.f_globals["__name__"]
	module = sys.modules[module_name]

	js_module = JsModule(name=name, src=src, kind=kind, values=values)
	JS_MODULES[module] = js_module

	# Delete all public functions so everything goes through __getattr__
	from types import FunctionType

	for attr_name in list(vars(module)):
		if attr_name.startswith("_"):
			continue
		if isinstance(getattr(module, attr_name), FunctionType):
			delattr(module, attr_name)

	# Clear annotations (they're just for IDE hints, not runtime values)
	if hasattr(module, "__annotations__"):
		module.__annotations__.clear()

	# Set up __getattr__ - all attribute access now goes through here
	def __getattr__(name: str) -> JSMember | Import:
		if name.startswith("_"):
			raise AttributeError(name)
		return js_module.get_value(name)

	module.__getattr__ = __getattr__  # type: ignore[method-assign]
