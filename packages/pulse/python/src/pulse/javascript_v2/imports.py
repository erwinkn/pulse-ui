"""JS imports for use in @javascript decorated functions."""

from collections.abc import Callable
from typing import TypeVar, TypeVarTuple, overload

from pulse.codegen.imports import Import

T = TypeVar("T")
Args = TypeVarTuple("Args")
R = TypeVar("R")


@overload
def js_import(
	name: str, src: str, *, is_default: bool = False
) -> Callable[[Callable[[*Args], R]], Callable[[*Args], R]]:
	"Import a JS function for use in `@javascript` functions"
	...


@overload
def js_import(name: str, src: str, type_: type[T], *, is_default: bool = False) -> T:
	"Import a JS value for use in `@javascript` functions"
	...


def js_import(
	name: str, src: str, type_: type[T] | None = None, *, is_default: bool = False
) -> T | Callable[[Callable[[*Args], R]], Callable[[*Args], R]]:
	imp = Import.default(name, src) if is_default else Import(name, src)

	if type_ is not None:
		return imp  # pyright: ignore[reportReturnType]

	def decorator(fn: Callable[[*Args], R]) -> Callable[[*Args], R]:
		return imp  # pyright: ignore[reportReturnType]

	return decorator
