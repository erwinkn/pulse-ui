import inspect
from collections.abc import Awaitable, Callable
from typing import (
	Any,
	Concatenate,
	Generic,
	ParamSpec,
	TypeVar,
	overload,
	override,
)

from pulse.helpers import call_flexible, maybe_await
from pulse.queries.common import OnErrorFn, OnSuccessFn, bind_state
from pulse.reactive import Signal
from pulse.state import InitializableProperty, State

T = TypeVar("T")
TState = TypeVar("TState", bound=State)
R = TypeVar("R")
P = ParamSpec("P")


class MutationResult(Generic[T, P]):
	"""
	Result object for mutations that provides reactive access to mutation state
	and is callable to execute the mutation.
	"""

	_data: Signal[T | None]
	_is_running: Signal[bool]
	_error: Signal[Exception | None]
	_fn: Callable[P, Awaitable[T]]
	_on_success: Callable[[T], Any] | None
	_on_error: Callable[[Exception], Any] | None

	def __init__(
		self,
		fn: Callable[P, Awaitable[T]],
		on_success: Callable[[T], Any] | None = None,
		on_error: Callable[[Exception], Any] | None = None,
	):
		self._data = Signal(None, name="mutation.data")
		self._is_running = Signal(False, name="mutation.is_running")
		self._error = Signal(None, name="mutation.error")
		self._fn = fn
		self._on_success = on_success
		self._on_error = on_error

	@property
	def data(self) -> T | None:
		return self._data()

	@property
	def is_running(self) -> bool:
		return self._is_running()

	@property
	def error(self) -> Exception | None:
		return self._error()

	async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
		self._is_running.write(True)
		self._error.write(None)
		try:
			mutation_result = await self._fn(*args, **kwargs)
			self._data.write(mutation_result)
			if self._on_success:
				await maybe_await(call_flexible(self._on_success, mutation_result))
			return mutation_result
		except Exception as e:
			self._error.write(e)
			if self._on_error:
				await maybe_await(call_flexible(self._on_error, e))
			raise e
		finally:
			self._is_running.write(False)


class MutationProperty(Generic[T, TState, P], InitializableProperty):
	_on_success_fn: Callable[[TState, T], Any] | None
	_on_error_fn: Callable[[TState, Exception], Any] | None
	name: str
	fn: Callable[Concatenate[TState, P], Awaitable[T]]

	def __init__(
		self,
		name: str,
		fn: Callable[Concatenate[TState, P], Awaitable[T]],
		on_success: OnSuccessFn[TState, T] | None = None,
		on_error: OnErrorFn[TState] | None = None,
	):
		self.name = name
		self.fn = fn
		self._on_success_fn = on_success  # pyright: ignore[reportAttributeAccessIssue]
		self._on_error_fn = on_error  # pyright: ignore[reportAttributeAccessIssue]

	# Decorator to attach an on-success handler (sync or async)
	def on_success(self, fn: OnSuccessFn[TState, T]):
		if self._on_success_fn is not None:
			raise RuntimeError(
				f"Duplicate on_success() decorator for mutation '{self.name}'. Only one is allowed."
			)
		self._on_success_fn = fn  # pyright: ignore[reportAttributeAccessIssue]
		return fn

	# Decorator to attach an on-error handler (sync or async)
	def on_error(self, fn: OnErrorFn[TState]):
		if self._on_error_fn is not None:
			raise RuntimeError(
				f"Duplicate on_error() decorator for mutation '{self.name}'. Only one is allowed."
			)
		self._on_error_fn = fn  # pyright: ignore[reportAttributeAccessIssue]
		return fn

	def __get__(self, obj: Any, objtype: Any = None) -> MutationResult[T, P]:
		if obj is None:
			return self  # pyright: ignore[reportReturnType]

		# Cache the result on the instance
		cache_key = f"__mutation_{self.name}"
		if not hasattr(obj, cache_key):
			# Bind methods to state
			bound_fn = bind_state(obj, self.fn)
			bound_on_success = (
				bind_state(obj, self._on_success_fn) if self._on_success_fn else None
			)
			bound_on_error = (
				bind_state(obj, self._on_error_fn) if self._on_error_fn else None
			)

			result = MutationResult[T, P](
				fn=bound_fn,
				on_success=bound_on_success,
				on_error=bound_on_error,
			)
			setattr(obj, cache_key, result)

		return getattr(obj, cache_key)

	@override
	def initialize(self, state: State, name: str) -> MutationResult[T, P]:
		# For compatibility with InitializableProperty, but mutations don't need special initialization
		return self.__get__(state, state.__class__)


@overload
def mutation(
	fn: Callable[Concatenate[TState, P], Awaitable[T]],
	*,
	on_success: OnSuccessFn[TState, T] | None = None,
	on_error: OnErrorFn[TState] | None = None,
) -> MutationProperty[T, TState, P]: ...


@overload
def mutation(
	fn: None = None,
	*,
	on_success: OnSuccessFn[TState, T] | None = None,
	on_error: OnErrorFn[TState] | None = None,
) -> Callable[
	[Callable[Concatenate[TState, P], Awaitable[T]]], MutationProperty[T, TState, P]
]: ...


def mutation(
	fn: Callable[Concatenate[TState, P], Awaitable[T]] | None = None,
	*,
	on_success: OnSuccessFn[TState, T] | None = None,
	on_error: OnErrorFn[TState] | None = None,
):
	def decorator(func: Callable[Concatenate[TState, P], Awaitable[T]], /):
		sig = inspect.signature(func)
		params = list(sig.parameters.values())

		if len(params) == 0 or params[0].name != "self":
			raise TypeError("@mutation method must have 'self' as first argument")

		return MutationProperty(
			func.__name__,
			func,
			on_success=on_success,
			on_error=on_error,
		)

	if fn:
		return decorator(fn)
	return decorator
