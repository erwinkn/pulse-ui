from collections.abc import Callable
from typing import (
	Any,
	Concatenate,
	Hashable,
	Literal,
	ParamSpec,
	TypeAlias,
	TypeVar,
)

from pulse.state import State

T = TypeVar("T")
TState = TypeVar("TState", bound="State")
P = ParamSpec("P")
R = TypeVar("R")

QueryKey: TypeAlias = tuple[Hashable, ...]
QueryStatus: TypeAlias = Literal["loading", "success", "error"]
QueryFetchStatus: TypeAlias = Literal["idle", "fetching", "paused"]

OnSuccessFn = Callable[[TState], Any] | Callable[[TState, T], Any]
OnErrorFn = Callable[[TState], Any] | Callable[[TState, Exception], Any]


def bind_state(
	state: TState, fn: Callable[Concatenate[TState, P], R]
) -> Callable[P, R]:
	"Type-safe helper to bind a method to a state"
	return fn.__get__(state, state.__class__)
