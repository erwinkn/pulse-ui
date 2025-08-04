from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

# TODO: Reimplement init hook with the new reactive system
# def init(init_func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
#     ...


def router(): ...
