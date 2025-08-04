"""
The reactive core of Pulse UI.

This module implements a push-pull reactive system inspired by Solid.js.
"""

from __future__ import annotations
from collections import deque
from contextvars import ContextVar, Token
from turtle import st
from typing import Any, Callable, Generic, ParamSpec, TypeVar, List, Set, Optional

T = TypeVar("T")
P = ParamSpec("P")

# --- Globals ---

EPOCH = ContextVar("EPOCH", default=1)
SCOPE: ContextVar[Optional[Scope]] = ContextVar("pulse_scope", default=None)
BATCH: ContextVar[Optional[UpdateBatch]] = ContextVar("pulse_batch", default=None)
PENDING: deque[Signal] = deque()
EFFECTS: deque[Effect] = deque()


# --- Reactive Nodes ---


# class Node(Generic[T]):
#     def __init__(self, value: T, name: Optional[str] = None):
#         self.value = value
#         self.name = name
#         self.last_change = -1
#         self.last_verified = -1
#         self.deps: List[Node] = []
#         self.obs: List[Node] = []
#         self.dirty = False
#         self.inactive = False
#         self.on_stack = False

#     def __call__(self) -> T:
#         return self.read()

#     def read(self) -> T:
#         raise NotImplementedError

#     def write(self, value: T):
#         raise NotImplementedError

#     def watch_dep(self, node: Node):
#         # NOTE: in the past I ran into bugs where this caused multiple instances of the
#         # dependency link to be registered, so let's be careful about this
#         node.obs.append(self)

#     def stop_watching_deps(self):
#         for dep in self.deps:
#             if self in dep.obs:
#                 dep.obs.remove(self)
#         self.deps = []


class Signal(Generic[T]):
    def __init__(self, value: T, name: Optional[str] = None):
        self.value = value
        self.name = name
        self.obs: list[Computed | Effect] = []
        self.last_change = -1

    def read(self) -> T:
        if scope := SCOPE.get():
            scope.accessed.add(self)
        return self.value

    def __call__(self) -> T:
        return self.read()

    def _add_obs(self, obs: Computed | Effect):
        self.obs.append(obs)

    def _do_write(self, value: T):
        if value == self.value:
            return
        self.value = value
        self.last_change = EPOCH.get()

    def _push_change(self):
        for obs in self.obs:
            obs._push_change()

    def write(self, value: T):
        # Do not perform the equality check immediately, in case it's costly or
        # has side effects (you never know in Python).
        if batch := BATCH.get():
            batch.schedule_signal(self, value)
        else:
            # This update may trigger multiple update iterations, this keeps the logic self-contained within a batch
            with UpdateBatch() as batch:
                print("Immediate update path")
                batch.schedule_signal(self, value)


# -- NOTE about dirty status
# "Dirty" means "may have changed". It's part of the push phase when a signal is
# written. During the pull phase, where we rerun effects and recompute their
# dependencies, we verify whether the change is real or not.

# -- NOTE about skipping inactive compute nodes
# If a computed was used in an effect, that effect reran, and the computed is
# not used anymore, it will have been marked as dirty and not have been updated.
# This will automatically opt it out of graph propagation, until it's read
# again.


class Computed(Generic[T]):
    def __init__(self, fn: Callable[[], T], name: Optional[str] = None):
        self.fn = fn
        self.value: T = None  # type: ignore
        self.name = name
        # self.active = False
        self.dirty = False
        self.on_stack = False
        self.last_change = -1
        self.deps: list[Signal | Computed] = []
        self.obs: list[Computed | Effect] = []

    def read(self) -> T:
        if self.on_stack:
            raise RuntimeError("Circular dependency detected")

        if scope := SCOPE.get():
            scope.accessed.add(self)

        print("Reading computed")
        self._recompute_if_necessary()
        return self.value

    def __call__(self) -> T:
        return self.read()

    def _push_change(self):
        # Skip inactive nodes.
        if self.dirty:
            return

        self.dirty = True
        for obs in self.obs:
            obs._push_change()

    def _recompute(self):
        print("Computed._recompute")
        epoch = EPOCH.get()
        current_deps = set(self.deps)

        prev_value = self.value
        with Scope(parent=SCOPE.get()) as scope:
            self.on_stack = True
            self.value = self.fn()
            self.on_stack = False
            self.dirty = False
            if prev_value != self.value:
                self.last_change = epoch

        new_deps = scope.accessed
        add_deps = new_deps - current_deps
        remove_deps = current_deps - new_deps
        for dep in add_deps:
            dep.obs.append(self)
        for dep in remove_deps:
            dep.obs.remove(self)

        self.deps = list(new_deps)

    def _recompute_if_necessary(self):
        "Recompute if necessary and return whether the value changed"
        if self.last_change < 0:
            self._recompute()
            return
        if not self.dirty:
            print("Skipping")
            return

        # Check dependencies to see if we need to recompute
        for dep in self.deps:
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
            if dep.last_change > self.last_change:
                self._recompute()
                return
            else:
                print("Skipping  due to no update deps")
                print("self.last_change =", self.last_change)
                print(f"dep.last_change = ", dep.last_change)


