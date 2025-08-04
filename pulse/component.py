from typing import Callable, ParamSpec

from pulse.vdom import Node

P = ParamSpec("P")


class Component:
    def __init__(self, fn: Callable[P, Node]) -> None:
        self.fn = fn


def component(fn: Callable[P, Node]):
    return Component(fn)
