import asyncio
from contextvars import ContextVar
from typing import (
    Callable,
    Generic,
    ParamSpec,
    TypeVar,
    Optional,
)


from pulse.flags import IS_PRERENDERING

T = TypeVar("T")
P = ParamSpec("P")

# NOTE: globals at the bottom of the file


# Used to track dependencies and effects created within a certain function or
# context.
class Scope:
    def __init__(self):
        # Use lists to preserve insertion order
        self.deps: list[Signal | Computed] = []
        self.effects: list[Effect] = []

    def register_effect(self, effect: "Effect"):
        if effect not in self.effects:
            self.effects.append(effect)

    def register_dep(self, value: "Signal | Computed"):
        if value not in self.deps:
            self.deps.append(value)

    def __enter__(self):
        self._prev = SCOPE.get()
        SCOPE.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        SCOPE.set(self._prev)
        self._prev = None


class EmptyScope(Scope): ...


class Signal(Generic[T]):
    def __init__(self, value: T, name: Optional[str] = None):
        self.value = value
        self.name = name
        self.obs: list[Computed | Effect] = []
        self.last_change = -1

    def read(self) -> T:
        if scope := SCOPE.get():
            scope.register_dep(self)
        return self.value

    def __call__(self) -> T:
        return self.read()

    def _add_obs(self, obs: "Computed | Effect"):
        self.obs.append(obs)

    def write(self, value: T):
        if value == self.value:
            return
        increment_epoch()
        self.value = value
        self.last_change = epoch()
        for obs in self.obs:
            obs._push_change()


class Computed(Generic[T]):
    def __init__(self, fn: Callable[..., T], name: Optional[str] = None):
        self.fn = fn
        self.value: T = None  # type: ignore
        self.name = name
        self.dirty = False
        self.on_stack = False
        self.last_change: int = -1
        self.deps: list[Signal | Computed] = []
        self.obs: list[Computed | Effect] = []

    def read(self) -> T:
        if self.on_stack:
            raise RuntimeError("Circular dependency detected")

        if scope := SCOPE.get():
            scope.register_dep(self)

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
        prev_value = self.value
        prev_deps = set(self.deps)
        with Scope() as scope:
            if self.on_stack:
                raise RuntimeError("Circular dependency detected")
            self.on_stack = True
            execution_epoch = epoch()
            self.value = self.fn()
            if epoch() != execution_epoch:
                raise RuntimeError(
                    f"Detected write to a signal in computed {self.name}. Computeds should be read-only."
                )
            self.on_stack = False
            self.dirty = False
            if prev_value != self.value:
                self.last_change = execution_epoch

            if len(scope.effects) > 0:
                raise RuntimeError(
                    "An effect was created within a computed variable's function. "
                    "This behavior is not allowed, computed variables should be pure calculations."
                )

        self.deps = scope.deps
        new_deps = set(self.deps)
        add_deps = new_deps - prev_deps
        remove_deps = prev_deps - new_deps
        for dep in add_deps:
            dep.obs.append(self)
        for dep in remove_deps:
            dep.obs.remove(self)

    def _recompute_if_necessary(self):
        if self.last_change < 0:
            self._recompute()
            return
        if not self.dirty:
            return

        for dep in self.deps:
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
            if dep.last_change > self.last_change:
                self._recompute()
                return

        self.dirty = False


EffectFnWithoutCleanup = Callable[[], None]
EffectCleanup = Callable[[], None]
EffectFnWithCleanup = Callable[[], EffectCleanup]
EffectFn = EffectFnWithCleanup | EffectFnWithoutCleanup


