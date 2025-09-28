from __future__ import annotations

from typing import Callable, overload, cast, TypeVar

from pulse.state import State

from .core import HookMetadata, HookState, hooks

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


class StatesHookState(HookState):
    __slots__ = ("initialized", "states", "key", "_called")

    def __init__(self) -> None:
        super().__init__()
        self.initialized = False
        self.states: tuple[State, ...] = ()
        self.key: str | None = None
        self._called = False

    def on_render_start(self, render_cycle: int) -> None:
        super().on_render_start(render_cycle)
        self._called = False

    def replace(self, states: list[State], key: str | None) -> None:
        self.dispose_states()
        self.states = tuple(states)
        self.key = key
        self.initialized = True

    def dispose_states(self) -> None:
        for state in self.states:
            state.dispose()
        self.states = ()
        self.initialized = False
        self.key = None

    def dispose(self) -> None:
        self.dispose_states()

    def ensure_not_called(self) -> None:
        if self._called:
            raise RuntimeError("`pulse.states` can only be called once per component render")

    def mark_called(self) -> None:
        self._called = True


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
    state = _states_hook()
    state.ensure_not_called()

    if not state.initialized:
        instances = [_instantiate_state(arg) for arg in args]
        state.replace(instances, key)
        state.mark_called()
        result = state.states
        return result[0] if len(result) == 1 else result

    if key is not None and key != state.key:
        instances = [_instantiate_state(arg) for arg in args]
        state.replace(instances, key)
        state.mark_called()
        result = state.states
        return result[0] if len(result) == 1 else result

    for arg in args:
        if isinstance(arg, State):
            arg.dispose()

    state.mark_called()
    result = state.states
    return result[0] if len(result) == 1 else result


__all__ = ["states", "StatesHookState"]
