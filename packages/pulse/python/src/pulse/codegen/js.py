# Placeholders for the WIP JS compilation feature
# NOTE: This module is deprecated. Use pulse.transpiler instead.

from collections.abc import Callable
from typing import Generic, TypeVar, TypeVarTuple

from pulse.transpiler.imports import Import

Args = TypeVarTuple("Args")
R = TypeVar("R")


class JsFunction(Generic[*Args, R]):
	"A transpiled JS function (deprecated - use pulse.transpiler.function.JsFunction)"

	name: str
	hint: Callable[[*Args], R]

	def __init__(
		self,
		name: str,
		hint: Callable[[*Args], R],
	) -> None:
		self.name = name
		self.hint = hint

	def __call__(self, *args: *Args) -> R: ...


class ExternalJsFunction(Generic[*Args, R]):
	"An imported JS function (deprecated - use pulse.transpiler.imports.Import)"

	import_: Import
	hint: Callable[[*Args], R]
	_prop: str | None

	def __init__(
		self,
		name: str,
		src: str,
		*,
		prop: str | None = None,
		is_default: bool,
		hint: Callable[[*Args], R],
	) -> None:
		kind = "default" if is_default else "named"
		self.import_ = Import(name, src, kind=kind)
		self._prop = prop
		self.hint = hint

	@property
	def name(self) -> str:
		return self.import_.name

	@property
	def src(self) -> str:
		return self.import_.src

	@property
	def is_default(self) -> bool:
		return self.import_.is_default

	@property
	def prop(self) -> str | None:
		return self._prop

	@property
	def expr(self) -> str:
		base = self.import_.js_name
		if self._prop:
			return f"{base}.{self._prop}"
		return base

	def __call__(self, *args: *Args) -> R: ...
