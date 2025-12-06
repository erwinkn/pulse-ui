from collections.abc import Callable
from typing import TypeVar, overload, override

from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.state import State

S = TypeVar("S", bound=State)
S1 = TypeVar("S1", bound=State)
S2 = TypeVar("S2", bound=State)
S3 = TypeVar("S3", bound=State)
S4 = TypeVar("S4", bound=State)
S5 = TypeVar("S5", bound=State)
S6 = TypeVar("S6", bound=State)
S7 = TypeVar("S7", bound=State)
S8 = TypeVar("S8", bound=State)
S9 = TypeVar("S9", bound=State)
S10 = TypeVar("S10", bound=State)


class StateNamespace:
	__slots__ = ("states", "key", "called")  # pyright: ignore[reportUnannotatedClassAttribute]
	states: tuple[State, ...]
	key: str | None
	called: bool

	def __init__(self, key: str | None) -> None:
		self.states = ()
		self.key = key
		self.called = False

	def ensure_not_called(self) -> None:
		if self.called:
			key_msg = (
				f" with key='{self.key}'" if self.key is not None else " without a key"
			)
			raise RuntimeError(
				f"`pulse.states` can only be called once per component render{key_msg}"
			)

	def get_or_create_states(
		self, args: tuple[State | Callable[[], State], ...]
	) -> tuple[State, ...]:
		if len(self.states) > 0:
			# Reuse existing states
			existing_states = self.states
			# Validate that the number of arguments matches
			if len(args) != len(existing_states):
				key_msg = (
					f" with key='{self.key}'"
					if self.key is not None
					else " without a key"
				)
				raise RuntimeError(
					f"`pulse.states` called with {len(args)} argument(s) but was previously "
					+ f"called with {len(existing_states)} argument(s){key_msg}. "
					+ "The number of arguments must remain consistent across renders."
				)
			# Dispose any State instances passed directly as args that aren't being used
			existing_set = set(existing_states)
			for arg in args:
				if isinstance(arg, State) and arg not in existing_set:
					try:
						if not arg.__disposed__:
							arg.dispose()
					except RuntimeError:
						# Already disposed, ignore
						pass
			return existing_states

		# Create new states
		instances = tuple(_instantiate_state(arg) for arg in args)
		self.states = instances
		return instances

	def dispose(self) -> None:
		for state in self.states:
			try:
				if not state.__disposed__:
					state.dispose()
			except RuntimeError:
				# Already disposed, ignore
				pass
		self.states = ()


class StatesHookState(HookState):
	__slots__ = ("namespaces",)  # pyright: ignore[reportUnannotatedClassAttribute]
	namespaces: dict[str | None, StateNamespace]

	def __init__(self) -> None:
		super().__init__()
		self.namespaces = {}

	@override
	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		if self.namespaces:
			for namespace in self.namespaces.values():
				namespace.called = False

	def get_namespace(self, key: str | None) -> StateNamespace:
		if key not in self.namespaces:
			self.namespaces[key] = StateNamespace(key)
		return self.namespaces[key]

	def get_or_create_states(
		self, args: tuple[State | Callable[[], State], ...], key: str | None
	) -> tuple[State, ...]:
		namespace = self.get_namespace(key)
		namespace.ensure_not_called()
		result = namespace.get_or_create_states(args)
		namespace.called = True
		return result

	@override
	def dispose(self) -> None:
		for namespace in self.namespaces.values():
			namespace.dispose()
		self.namespaces.clear()


def _instantiate_state(arg: State | Callable[[], State]) -> State:
	state = arg() if callable(arg) else arg
	if not isinstance(state, State):
		raise TypeError(
			"`pulse.states` expects State instances or callables returning State instances"
		)
	return state


def _states_factory():
	return StatesHookState()


_states_hook = hooks.create(
	"pulse:core.states",
	_states_factory,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.states hook",
	),
)


@overload
def states(s1: S1 | Callable[[], S1], /, *, key: str | None = ...) -> S1: ...  # pyright: ignore[reportOverlappingOverload]


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	s4: S4 | Callable[[], S4],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3, S4]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	s4: S4 | Callable[[], S4],
	s5: S5 | Callable[[], S5],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3, S4, S5]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	s4: S4 | Callable[[], S4],
	s5: S5 | Callable[[], S5],
	s6: S6 | Callable[[], S6],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3, S4, S5, S6]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	s4: S4 | Callable[[], S4],
	s5: S5 | Callable[[], S5],
	s6: S6 | Callable[[], S6],
	s7: S7 | Callable[[], S7],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3, S4, S5, S6, S7]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	s4: S4 | Callable[[], S4],
	s5: S5 | Callable[[], S5],
	s6: S6 | Callable[[], S6],
	s7: S7 | Callable[[], S7],
	s8: S8 | Callable[[], S8],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	s4: S4 | Callable[[], S4],
	s5: S5 | Callable[[], S5],
	s6: S6 | Callable[[], S6],
	s7: S7 | Callable[[], S7],
	s8: S8 | Callable[[], S8],
	s9: S9 | Callable[[], S9],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8, S9]: ...


@overload
def states(
	s1: S1 | Callable[[], S1],
	s2: S2 | Callable[[], S2],
	s3: S3 | Callable[[], S3],
	s4: S4 | Callable[[], S4],
	s5: S5 | Callable[[], S5],
	s6: S6 | Callable[[], S6],
	s7: S7 | Callable[[], S7],
	s8: S8 | Callable[[], S8],
	s9: S9 | Callable[[], S9],
	s10: S10 | Callable[[], S10],
	/,
	*,
	key: str | None = ...,
) -> tuple[S1, S2, S3, S4, S5, S6, S7, S8, S9, S10]: ...


@overload
def states(*args: S | Callable[[], S], key: str | None = ...) -> tuple[S, ...]: ...


def states(*args: State | Callable[[], State], key: str | None = None):
	hook_state = _states_hook()
	result = hook_state.get_or_create_states(args, key)
	return result[0] if len(result) == 1 else result


__all__ = ["states", "StatesHookState"]
