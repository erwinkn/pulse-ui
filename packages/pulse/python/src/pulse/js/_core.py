"""Core infrastructure for pulse.js modules."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import FunctionType
from typing import TYPE_CHECKING, Any, Final, Literal, final, override

if TYPE_CHECKING:
	from pulse.javascript_v2.imports import Import


class JsModuleError(Exception):
	"""Raised when a JS module member is accessed at runtime."""


@dataclass(frozen=True)
class JsModuleConfig:
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

	@classmethod
	def builtin(cls, name: str) -> JsModuleConfig:
		"""Create a builtin module config (no import needed)."""
		return cls(name=name, src=None)

	@classmethod
	def named(cls, name: str, src: str) -> JsModuleConfig:
		"""Create a named import module: import { name } from "src" """
		return cls(name=name, src=src, kind="named")

	@classmethod
	def default(cls, name: str, src: str) -> JsModuleConfig:
		"""Create a default import module: import name from "src" """
		return cls(name=name, src=src, kind="default")

	@classmethod
	def namespace(cls, name: str, src: str) -> JsModuleConfig:
		"""Create a namespace import: import * as name from "src" """
		return cls(name=name, src=src, kind="namespace")

	def to_import(self) -> Import | None:
		"""Generate an Import object for non-builtin modules.

		Returns None for builtin modules (no import needed).
		"""
		if self.is_builtin:
			return None

		from pulse.javascript_v2.imports import Import

		assert self.src is not None
		if self.kind == "default":
			return Import.default(self.name, self.src)
		elif self.kind == "namespace":
			# Namespace imports use default import mechanics with a different emit
			return Import.default(self.name, self.src)
		else:  # named
			return Import.named(self.name, self.src)


@final
class JsValue:
	"""A marker for a JavaScript value. Raises on any operation.

	Contains all information needed for transpilation:
	- config: The JsModuleConfig for the parent module
	- name: The value/function name within the module

	During transpilation, this becomes JSMember(config.name, name) for properties
	or JSMemberCall(config.name, name, args) for function calls.
	"""

	__slots__: Final = ("config", "name")
	config: JsModuleConfig
	name: str

	def __init__(self, config: JsModuleConfig, name: str) -> None:
		self.config = config
		self.name = name

	@property
	def js_module_name(self) -> str:
		"""The JavaScript module name (e.g., 'Math')."""
		return self.config.name

	def _error(self, op: str = "accessed") -> JsModuleError:
		msg = f"{self.config.name}.{self.name} cannot be {op} at runtime. Use only within @javascript decorated functions."
		return JsModuleError(msg)

	@override
	def __repr__(self) -> str:
		return f"<JsValue {self.config.name}.{self.name}>"

	# Raise on any operation
	def __getattr__(self, name: str) -> Any:
		raise self._error("accessed")

	def __call__(self, *args: Any, **kwargs: Any) -> Any:
		raise self._error("called")

	def __add__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __radd__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __sub__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __rsub__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __mul__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __rmul__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __truediv__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __rtruediv__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __floordiv__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __rfloordiv__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __mod__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __rmod__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __pow__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __rpow__(self, other: Any) -> Any:
		raise self._error("used in expression")

	def __neg__(self) -> Any:
		raise self._error("used in expression")

	def __pos__(self) -> Any:
		raise self._error("used in expression")

	def __bool__(self) -> Any:
		raise self._error("used in boolean context")

	@override
	def __eq__(self, other: Any) -> Any:  # type: ignore[override]
		raise self._error("compared")

	@override
	def __ne__(self, other: Any) -> Any:  # type: ignore[override]
		raise self._error("compared")

	def __lt__(self, other: Any) -> Any:
		raise self._error("compared")

	def __le__(self, other: Any) -> Any:
		raise self._error("compared")

	def __gt__(self, other: Any) -> Any:
		raise self._error("compared")

	def __ge__(self, other: Any) -> Any:
		raise self._error("compared")

	def __iter__(self) -> Any:
		raise self._error("iterated")

	def __getitem__(self, key: Any) -> Any:
		raise self._error("subscripted")

	@override
	def __hash__(self) -> int:
		# Allow hashing so it can be used in sets/dicts for tracking
		return hash((self.config.name, self.name))


def setup_js_module() -> None:
	"""Call at end of a pulse.js.* module to replace stubs with JsValue markers.

	Expects __js__ to be defined at module level with a JsModuleConfig.

	This replaces all public functions and uninitialized annotations with
	JsValue instances that raise when used at runtime.
	"""
	import inspect

	# Get the calling module
	frame = inspect.currentframe()
	assert frame is not None and frame.f_back is not None
	caller_globals = frame.f_back.f_globals
	module = sys.modules[caller_globals["__name__"]]

	# Get the JsModuleConfig from the module
	config = caller_globals.get("__js__")
	if not isinstance(config, JsModuleConfig):
		raise RuntimeError(
			f"Module {module.__name__} must define __js__ = JsModuleConfig(...) before calling setup_js_module()"
		)

	# Replace functions with JsValue
	for name in list(vars(module)):
		if name.startswith("_"):
			continue
		value = getattr(module, name)
		if isinstance(value, FunctionType):
			setattr(module, name, JsValue(config, name))

	# Handle annotated but unassigned attributes
	annotations = getattr(module, "__annotations__", {})
	for name in annotations:
		if name.startswith("_"):
			continue
		if not hasattr(module, name) or getattr(module, name) is None:
			setattr(module, name, JsValue(config, name))

	# Set up __getattr__ for dynamic access
	def __getattr__(name: str) -> JsValue:
		if name.startswith("_"):
			raise AttributeError(name)
		return JsValue(config, name)

	module.__getattr__ = __getattr__  # type: ignore[method-assign]
