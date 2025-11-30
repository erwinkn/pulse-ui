"""JS Module system for javascript_v2.

Provides base classes for defining JS module bindings with automatic import registration.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any, ClassVar, get_type_hints

from pulse.javascript_v2.imports import Import
from pulse.javascript_v2.nodes import JSExpr, JSIdentifier, JSMember, JSMemberCall


class JsModuleError(Exception):
	"""Raised when a JsModule method or property is accessed at runtime."""


def _make_method_stub(module_name: str, method_name: str):
	"""Create a method stub that raises on call."""

	def stub(*args: Any, **kwargs: Any) -> JSExpr:
		msg = f"JsModule method {module_name}.{method_name}() cannot be called at runtime. These methods are for transpilation only."
		raise JsModuleError(msg)

	stub.__name__ = method_name
	stub.__qualname__ = f"{module_name}.{method_name}"
	return staticmethod(stub)


class _JsPropertyDescriptor:
	"""Descriptor for JS module properties that raises on access."""

	module_name: str
	prop_name: str

	def __init__(self, module_name: str, prop_name: str) -> None:
		self.module_name = module_name
		self.prop_name = prop_name

	def __get__(self, obj: object, owner: type) -> JSExpr:
		msg = f"JsModule property {self.module_name}.{self.prop_name} cannot be accessed at runtime. These properties are for transpilation only."
		raise JsModuleError(msg)


class JsModuleMeta(type):
	"""Metaclass for JsModule that handles automatic import registration."""

	def __new__(
		mcs,
		name: str,
		bases: tuple[type, ...],
		namespace: dict[str, Any],
		**kwargs: Any,
	) -> JsModuleMeta:
		# Get the js_name before class creation (default to class name)
		js_name: str = kwargs.pop("js_name", name)
		js_src: str | None = kwargs.pop("js_src", None)
		is_default: bool = kwargs.pop("is_default", False)

		cls = super().__new__(mcs, name, bases, namespace, **kwargs)

		# Skip base class
		if name == "JsModule" and not bases:
			return cls

		# Store module metadata
		cls._js_name_ = js_name  # pyright: ignore[reportAttributeAccessIssue]
		cls._js_src_ = js_src  # pyright: ignore[reportAttributeAccessIssue]
		cls._js_is_default_ = is_default  # pyright: ignore[reportAttributeAccessIssue]

		# Register import if source is provided
		if js_src is not None:
			from pulse.javascript_v2.imports import Import

			if is_default:
				imp = Import.default(js_name, js_src)
			else:
				imp = Import.named(js_name, js_src)
			cls._js_import_ = imp  # pyright: ignore[reportAttributeAccessIssue]

		# Convert methods to stubs and properties to descriptors
		_setup_stubs(cls, js_name)

		return cls


def _setup_stubs(cls: type, js_name: str) -> None:
	"""Replace methods with stubs and annotated attributes with descriptors."""
	# Get annotations for property handling
	try:
		hints = get_type_hints(cls)
	except Exception:
		hints = getattr(cls, "__annotations__", {})

	# Process methods - replace with stubs
	for attr_name in dir(cls):
		if attr_name.startswith("_"):
			continue

		attr = getattr(cls, attr_name, None)
		if attr is None:
			continue

		# Check if it's a method (function or staticmethod)
		if callable(attr) and not isinstance(attr, type):
			# Don't replace if it's inherited from JsModule base
			if hasattr(JsModule, attr_name):
				continue
			setattr(cls, attr_name, _make_method_stub(js_name, attr_name))

	# Process annotated attributes as properties
	for prop_name in hints:
		if prop_name.startswith("_"):
			continue
		# Only convert if not already set to something else
		if not hasattr(cls, prop_name) or getattr(cls, prop_name, None) is None:
			setattr(cls, prop_name, _JsPropertyDescriptor(js_name, prop_name))


class JsModule(metaclass=JsModuleMeta):
	"""Base class for JS module bindings.

	Usage:
		class Math(JsModule):
			# Properties - just type hints
			PI: JSExpr
			E: JSExpr

			# Methods - just signatures, no body needed
			@staticmethod
			def abs(x: int | float | JSExpr) -> JSExpr: ...

			@staticmethod
			def floor(x: int | float | JSExpr) -> JSExpr: ...

		# For external modules, specify source:
		class lodash(JsModule, js_src="lodash", is_default=True):
			@staticmethod
			def chunk(array: JSExpr, size: int) -> JSExpr: ...

	At transpilation time, use the helper methods to generate JSExpr nodes.
	"""

	_js_name_: ClassVar[str]
	_js_src_: ClassVar[str | None]
	_js_is_default_: ClassVar[bool]
	_js_import_: ClassVar[Import]

	@classmethod
	def _prop(cls, name: str) -> JSExpr:
		"""Generate a property access expression: Module.name"""
		return JSMember(JSIdentifier(cls._js_name_), name)

	@classmethod
	def _call(cls, method: str, *args: JSExpr) -> JSExpr:
		"""Generate a method call expression: Module.method(args)"""
		return JSMemberCall(JSIdentifier(cls._js_name_), method, list(args))


class PyModule:
	"""Base class for Python module transpilation mappings."""


PY_MODULES: dict[ModuleType, type[PyModule]] = {}


def register_module(module: ModuleType, transpilation: type[PyModule]):
	PY_MODULES[module] = transpilation
