"""Python module transpilation system for transpiler_v2.

Provides infrastructure for mapping Python modules (like `math`) to JavaScript equivalents.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from types import ModuleType
from typing import TYPE_CHECKING, Any, ClassVar, cast, override

from pulse.transpiler_v2.nodes import Expr, Primitive, Transformer

if TYPE_CHECKING:
	from pulse.transpiler_v2.transpiler import Transpiler


class PyModule(Expr):
	"""Expr for a Python module imported as a whole (e.g., `import math`).

	Subclasses can define transpiler mappings as class attributes:
	- Expr attributes are used directly
	- Callable attributes are wrapped in Transformer
	- Primitives are converted via Expr.of()

	The transpiler dict is built automatically via __init_subclass__.
	"""

	__slots__: tuple[str, str] = ("transpiler", "name")

	# Class-level transpiler template, built by __init_subclass__
	_transpiler: ClassVar[dict[str, Expr]] = {}

	transpiler: dict[str, Expr]
	name: str

	def __init__(self, transpiler: dict[str, Expr] | None = None, name: str = ""):
		self.transpiler = transpiler if transpiler is not None else {}
		self.name = name

	def __init_subclass__(cls, **kwargs: Any) -> None:
		super().__init_subclass__(**kwargs)
		cls._transpiler = {}
		for attr_name in dir(cls):
			if attr_name.startswith("_"):
				continue
			attr = getattr(cls, attr_name)
			if isinstance(attr, Expr):
				cls._transpiler[attr_name] = attr
			elif callable(attr):
				cls._transpiler[attr_name] = Transformer(
					cast(Callable[..., Expr], attr), name=attr_name
				)
			elif isinstance(attr, (bool, int, float, str)) or attr is None:
				cls._transpiler[attr_name] = Expr.of(attr)

	@override
	def emit(self, out: list[str]) -> None:
		label = self.name or "PyModule"
		raise TypeError(f"{label} cannot be emitted directly")

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		kwargs: dict[str, ast.expr],
		ctx: Transpiler,
	) -> Expr:
		label = self.name or "PyModule"
		raise TypeError(f"{label} cannot be called directly")

	@override
	def transpile_getattr(self, attr: str, ctx: Transpiler) -> Expr:
		if attr not in self.transpiler:
			label = self.name or "Module"
			raise TypeError(f"{label} has no attribute '{attr}'")
		return self.transpiler[attr]

	@override
	def transpile_subscript(self, key: ast.expr, ctx: Transpiler) -> Expr:
		label = self.name or "PyModule"
		raise TypeError(f"{label} cannot be subscripted")

	@staticmethod
	def _build_transpiler(items: Iterable[tuple[str, Any]]) -> dict[str, Expr]:
		"""Build transpiler dict from name/value pairs."""
		result: dict[str, Expr] = {}
		for attr_name, attr in items:
			if isinstance(attr, Expr):
				result[attr_name] = attr
			elif callable(attr):
				result[attr_name] = Transformer(
					cast(Callable[..., Expr], attr), name=attr_name
				)
			elif isinstance(attr, (bool, int, float, str)) or attr is None:
				result[attr_name] = Expr.of(attr)
		return result

	@staticmethod
	def register(  # pyright: ignore[reportIncompatibleMethodOverride, reportImplicitOverride]
		module: ModuleType,
		transpilation: type[PyModule]
		| dict[str, Expr | Primitive | Callable[..., Expr]],
	) -> None:
		"""Register a Python module for transpilation.

		Args:
			module: The Python module to register (e.g., `math`)
			transpilation: Either a PyModule subclass or a dict mapping attribute names to:
				- Expr: used directly
				- Primitive (bool, int, float, str, None): converted via Expr.of()
				- Callable[..., Expr]: wrapped in Transformer
		"""
		# Get transpiler dict - use pre-built _transpiler for PyModule subclasses
		if isinstance(transpilation, dict):
			transpiler_dict = PyModule._build_transpiler(transpilation.items())
		elif hasattr(transpilation, "_transpiler"):
			transpiler_dict = transpilation._transpiler
		else:
			# Legacy: class namespace without PyModule inheritance
			items = (
				(name, getattr(transpilation, name))
				for name in dir(transpilation)
				if not name.startswith("_")
			)
			transpiler_dict = PyModule._build_transpiler(items)

		# Register individual values for lookup by id
		for attr_name, expr in transpiler_dict.items():
			module_value = getattr(module, attr_name, None)
			if module_value is not None:
				Expr.register(module_value, expr)

		# Register the module object itself
		Expr.register(module, PyModule(transpiler_dict, name=module.__name__))
