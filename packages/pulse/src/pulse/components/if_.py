from collections.abc import Iterable
from typing import TypeVar

from pulse.vdom import Element

T1 = TypeVar("T1", bound=Element | Iterable[Element])
T2 = TypeVar("T2", bound=Element | Iterable[Element] | None)


def If(
    condition: bool,
    then: T1,
    else_: T2 = None,
) -> T1 | T2:
    """Conditional rendering helper that returns either then or else_ based on condition.

    Args:
        condition: Value to test truthiness
        then: Element to render if condition is truthy
        else_: Optional element to render if condition is falsy

    Returns:
        The then value if condition is truthy, else_ if provided and condition is falsy, None otherwise
    """
    if condition:
        return then
    return else_
