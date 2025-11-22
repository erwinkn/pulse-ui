from collections.abc import Callable
from typing import (
	Any,
	Concatenate,
	ParamSpec,
	TypeVar,
)

from pulse.state import State

T = TypeVar("T")
TState = TypeVar("TState", bound="State")
P = ParamSpec("P")
R = TypeVar("R")

OnSuccessFn = Callable[[TState], Any] | Callable[[TState, T], Any]
OnErrorFn = Callable[[TState], Any] | Callable[[TState, Exception], Any]


def bind_state(
	state: TState, fn: Callable[Concatenate[TState, P], R]
) -> Callable[P, R]:
	"Type-safe helper to bind a method to a state"
	return fn.__get__(state, state.__class__)
