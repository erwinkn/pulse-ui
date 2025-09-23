from typing import (
    Any,
    Callable,
    Coroutine,
    TypeVar,
)

EventHandlerResult = None | Coroutine[Any, Any, None]

T1 = TypeVar("T1", contravariant=True)
T2 = TypeVar("T2", contravariant=True)
T3 = TypeVar("T3", contravariant=True)
T4 = TypeVar("T4", contravariant=True)
T5 = TypeVar("T5", contravariant=True)
T6 = TypeVar("T6", contravariant=True)
T7 = TypeVar("T7", contravariant=True)
T8 = TypeVar("T8", contravariant=True)
T9 = TypeVar("T9", contravariant=True)
T10 = TypeVar("T10", contravariant=True)


EventHandler0 = Callable[[], EventHandlerResult]
EventHandler1 = EventHandler0 | Callable[[T1], EventHandlerResult]
EventHandler2 = EventHandler1[T1] | Callable[[T1, T2], EventHandlerResult]
EventHandler3 = EventHandler2[T1, T2] | Callable[[T1, T2, T3], EventHandlerResult]
EventHandler4 = (
    EventHandler3[T1, T2, T3] | Callable[[T1, T2, T3, T4], EventHandlerResult]
)
EventHandler5 = (
    EventHandler4[T1, T2, T3, T4] | Callable[[T1, T2, T3, T4, T5], EventHandlerResult]
)
EventHandler6 = (
    EventHandler5[T1, T2, T3, T4, T5]
    | Callable[[T1, T2, T3, T4, T5, T6], EventHandlerResult]
)
EventHandler7 = (
    EventHandler6[T1, T2, T3, T4, T5, T6]
    | Callable[[T1, T2, T3, T4, T5, T6, T7], EventHandlerResult]
)
EventHandler8 = (
    EventHandler7[T1, T2, T3, T4, T5, T6, T7]
    | Callable[[T1, T2, T3, T4, T5, T6, T7, T8], EventHandlerResult]
)
EventHandler9 = (
    EventHandler8[T1, T2, T3, T4, T5, T6, T7, T8]
    | Callable[[T1, T2, T3, T4, T5, T6, T7, T8, T9], EventHandlerResult]
)
EventHandler10 = (
    EventHandler9[T1, T2, T3, T4, T5, T6, T7, T8, T9]
    | Callable[[T1, T2, T3, T4, T5, T6, T7, T8, T9, T10], EventHandlerResult]
)
