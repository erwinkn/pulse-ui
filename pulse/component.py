from typing import Callable, ParamSpec

from pulse.vdom import Node

P = ParamSpec("P")


class Component:
    def __init__(self, fn: Callable[P, Node]) -> None:
        self.fn = fn


class ComponentInstance:
    def __init__(self) -> None:
        pass


def component(fn: Callable[P, Node]):
    return Component(fn)
