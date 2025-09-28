from typing import Callable, Iterable, TypeVar

from pulse.vdom import Element

T = TypeVar("T")


def For(items: Iterable[T], fn: Callable[[T], Element]):
    return [fn(item) for item in items]
