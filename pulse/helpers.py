from typing import Any, Callable, Coroutine, TypeVarTuple, Unpack


Args = TypeVarTuple("Args")
EventHandler = (
    Callable[[], None]
    | Callable[[], Coroutine[Any, Any, None]]
    | Callable[[Unpack[Args]], None]
    | Callable[[Unpack[Args]], Coroutine[Any, Any, None]]
)


class Sentinel:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name