EffectFnWithoutCleanup = Callable[[], None]
EffectCleanup = Callable[[], None]
EffectFnWithCleanup = Callable[[], EffectCleanup]
EffectFn = EffectFnWithCleanup | EffectFnWithoutCleanup


class Effect:
    def __init__(self, fn: EffectFn, name: Optional[str] = None):
        self.fn = fn
        self.name = name
        self.deps: list[Signal | Computed] = []
        self.cleanup: Optional[EffectCleanup] = None

        self.on_stack = True
        self._run()
        self.on_stack = False

    def _push_change(self):
        batch = BATCH.get()
        # Use assert as this case should be impossible
        assert batch is not None, (
            "Effect._push_change() should never be called without a BATCH ContextVar"
        )
        batch.effects.append(self)

    def _should_run(self):
        epoch = EPOCH.get()
        # Check dependencies in the order they were registered. That way, if
        # there is a conditional dependency that changed, we'll determine that
        # we need to run just by looking at the condition and we'll skip the
        # dependencies under the condition (that may not need to run).
        for dep in self.deps:
            # True for both signals and computeds
            if dep.last_change == epoch:
                return True
            if isinstance(dep, Computed) and dep._recompute_if_necessary():
                return True
        return False

    def _run(self):
        # TODO: cleanup -> run -> update deps
        current_deps = set(self.deps)

        with Scope(parent=SCOPE.get()) as scope:
            if self.cleanup:
                self.cleanup()
            self.cleanup = self.fn()

        new_deps = scope.accessed
        add_deps = new_deps - current_deps
        remove_deps = current_deps - new_deps
        for dep in add_deps:
            dep.obs.append(self)
        for dep in remove_deps:
            dep.obs.remove(self)

        self.deps = list(new_deps)


# --- Scope & Dependency Management ---


class Scope:
    def __init__(self, parent: Optional[Scope] = None):
        self.parent = parent
        self.accessed: Set[Signal | Computed] = set()

    def __enter__(self):
        self._token = SCOPE.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        SCOPE.reset(self._token)


class UpdateBatch:
    def __init__(self) -> None:
        self.signals: list[tuple[Signal, Any]] = []
        self.effects: list[Effect] = []

    def schedule_signal(self, signal: Signal[T], value: T):
        self.signals.append((signal, value))

    def schedule_effect(self, effect: Effect):
        self.effects.append(effect)

    def flush(self):
        # Make sure this batch accumulates any writes that may happen during the update cycle
        global_batch = BATCH.get()
        token = None
        if global_batch != self:
            token = BATCH.set(self)
        # print("Flushing batch with:")
        # print(f'- Signals: {self.signals}')
        # print(f'- Effects: {self.effects}')
        MAX_ITERS = 10000
        epoch = start_epoch = EPOCH.get()
        print(f"Flush with start_epoch = {start_epoch}")

        # NOTE: is there a reason an effect may schedule an effect without a write?
        while len(self.signals) > 0:
            epoch += 1
            EPOCH.set(epoch)
            if epoch - start_epoch > MAX_ITERS:
                raise RuntimeError(
                    f"Pulse's reactive system registered more than {MAX_ITERS} iterations. There is likely an update cycle in your application.\n"
                    "This is most often caused through a state update during rerender or in an effect that ends up triggering the same rerender or effect."
                )

            for signal, value in self.signals:
                signal._do_write(value)
                # This will flag dirty all upstream nodes and add the dirty effects to self.effects
                signal._push_change()
            # Reset signals before running effects, so that new writes may accumulate there
            self.signals = []

            for effect in self.effects:
                if effect._should_run():
                    effect._run()
            # Reset effects before the next batch of updates
            self.effects = []

        if token:
            BATCH.reset(token)

    def __enter__(self):
        self._token = BATCH.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # Flush while this batch is still global, as .flush() will check for it anyways
        self.flush()
        BATCH.reset(self._token)


# --- Utilities ---


def untrack(fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    with Scope():
        return fn(*args, **kwargs)


def batch(fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    with UpdateBatch():
        return fn(*args, **kwargs)


class InvariantError(Exception): ...
