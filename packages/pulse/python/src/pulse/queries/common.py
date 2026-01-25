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

QueryKey: TypeAlias = tuple[Hashable, ...] | list[Hashable]
"""Sequence of hashable values identifying a query in the store.

Used to uniquely identify queries for caching, deduplication, and invalidation.
Keys are hierarchical sequences like ``("user", user_id)`` or ``["posts", "feed"]``.
Lists are normalized to tuples internally for hashability.
"""


def normalize_key(key: QueryKey) -> tuple[Hashable, ...]:
	"""Convert a query key to a tuple for use as a dict key."""
	return key if isinstance(key, tuple) else tuple(key)


QueryStatus: TypeAlias = Literal["loading", "success", "error"]
"""Current status of a query.

Values:
    - ``"loading"``: Query is fetching data (initial load or refetch).
    - ``"success"``: Query has successfully fetched data.
    - ``"error"``: Query encountered an error during fetch.
"""


@dataclass(slots=True, frozen=True)
class ActionSuccess(Generic[T]):
	"""Successful query action result.

	Returned by query operations like ``refetch()`` and ``wait()`` when the
	operation completes successfully.

	Attributes:
		data: The fetched data of type T.
		status: Always ``"success"`` for discriminated union matching.

	Example:

	```python
	result = await state.user.refetch()
	if result.status == "success":
	    print(result.data)
	```
	"""

	data: T
	status: Literal["success"] = "success"


@dataclass(slots=True, frozen=True)
class ActionError:
	"""Failed query action result.

	Returned by query operations like ``refetch()`` and ``wait()`` when the
	operation fails after exhausting retries.

	Attributes:
		error: The exception that caused the failure.
		status: Always ``"error"`` for discriminated union matching.

	Example:

	```python
	result = await state.user.refetch()
	if result.status == "error":
	    print(f"Failed: {result.error}")
	```
	"""

	error: Exception
	status: Literal["error"] = "error"


ActionResult: TypeAlias = ActionSuccess[T] | ActionError
"""Union type for query action results.

Either ``ActionSuccess[T]`` with data or ``ActionError`` with an exception.
Use the ``status`` field to discriminate between success and error cases.
"""

OnSuccessFn = Callable[[TState], Any] | Callable[[TState, T], Any]
OnErrorFn = Callable[[TState], Any] | Callable[[TState, Exception], Any]


def bind_state(
	state: TState, fn: Callable[Concatenate[TState, P], R]
) -> Callable[P, R]:
	"Type-safe helper to bind a method to a state"
	return fn.__get__(state, state.__class__)