class Effect:
    def __init__(
        self, fn: EffectFn, name: Optional[str] = None, immediate=False, lazy=False
    ):
        self.fn: EffectFn = fn
        self.name: Optional[str] = name
        self.cleanup_fn: Optional[EffectCleanup] = None
        self.deps: list[Signal | Computed] = []
        self.children: list[Effect] = []
        self.parent: Optional[Effect] = None
        # Used to detect the first run, but useful for testing/optimization
        self.runs: int = 0
        self.last_run: int = -1
        self.scope: Optional[Scope] = None
        self.batch: Optional[Batch] = None

        if immediate and lazy:
            raise ValueError("An effect cannot be boht immediate and lazy")

        if scope := SCOPE.get():
            scope.register_effect(self)

        # Will either run the effect now or add it to the current batch
        if immediate:
            self.run()
        elif not lazy:
            self.schedule()

    def _cleanup_before_run(self):
        # Run children cleanups first
        for child in self.children:
            child._cleanup_before_run()
        if self.cleanup_fn:
            self.cleanup_fn()

    def dispose(self):
        # Run children cleanups first. Children will unregister themselves, so
        # self.children will change size -> convert to a list first.
        for child in self.children.copy():
            child.dispose()
        if self.cleanup_fn:
            self.cleanup_fn()
        for dep in self.deps:
            dep.obs.remove(self)
        if self.parent:
            self.parent.children.remove(self)
        if self.batch:
            self.batch.effects.remove(self)

    def schedule(self):
        batch = BATCH.get()
        batch.register_effect(self)
        self.batch = batch

    def _push_change(self):
        self.schedule()

    def _should_run(self):
        return self.runs == 0 or self._deps_changed_since_last_run()

    def _deps_changed_since_last_run(self):
        for dep in self.deps:
            if dep.last_change > self.last_run:
                return True
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
                if dep.last_change > self.last_run:
                    return True
        return False

    def __call__(self):
        self.run()

    def run(self):
        # Skip effects during prerendering
        if IS_PRERENDERING.get():
            return

        # Don't track what happens in the cleanup
        with untrack():
            # Run children cleanup first
            self._cleanup_before_run()

        prev_deps = set(self.deps)
        execution_epoch = epoch()
        with Scope() as scope:
            # Clear batch *before* running as we may update a signal that causes
            # this effect to be rescheduled.
            self.batch = None
            self.cleanup_fn = self.fn()
            self.runs += 1
            self.last_run = execution_epoch

        self.children = scope.effects
        for child in self.children:
            child.parent = self
        self.deps = scope.deps
        new_deps = set(self.deps)
        add_deps = new_deps - prev_deps
        remove_deps = prev_deps - new_deps
        for dep in add_deps:
            dep.obs.append(self)
        for dep in remove_deps:
            dep.obs.remove(self)

        if self._deps_changed_since_last_run():
            self.schedule()


class Batch:
    def __init__(self) -> None:
        self.effects: list[Effect] = []

    def register_effect(self, effect: Effect):
        if effect not in self.effects:
            self.effects.append(effect)

    def flush(self):
        global_batch = BATCH.get()
        token = None
        if global_batch != self:
            token = BATCH.set(self)

        MAX_ITERS = 10000
        iters = 0

        while len(self.effects) > 0:
            if iters > MAX_ITERS:
                raise RuntimeError(
                    f"Pulse's reactive system registered more than {MAX_ITERS} iterations. There is likely an update cycle in your application.\n"
                    "This is most often caused through a state update during rerender or in an effect that ends up triggering the same rerender or effect."
                )

            # This ensures the epoch is incremented *after* all the signal
            # writes and associated effects have been run.

            current_effects = self.effects
            self.effects = []

            for effect in current_effects:
                if effect._should_run():
                    effect.run()

            iters += 1

        if token:
            BATCH.reset(token)

    def __enter__(self):
        self._token = BATCH.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.flush()
        # Reset AFTER flushing, as the batch needs to capture any signals or
        # effects triggered while flushing.
        BATCH.reset(self._token)


class GlobalBatch(Batch):
    def __init__(self) -> None:
        self.is_scheduled = False
        super().__init__()

    def register_effect(self, effect: Effect):
        if not self.is_scheduled:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self.flush)
                self.is_scheduled = True
            except RuntimeError:
                pass
        return super().register_effect(effect)

    def flush(self):
        super().flush()
        self.is_scheduled = False


def flush_effects():
    BATCH.get().flush()


def batch():
    return Batch()


def untrack():
    return EmptyScope()


class InvariantError(Exception): ...


# --- Globals ---
class Epoch:
    current: int = 0


EPOCH = ContextVar("pulse_epoch", default=Epoch())
SCOPE: ContextVar[Optional[Scope]] = ContextVar("pulse_scope", default=None)
BATCH: ContextVar[Batch] = ContextVar("pulse_batch", default=GlobalBatch())


def epoch():
    return EPOCH.get().current


def increment_epoch():
    EPOCH.get().current += 1
