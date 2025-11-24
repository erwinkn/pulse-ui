from typing import (
	TypeVar,
)

from pulse.state import State

T = TypeVar("T")
TState = TypeVar("TState", bound=State)
