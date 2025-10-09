# Placeholders for the WIP JS compilation feature

from typing import TypeVar, TypeVarTuple, Generic, Callable, Optional

from pulse.codegen.imports import Imported


Args = TypeVarTuple("Args")
R = TypeVar("R")


class JsFunction(Generic[*Args, R]):
    "A transpiled JS function"

    def __init__(
        self,
        name: str,
        hint: Callable[[*Args], R],
    ) -> None:
        self.name = name
        self.hint = hint

    def __call__(self, *args: *Args) -> R: ...


class ExternalJsFunction(Generic[*Args, R], Imported):
    "An imported JS function"

    def __init__(
        self,
        name: str,
        src: str,
        *,
        prop: Optional[str] = None,
        is_default: bool,
        hint: Callable[[*Args], R],
    ) -> None:
        super().__init__(name, src, is_default=is_default, prop=prop)
        self.hint = hint

    def __call__(self, *args: *Args) -> R: ...
