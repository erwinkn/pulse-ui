from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast, override

from pulse.helpers import Disposable
from pulse.hooks.core import INIT_SCOPE_ACTIVE, HookMetadata, HookState, hooks
from pulse.reactive import Effect, Scope, Signal

P = ParamSpec("P")
T = TypeVar("T")


class SetupState(HookState):
	"""Internal hook state for the setup hook.

	Manages the initialization, argument tracking, and lifecycle of
	setup-created values.

	Attributes:
		value: The value returned by the setup function.
		initialized: Whether setup has been called at least once.
		args: List of signals tracking positional argument values.
		kwargs: Dict of signals tracking keyword argument values.
		effects: List of effects created during setup execution.
		key: Optional key for re-initialization control.
	"""

	__slots__ = (  # pyright: ignore[reportUnannotatedClassAttribute]
		"value",
		"initialized",
		"args",
		"kwargs",
		"effects",
		"states",
		"key",
		"_called",
		"_pending_key",
	)
	initialized: bool
	_called: bool

	def __init__(self) -> None:
		super().__init__()
		self.value: Any = None
		self.initialized = False
		self.args: list[Signal[Any]] = []
		self.kwargs: dict[str, Signal[Any]] = {}
		self.effects: list[Effect] = []
		self.states: list[Disposable] = []
		self.key: str | None = None
		self._called = False
		self._pending_key: str | None = None

	@override
	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		self._called = False
		self._pending_key = None

	def initialize(
		self,
		init_func: Callable[..., Any],
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
		key: str | None,
	) -> Any:
		self.dispose_owned()
		# Effects and states created by the init function belong to this hook
		# alone: INIT_SCOPE_ACTIVE makes @ps.effect skip the inline-effects
		# cache so nothing ends up with two owners.
		token = INIT_SCOPE_ACTIVE.set(True)
		try:
			with Scope() as scope:
				self.value = init_func(*args, **kwargs)
		finally:
			INIT_SCOPE_ACTIVE.reset(token)
		self.effects = list(scope.effects)
		self.states = list(scope.states)
		self.args = [Signal(arg) for arg in args]
		self.kwargs = {name: Signal(value) for name, value in kwargs.items()}
		self.initialized = True
		self.key = key
		return self.value

	def ensure_signature(
		self,
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
	) -> None:
		if len(args) != len(self.args):
			raise RuntimeError(
				"Number of positional arguments passed to `pulse.setup` changed. "
				+ "Make sure you always call `pulse.setup` with the same number of positional "
				+ "arguments and the same keyword arguments."
			)
		if kwargs.keys() != self.kwargs.keys():
			new_keys = kwargs.keys() - self.kwargs.keys()
			missing_keys = self.kwargs.keys() - kwargs.keys()
			raise RuntimeError(
				"Keyword arguments passed to `pulse.setup` changed. "
				+ f"New arguments: {list(new_keys)}. Missing arguments: {list(missing_keys)}. "
				+ "Make sure you always call `pulse.setup` with the same number of positional "
				+ "arguments and the same keyword arguments."
			)

	def update_args(
		self,
		args: tuple[Any, ...],
		kwargs: dict[str, Any],
	) -> None:
		for idx, value in enumerate(args):
			self.args[idx].write(value)
		for name, value in kwargs.items():
			self.kwargs[name].write(value)

	def dispose_owned(self) -> None:
		"""Dispose the effects and states created by the last init run."""
		for effect in self.effects:
			if not effect.__disposed__:
				effect.dispose()
		self.effects = []
		for state in self.states:
			if not state.__disposed__:
				state.dispose()
		self.states = []

	@override
	def dispose(self) -> None:
		self.dispose_owned()
		self.args = []
		self.kwargs = {}
		self.value = None
		self.initialized = False
		self.key = None
		self._pending_key = None

	def ensure_not_called(self) -> None:
		if self._called:
			raise RuntimeError(
				"`pulse.setup` can only be called once per component render"
			)

	def mark_called(self) -> None:
		self._called = True

	@property
	def called_this_render(self) -> bool:
		return self._called

	def set_pending_key(self, key: str) -> None:
		self._pending_key = key

	def consume_pending_key(self) -> str | None:
		key = self._pending_key
		self._pending_key = None
		return key


setup_state = hooks.create(
	"pulse:core.setup",
	factory=SetupState,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.setup hook",
	),
)


def setup(init_func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
	"""One-time initialization that persists across renders.

	Calls the init function on first render and caches the result. On subsequent
	renders, returns the cached value without re-running the function.

	This is the lower-level alternative to ``ps.init()`` that doesn't require
	AST rewriting and works in all environments.

	Args:
		init_func: Function to call on first render. Its return value is cached.
		*args: Positional arguments passed to init_func. Changes to these are
			tracked via reactive signals.
		**kwargs: Keyword arguments passed to init_func. Changes to these are
			tracked via reactive signals.

	Returns:
		The value returned by init_func (cached on first render).

	Raises:
		RuntimeError: If called more than once per component render.
		RuntimeError: If the number or names of arguments change between renders.

	Example:

	```python
	@ps.component
	def Counter():
	    def init():
	        return CounterState(), expensive_calculation()

	    state, value = ps.setup(init)

	    return ps.div(f"Count: {state.count}")
	```

	Notes:
		- ``ps.init()`` is syntactic sugar that transforms into ``ps.setup()`` calls
		- Use ``ps.setup()`` directly when AST rewriting is problematic
		- Arguments must be consistent across renders (same count and names)
	"""
	state = setup_state()
	state.ensure_not_called()

	key = state.consume_pending_key()
	args_tuple = tuple(args)
	kwargs_dict = dict(kwargs)

	if state.initialized:
		if key is not None and key != state.key:
			state.initialize(init_func, args_tuple, kwargs_dict, key)
			state.mark_called()
			return cast(T, state.value)
		state.ensure_signature(args_tuple, kwargs_dict)
		state.update_args(args_tuple, kwargs_dict)
		if key is not None:
			state.key = key
		state.mark_called()
		return cast(T, state.value)

	state.initialize(init_func, args_tuple, kwargs_dict, key)
	state.mark_called()
	return cast(T, state.value)


def setup_key(key: str) -> None:
	"""Set a key for the next setup call to control re-initialization.

	When the key changes between renders, the setup function is re-run
	and a new value is created. This is useful for resetting state when
	a prop changes.

	Args:
		key: String key that, when changed, triggers re-initialization
			of the subsequent setup call.

	Raises:
		TypeError: If key is not a string.
		RuntimeError: If called after setup() in the same render.

	Example:

	```python
	def user_profile(user_id: str):
	    ps.setup_key(user_id)  # Re-run setup when user_id changes
	    data = ps.setup(lambda: fetch_user_data(user_id))
	    return m.Text(data.name)
	```
	"""
	if not isinstance(key, str):
		raise TypeError("setup_key() requires a string key")
	state = setup_state()
	if state.called_this_render:
		raise RuntimeError("setup_key() must be called before setup() in a render")
	state.set_pending_key(key)


__all__ = ["setup", "setup_key", "SetupState"]
