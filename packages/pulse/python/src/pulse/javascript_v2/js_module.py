"""Core infrastructure for pulse.js modules."""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from types import FunctionType
from typing import Literal

from pulse.javascript_v2.imports import Import
from pulse.javascript_v2.nodes import JSIdentifier, JSMember


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


def setup_js_module() -> None:
	"""Call at end of a pulse.js.* module to replace stubs with JSMember expressions.

	Expects __js__ to be defined at module level with a JsModuleConfig.

	This replaces all public functions and uninitialized annotations with
	JSMember instances for use in transpilation.
	"""

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

	# Replace functions with JSMember
	for name in list(vars(module)):
		if name.startswith("_"):
			continue
		value = getattr(module, name)
		if isinstance(value, FunctionType):
			setattr(module, name, JSMember(JSIdentifier(config.name), name))

	# Handle annotated but unassigned attributes
	annotations = getattr(module, "__annotations__", {})
	for name in annotations:
		if name.startswith("_"):
			continue
		if not hasattr(module, name) or getattr(module, name) is None:
			setattr(module, name, JSMember(JSIdentifier(config.name), name))

	# Set up __getattr__ for dynamic access
	def __getattr__(name: str) -> JSMember:
		if name.startswith("_"):
			raise AttributeError(name)
		return JSMember(JSIdentifier(config.name), name)

	module.__getattr__ = __getattr__  # type: ignore[method-assign]
