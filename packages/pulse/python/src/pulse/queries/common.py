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
	final,
	override,
)

from pulse.state import State

T = TypeVar("T")
TState = TypeVar("TState", bound="State")
P = ParamSpec("P")
R = TypeVar("R")


@final
class Key(tuple[Hashable, ...]):
	"""Normalized query key with a precomputed hash."""

	_hash: int = 0

	def __new__(cls, key: "QueryKey"):
		if isinstance(key, Key):
			return key
		if isinstance(key, (list, tuple)):
			parts = tuple(key)
			try:
				key_hash = hash(parts)
			except TypeError as e:
				raise TypeError(
					f"Query key contains unhashable value: {e}.\n\n"
					f"Keys must contain only hashable values (strings, numbers, tuples).\n"
					f"Got: {key!r}\n\n"
					f"If using a dict or list inside the key, convert it to a tuple:\n"
					f"    key=('users', tuple(user_ids))  # instead of list"
				) from None
			obj = super().__new__(cls, parts)
			obj._hash = key_hash
			return obj
		raise TypeError(
			f"Query key must be a tuple or list, got {type(key).__name__}: {key!r}\n\n"
			f"Examples of valid keys:\n"
			f"    key=('users',)           # single-element tuple\n"
			f"    key=('user', user_id)    # tuple with dynamic value\n"
			f"    key=['posts', 'feed']    # list form also works"
		)

	@override
	def __hash__(self) -> int:
		return self._hash


QueryKey: TypeAlias = tuple[Hashable, ...] | list[Hashable] | Key
"""List/tuple of hashable values identifying a query in the store.

Used to uniquely identify queries for caching, deduplication, and invalidation.
Keys are hierarchical lists/tuples like ``("user", user_id)`` or ``["posts", "feed"]``.
Lists are normalized to a tuple-backed Key internally.
"""


def normalize_key(key: QueryKey) -> Key:
	"""Convert a query key to a normalized key for use as a dict key."""
	return Key(key)


@final
@dataclass(frozen=True, slots=True)
class QueryKeys:
	"""Wrapper for selecting multiple query keys."""

	keys: tuple[Key, ...]

	def __init__(self, *keys: QueryKey):
		object.__setattr__(self, "keys", tuple(normalize_key(key) for key in keys))


def keys(*query_keys: QueryKey) -> QueryKeys:
	"""Create a QueryKeys wrapper for filtering by multiple keys."""
	return QueryKeys(*query_keys)


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
