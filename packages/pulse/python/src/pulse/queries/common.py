from collections.abc import Callable
from dataclasses import dataclass
from typing import (
	Any,
	Concatenate,
	Generic,
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


# Discriminated union result types for query actions
@dataclass(slots=True, frozen=True)
class ActionSuccess(Generic[T]):
	"""Successful query action result."""

	data: T
	status: Literal["success"] = "success"


@dataclass(slots=True, frozen=True)
class ActionError:
	"""Failed query action result."""

	error: Exception
	status: Literal["error"] = "error"


ActionResult: TypeAlias = ActionSuccess[T] | ActionError

OnSuccessFn = Callable[[TState], Any] | Callable[[TState, T], Any]
OnErrorFn = Callable[[TState], Any] | Callable[[TState, Exception], Any]


def bind_state(
	state: TState, fn: Callable[Concatenate[TState, P], R]
) -> Callable[P, R]:
	"Type-safe helper to bind a method to a state"
	return fn.__get__(state, state.__class__)
