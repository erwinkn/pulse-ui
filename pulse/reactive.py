from __future__ import annotations
from collections import deque
from contextvars import ContextVar, Token
from typing import Any, Callable, Generic, ParamSpec, TypeVar, List, Set, Optional

T = TypeVar("T")
P = ParamSpec("P")

# --- Globals ---

EPOCH = ContextVar("EPOCH", default=1)
SCOPE: ContextVar[Optional[Scope]] = ContextVar("pulse_scope", default=None)
BATCH: ContextVar[Optional[UpdateBatch]] = ContextVar("pulse_batch", default=None)


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
        if batch := BATCH.get():
            batch.schedule_signal(self, value)
        else:
            with UpdateBatch() as batch:
                batch.schedule_signal(self, value)


class Computed(Generic[T]):
    def __init__(self, fn: Callable[[], T], name: Optional[str] = None):
        self.fn = fn
        self.value: T = None  # type: ignore
        self.name = name
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

        self._recompute_if_necessary()
        return self.value

    def __call__(self) -> T:
        return self.read()

    def _push_change(self):
        if self.dirty:
            return

        self.dirty = True
        for obs in self.obs:
            obs._push_change()

    def _recompute(self):
        epoch = EPOCH.get()
        current_deps = set(self.deps)

        prev_value = self.value
        with Scope(parent=SCOPE.get()) as scope:
            if self.on_stack:
                raise RuntimeError("Circular dependency detected")
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
        if self.last_change < 0:
            self._recompute()
            return
        if not self.dirty:
            return

        for dep in self.deps:
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
            if dep.last_change >= self.last_change:
                self._recompute()
                return

        self.dirty = False


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
        assert batch is not None, (
            "Effect._push_change() should never be called without a BATCH ContextVar"
        )
        if self not in batch.effects:
            batch.effects.append(self)

    def _should_run(self):
        epoch = EPOCH.get()
        for dep in self.deps:
            if dep.last_change >= epoch:
                return True
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
                if dep.last_change >= epoch:
                    return True
        return False

    def _run(self):
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
        global_batch = BATCH.get()
        token = None
        if global_batch != self:
            token = BATCH.set(self)

        MAX_ITERS = 10000
        epoch = start_epoch = EPOCH.get()

        while len(self.signals) > 0:
            epoch += 1
            EPOCH.set(epoch)
            if epoch - start_epoch > MAX_ITERS:
                raise RuntimeError(
                    f"Pulse's reactive system registered more than {MAX_ITERS} iterations. There is likely an update cycle in your application.\n"
                    "This is most often caused through a state update during rerender or in an effect that ends up triggering the same rerender or effect."
                )

            current_signals = self.signals
            self.signals = []

            for signal, value in current_signals:
                signal._do_write(value)
                signal._push_change()

            current_effects = self.effects
            self.effects = []

            for effect in current_effects:
                if effect._should_run():
                    effect._run()

        if token:
            BATCH.reset(token)

    def __enter__(self):
        self._token = BATCH.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.flush()
        BATCH.reset(self._token)


def untrack(fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    with Scope():
        return fn(*args, **kwargs)


def batch(fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    with UpdateBatch():
        return fn(*args, **kwargs)


class InvariantError(Exception): ...
