# Placeholders for the WIP JS compilation feature
# NOTE: This module is deprecated. Use pulse.javascript_v2 instead.

from collections.abc import Callable
from typing import Generic, TypeVar, TypeVarTuple

from pulse.javascript_v2.imports import Import

Args = TypeVarTuple("Args")
R = TypeVar("R")


class JsFunction(Generic[*Args, R]):
	"A transpiled JS function (deprecated - use pulse.javascript_v2.function.JsFunction)"

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
	"An imported JS function (deprecated - use pulse.javascript_v2.imports.Import)"

	import_: Import
	hint: Callable[[*Args], R]

	def __init__(
		self,
		name: str,
		src: str,
		*,
		prop: str | None = None,
		is_default: bool,
		hint: Callable[[*Args], R],
	) -> None:
		if is_default:
			self.import_ = Import.default(name, src, prop=prop)
		else:
			self.import_ = Import.named(name, src, prop=prop)
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
		return self.import_.prop

	@property
	def expr(self) -> str:
		return self.import_.expr

	def __call__(self, *args: *Args) -> R: ...
