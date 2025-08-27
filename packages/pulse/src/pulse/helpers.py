from typing import (
    Any,
    Callable,
    Coroutine,
    Iterable,
    ParamSpec,
    Protocol,
    TypeVar,
    TypeVarTuple,
    Unpack,
)

from pulse.vdom import Element


Args = TypeVarTuple("Args")

T = TypeVar("T")
P = ParamSpec("P")
EventHandler = (
    Callable[[], None]
    | Callable[[], Coroutine[Any, Any, None]]
    | Callable[[Unpack[Args]], None]
    | Callable[[Unpack[Args]], Coroutine[Any, Any, None]]
)
JsFunction = Callable[P, T]

# In case we refine it later
CssStyle = dict[str, Any]

# Will be replaced by a JS transpiler type
class JsObject(Protocol):
    ...

MISSING = object()


class Sentinel:
    def __init__(self, name: str, value=MISSING) -> None:
        self.name = name
        self.value = value

    def __call__(self, value):
        return Sentinel(self.name, value)

    def __repr__(self) -> str:
        if self.value is not MISSING:
            return f"{self.name}({self.value})"
        else:
            return self.name


def For(items: Iterable[T], fn: Callable[[T], Element]):
    return [fn(item) for item in items]
