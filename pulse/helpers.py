from typing import Any, Callable, Coroutine, TypeVarTuple, Unpack


Args = TypeVarTuple("Args")
EventHandler = (
    Callable[[], None]
    | Callable[[], Coroutine[Any, Any, None]]
    | Callable[[Unpack[Args]], None]
    | Callable[[Unpack[Args]], Coroutine[Any, Any, None]]
)
