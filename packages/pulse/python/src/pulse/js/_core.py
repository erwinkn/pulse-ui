"""Core infrastructure for pulse.js modules."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import FunctionType
from typing import Any, Final, Literal, final, override


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


@final
class JsValue:
	"""A marker for a JavaScript value. Raises on any operation."""

	__slots__: Final = ("_module", "_name")

	def __init__(self, module: str, name: str) -> None:
		self._module = module
		self._name = name

	def _error(self, op: str = "accessed") -> JsModuleError:
		module = object.__getattribute__(self, "_module")
		name = object.__getattribute__(self, "_name")
		msg = f"pulse.js.{module}.{name} cannot be {op} at runtime. Use only within @javascript decorated functions."
		return JsModuleError(msg)

	@override
	def __repr__(self) -> str:
		module = object.__getattribute__(self, "_module")
		name = object.__getattribute__(self, "_name")
		return f"<JsValue {module}.{name}>"

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
		module = object.__getattribute__(self, "_module")
		name = object.__getattribute__(self, "_name")
		return hash((module, name))


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

	# Short name for JsValue (e.g., "math")
	short_name = module.__name__.rsplit(".", 1)[-1]

	# Replace functions with JsValue
	for name in list(vars(module)):
		if name.startswith("_"):
			continue
		value = getattr(module, name)
		if isinstance(value, FunctionType):
			setattr(module, name, JsValue(short_name, name))

	# Handle annotated but unassigned attributes
	annotations = getattr(module, "__annotations__", {})
	for name in annotations:
		if name.startswith("_"):
			continue
		if not hasattr(module, name) or getattr(module, name) is None:
			setattr(module, name, JsValue(short_name, name))

	# Set up __getattr__ for dynamic access
	def __getattr__(name: str) -> JsValue:
		if name.startswith("_"):
			raise AttributeError(name)
		return JsValue(short_name, name)

	module.__getattr__ = __getattr__  # type: ignore[method-assign]
