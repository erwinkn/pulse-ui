"""Core infrastructure for JavaScript module bindings.

JS modules are Python modules that map to JavaScript modules/builtins.
Registration is external (like Python modules) via register_js_module().
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Literal

from pulse.javascript.imports import Import
from pulse.javascript.nodes import JSIdentifier, JSMember


@dataclass(frozen=True)
class JsModule:
	"""Configuration for a JavaScript module binding.

	Attributes:
		name: The JavaScript identifier (e.g., "Math", "lodash")
		src: Import source path. None for builtins.
		kind: Import kind - "named", "default", or "namespace"
	"""

	name: str
	src: str | None = None
	kind: Literal["named", "default", "namespace"] = "named"

	@property
	def is_builtin(self) -> bool:
		return self.src is None

	def to_js_expr(self) -> JSIdentifier | Import:
		"""Generate the appropriate JSExpr for this module.

		Returns JSIdentifier for builtins, Import for external modules.
		"""
		if self.is_builtin:
			return JSIdentifier(self.name)

		assert self.src is not None
		if self.kind == "default":
			return Import.default(self.name, self.src)
		elif self.kind == "namespace":
			return Import.namespace(self.name, self.src)
		else:  # named
			return Import.named(self.name, self.src)


# Registry: Python module -> JsModule config
JS_MODULES: dict[ModuleType, JsModule] = {}


def register_js_module(
	module: ModuleType,
	*,
	name: str,
	src: str | None = None,
	kind: Literal["named", "default", "namespace"] = "named",
) -> None:
	"""Register a Python module as a JavaScript module binding.

	This function:
	1. Creates a JsModule config and adds it to JS_MODULES
	2. Sets up __getattr__ on the module for dynamic attribute access

	Args:
		module: The Python module to register (e.g., pulse.js.math)
		name: The JavaScript identifier (e.g., "Math")
		src: Import source path. None for builtins.
		kind: Import kind - "named", "default", or "namespace"

	Example:
		import pulse.js.math as math_module
		register_js_module(math_module, name="Math")  # builtin
		register_js_module(lodash_module, name="_", src="lodash", kind="default")
	"""
	js_module = JsModule(name=name, src=src, kind=kind)
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
	def __getattr__(name: str) -> JSMember:
		if name.startswith("_"):
			raise AttributeError(name)
		return JSMember(JSIdentifier(js_module.name), name)

	module.__getattr__ = __getattr__  # type: ignore[method-assign]
