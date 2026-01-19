from collections.abc import Callable
from typing import TypeVar, override

from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.state import State

S = TypeVar("S", bound=State)


class StateHookState(HookState):
	"""Internal hook state for managing State instances across renders.

	Stores State instances keyed by string identifier and tracks which keys
	have been accessed during the current render cycle.
	"""

	__slots__ = ("instances", "called_keys")  # pyright: ignore[reportUnannotatedClassAttribute]
	instances: dict[str, State]
	called_keys: set[str]

	def __init__(self) -> None:
		super().__init__()
		self.instances = {}
		self.called_keys = set()

	@override
	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		self.called_keys.clear()

	def get_or_create_state(self, key: str, arg: State | Callable[[], State]) -> State:
		if key in self.called_keys:
			raise RuntimeError(
				f"`pulse.state` can only be called once per component render with key='{key}'"
			)
		self.called_keys.add(key)

		existing = self.instances.get(key)
		if existing is not None:
			# Dispose any State instances passed directly as args that aren't being used
			if isinstance(arg, State) and arg is not existing:
				try:
					if not arg.__disposed__:
						arg.dispose()
				except RuntimeError:
					# Already disposed, ignore
					pass
			return existing

		# Create new state
		instance = _instantiate_state(arg)
		self.instances[key] = instance
		return instance

	@override
	def dispose(self) -> None:
		for instance in self.instances.values():
			try:
				if not instance.__disposed__:
					instance.dispose()
			except RuntimeError:
				# Already disposed, ignore
				pass
		self.instances.clear()


def _instantiate_state(arg: State | Callable[[], State]) -> State:
	instance = arg() if callable(arg) else arg
	if not isinstance(instance, State):
		raise TypeError(
			"`pulse.state` expects a State instance or a callable returning a State instance"
		)
	return instance


def _state_factory():
	return StateHookState()


_state_hook = hooks.create(
	"pulse:core.state",
	_state_factory,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.state hook",
	),
)


def state(key: str, arg: S | Callable[[], S]) -> S:
	"""Get or create a State instance persisted across renders.

	Args:
		key: Unique identifier within the component. Must be a non-empty string.
		arg: State instance or factory function that returns a State instance.
			The factory is only called on first render; subsequent renders
			return the cached instance.

	Returns:
		The same State instance on subsequent renders with the same key.

	Raises:
		ValueError: If key is empty.
		RuntimeError: If called more than once per render with the same key.
		TypeError: If arg is not a State or callable returning a State.

	Example:
		>>> def counter():
		...     s = ps.state("counter", lambda: CounterState())
		...     return m.Button(f"Count: {s.count}", on_click=lambda: s.increment())

	Notes:
		- Key must be non-empty string
		- Can only be called once per render with the same key
		- Factory is only called on first render; subsequent renders return cached instance
		- State is disposed when component unmounts
	"""
	if not key:
		raise ValueError("state() requires a non-empty string key")
	hook_state = _state_hook()
	return hook_state.get_or_create_state(key, arg)  # pyright: ignore[reportReturnType]


__all__ = ["state", "StateHookState"]
