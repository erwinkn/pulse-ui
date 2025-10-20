from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast, override

from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.reactive import Effect, Scope, Signal

P = ParamSpec("P")
T = TypeVar("T")


class SetupHookState(HookState):
	__slots__: tuple[str, ...] = (
		"value",
		"initialized",
		"args",
		"kwargs",
		"effects",
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
		self.dispose_effects()
		with Scope() as scope:
			self.value = init_func(*args, **kwargs)
			self.effects = list(scope.effects)
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

	def dispose_effects(self) -> None:
		for effect in self.effects:
			effect.dispose()
		self.effects = []

	@override
	def dispose(self) -> None:
		self.dispose_effects()
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


def _setup_factory():
	return SetupHookState()


_setup_hook = hooks.create(
	"pulse:core.setup",
	_setup_factory,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.setup hook",
	),
)


def setup(init_func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
	state = _setup_hook()
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
	if not isinstance(key, str):
		raise TypeError("setup_key() requires a string key")
	state = _setup_hook()
	if state.called_this_render:
		raise RuntimeError("setup_key() must be called before setup() in a render")
	state.set_pending_key(key)


__all__ = ["setup", "setup_key", "SetupHookState"]
