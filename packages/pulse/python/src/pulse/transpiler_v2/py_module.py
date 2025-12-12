"""Python module transpilation system for transpiler_v2.

Provides infrastructure for mapping Python modules (like `math`) to JavaScript equivalents.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from types import ModuleType
from typing import TYPE_CHECKING, Any, ClassVar, cast, override

from pulse.transpiler_v2.nodes import ExprNode, Primitive, Transformer

if TYPE_CHECKING:
	from pulse.transpiler_v2.transpiler import Transpiler


class PyModule(ExprNode):
	"""ExprNode for a Python module imported as a whole (e.g., `import math`).

	Subclasses can define transpiler mappings as class attributes:
	- ExprNode attributes are used directly
	- Callable attributes are wrapped in Transformer
	- Primitives are converted via ExprNode.of()

	The transpiler dict is built automatically via __init_subclass__.
	"""

	__slots__ = ("transpiler", "name")

	# Class-level transpiler template, built by __init_subclass__
	_transpiler: ClassVar[dict[str, ExprNode]] = {}

	transpiler: dict[str, ExprNode]
	name: str

	def __init__(self, transpiler: dict[str, ExprNode] | None = None, name: str = ""):
		self.transpiler = transpiler if transpiler is not None else {}
		self.name = name

	def __init_subclass__(cls, **kwargs: Any) -> None:
		super().__init_subclass__(**kwargs)
		cls._transpiler = {}
		for attr_name in dir(cls):
			if attr_name.startswith("_"):
				continue
			attr = getattr(cls, attr_name)
			if isinstance(attr, ExprNode):
				cls._transpiler[attr_name] = attr
			elif callable(attr):
				cls._transpiler[attr_name] = Transformer(
					cast(Callable[..., ExprNode], attr), name=attr_name
				)
			elif isinstance(attr, (bool, int, float, str)) or attr is None:
				cls._transpiler[attr_name] = ExprNode.of(attr)

	@override
	def emit(self, out: list[str]) -> None:
		label = self.name or "PyModule"
		raise TypeError(f"{label} cannot be emitted directly")

	@override
	def emit_call(
		self,
		args: list[Any],
		kwargs: dict[str, Any],
		ctx: Transpiler,
	) -> ExprNode:
		label = self.name or "PyModule"
		raise TypeError(f"{label} cannot be called directly")

	@override
	def emit_getattr(self, attr: str, ctx: Transpiler) -> ExprNode:
		if attr not in self.transpiler:
			label = self.name or "Module"
			raise TypeError(f"{label} has no attribute '{attr}'")
		return self.transpiler[attr]

	@override
	def emit_subscript(self, key: Any, ctx: Transpiler) -> ExprNode:
		label = self.name or "PyModule"
		raise TypeError(f"{label} cannot be subscripted")

	@staticmethod
	def _build_transpiler(items: Iterable[tuple[str, Any]]) -> dict[str, ExprNode]:
		"""Build transpiler dict from name/value pairs."""
		result: dict[str, ExprNode] = {}
		for attr_name, attr in items:
			if isinstance(attr, ExprNode):
				result[attr_name] = attr
			elif callable(attr):
				result[attr_name] = Transformer(
					cast(Callable[..., ExprNode], attr), name=attr_name
				)
			elif isinstance(attr, (bool, int, float, str)) or attr is None:
				result[attr_name] = ExprNode.of(attr)
		return result

	@staticmethod
	def register(  # pyright: ignore[reportIncompatibleMethodOverride, reportImplicitOverride]
		module: ModuleType,
		transpilation: type[PyModule]
		| dict[str, ExprNode | Primitive | Callable[..., ExprNode]],
	) -> None:
		"""Register a Python module for transpilation.

		Args:
			module: The Python module to register (e.g., `math`)
			transpilation: Either a PyModule subclass or a dict mapping attribute names to:
				- ExprNode: used directly
				- Primitive (bool, int, float, str, None): converted via ExprNode.of()
				- Callable[..., ExprNode]: wrapped in Transformer
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
				ExprNode.register(module_value, expr)

		# Register the module object itself
		ExprNode.register(module, PyModule(transpiler_dict, name=module.__name__))
