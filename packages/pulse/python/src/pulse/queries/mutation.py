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

from pulse.context import PulseContext
from pulse.helpers import call_flexible, maybe_await
from pulse.queries.common import OnErrorFn, OnSuccessFn, bind_state
from pulse.reactive import Signal
from pulse.state.property import InitializableProperty
from pulse.state.state import State

T = TypeVar("T")
TState = TypeVar("TState", bound=State)
R = TypeVar("R")
P = ParamSpec("P")


class MutationResult(Generic[T, P]):
	"""Result object for mutations providing reactive state and execution.

	MutationResult wraps an async mutation function and provides reactive
	access to its execution state. It is callable to execute the mutation.

	Attributes:
		data: The last successful mutation result, or None.
		is_running: Whether the mutation is currently executing.
		error: The last error encountered, or None.

	Example:

	```python
	# Access mutation state
	if state.update_name.is_running:
	    show_loading()
	if state.update_name.error:
	    show_error(state.update_name.error)

	# Execute mutation
	result = await state.update_name("New Name")
	```
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
		"""Initialize the mutation result.

		Args:
			fn: The bound async function to execute.
			on_success: Optional callback invoked on successful completion.
			on_error: Optional callback invoked on error.
		"""
		self._data = Signal(None, name="mutation.data")
		self._is_running = Signal(False, name="mutation.is_running")
		self._error = Signal(None, name="mutation.error")
		self._fn = fn
		self._on_success = on_success
		self._on_error = on_error

	@property
	def data(self) -> T | None:
		"""The last successful mutation result, or None if never completed."""
		return self._data()

	@property
	def is_running(self) -> bool:
		"""Whether the mutation is currently executing."""
		return self._is_running()

	@property
	def error(self) -> Exception | None:
		"""The last error encountered, or None if no error."""
		return self._error()

	async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
		self._is_running.write(True)
		self._error.write(None)
		try:
			mutation_result = await self._fn(*args, **kwargs)
			self._data.write(mutation_result)
			if self._on_success:
				try:
					await maybe_await(call_flexible(self._on_success, mutation_result))
				except Exception as handler_exc:
					PulseContext.get().errors.report(
						handler_exc,
						code="mutation.handler",
						details={
							"handler": "on_success",
							"mutation": getattr(self._fn, "__name__", "<unknown>"),
						},
					)
			return mutation_result
		except Exception as exc:
			self._error.write(exc)
			if self._on_error:
				try:
					await maybe_await(call_flexible(self._on_error, exc))
				except Exception as handler_exc:
					PulseContext.get().errors.report(
						handler_exc,
						code="mutation.handler",
						details={
							"handler": "on_error",
							"mutation": getattr(self._fn, "__name__", "<unknown>"),
						},
					)
			raise
		finally:
			self._is_running.write(False)


class MutationProperty(Generic[T, TState, P], InitializableProperty):
	"""Descriptor for state-bound mutations created by the @mutation decorator.

	MutationProperty is the return type of the ``@mutation`` decorator. It acts
	as a descriptor that creates and manages MutationResult instances for each
	State object.

	When accessed on a State instance, returns a MutationResult that can be
	called to execute the mutation and provides reactive state properties.

	Supports additional decorators for customization:
		- ``@mutation_prop.on_success``: Handle successful mutation.
		- ``@mutation_prop.on_error``: Handle mutation errors.

	Example:

	```python
	class UserState(ps.State):
	    @ps.mutation
	    async def update_name(self, name: str) -> User:
	        return await api.update_user(name=name)

	    @update_name.on_success
	    def _on_success(self, data: User):
	        self.user.invalidate()  # Refresh user query

	    @update_name.on_error
	    def _on_error(self, error: Exception):
	        logger.error(f"Update failed: {error}")
	```
	"""

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
		"""Initialize the mutation property.

		Args:
			name: The method name.
			fn: The async method to wrap.
			on_success: Optional success callback.
			on_error: Optional error callback.
		"""
		self.name = name
		self.fn = fn
		self._on_success_fn = on_success  # pyright: ignore[reportAttributeAccessIssue]
		self._on_error_fn = on_error  # pyright: ignore[reportAttributeAccessIssue]

	def on_success(self, fn: OnSuccessFn[TState, T]) -> OnSuccessFn[TState, T]:
		"""Decorator to attach an on-success handler (sync or async).

		Args:
			fn: Callback receiving (self, data) on successful mutation.

		Returns:
			The callback function unchanged.
		"""
		if self._on_success_fn is not None:
			raise RuntimeError(
				f"Duplicate on_success() decorator for mutation '{self.name}'. Only one is allowed."
			)
		self._on_success_fn = fn  # pyright: ignore[reportAttributeAccessIssue]
		return fn

	def on_error(self, fn: OnErrorFn[TState]) -> OnErrorFn[TState]:
		"""Decorator to attach an on-error handler (sync or async).

		Args:
			fn: Callback receiving (self, error) on mutation failure.

		Returns:
			The callback function unchanged.
		"""
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
) -> MutationProperty[T, TState, P]: ...


@overload
def mutation(
	fn: None = None,
) -> Callable[
	[Callable[Concatenate[TState, P], Awaitable[T]]], MutationProperty[T, TState, P]
]: ...


def mutation(
	fn: Callable[Concatenate[TState, P], Awaitable[T]] | None = None,
) -> (
	MutationProperty[T, TState, P]
	| Callable[
		[Callable[Concatenate[TState, P], Awaitable[T]]],
		MutationProperty[T, TState, P],
	]
):
	"""Decorator for async mutations (write operations) on State methods.

	Creates a mutation wrapper that tracks execution state and provides
	callbacks for success/error handling. Unlike queries, mutations are
	not cached and must be explicitly called.

	Args:
		fn: The async method to decorate (when used without parentheses).

	Returns:
		MutationProperty that creates MutationResult instances when accessed.

	Example:

	```python
	class UserState(ps.State):
	    @ps.mutation
	    async def update_name(self, name: str) -> User:
	        return await api.update_user(name=name)

	    @update_name.on_success
	    def _on_success(self, data: User):
	        self.user.invalidate()
	```

	Calling the mutation:

	```python
	result = await state.update_name("New Name")
	```
	"""

	def decorator(func: Callable[Concatenate[TState, P], Awaitable[T]], /):
		sig = inspect.signature(func)
		params = list(sig.parameters.values())

		if len(params) == 0 or params[0].name != "self":
			raise TypeError("@mutation method must have 'self' as first argument")

		return MutationProperty(func.__name__, func)

	if fn:
		return decorator(fn)
	return decorator
