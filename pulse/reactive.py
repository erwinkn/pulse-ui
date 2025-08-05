from contextvars import ContextVar
from typing import (
    Callable,
    Generic,
    ParamSpec,
    TypeVar,
    Set,
    Optional,
    overload,
)

T = TypeVar("T")
P = ParamSpec("P")

# --- Globals ---

EPOCH = ContextVar("EPOCH", default=1)
SCOPE: "ContextVar[Optional[Scope]]" = ContextVar("pulse_scope", default=None)
BATCH: "ContextVar[Optional[Batch]]" = ContextVar("pulse_batch", default=None)
IS_PRERENDERING: ContextVar[bool] = ContextVar("pulse_is_prerendering", default=False)


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

    def _add_obs(self, obs: "Computed | Effect"):
        self.obs.append(obs)

    def write(self, value: T):
        if value == self.value:
            return
        print(f"Writing to {self.name}")
        self.value = value
        self.last_change = EPOCH.get()
        # If there is no current batch, this ensures that the full graph gets
        # flagged as dirty before any effects are executed. This is necessary to
        # avoid the diamond problem.
        with EnsureBatch():
            for obs in self.obs:
                obs._push_change()

    # def _push_change(self):
    #     for obs in self.obs:
    #         obs._push_change()

    # def write(self, value: T):
    #     with EnsureBatch() as batch:
    #         batch.schedule_signal(self, value)


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

        print(f"Marking {self.name} as dirty")
        self.dirty = True
        for obs in self.obs:
            obs._push_change()

    def _recompute(self):
        epoch = EPOCH.get()
        current_deps = set(self.deps)

        prev_value = self.value
        with Scope() as scope:
            if self.on_stack:
                raise RuntimeError("Circular dependency detected")
            self.on_stack = True
            self.value = self.fn()
            self.on_stack = False
            self.dirty = False
            if prev_value != self.value:
                self.last_change = epoch

            if len(scope.effects) > 0:
                raise RuntimeError(
                    "An effect was created within a computed variable's function. "
                    "This behavior is not allowed, computed variables should be pure calculations."
                )

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


@overload
def computed(fn: Callable[[], T], *, name: Optional[str] = None) -> Computed[T]: ...
@overload
def computed(
    fn: None = None, *, name: Optional[str] = None
) -> Callable[[Callable[[], T]], Computed[T]]: ...


def computed(fn: Optional[Callable[[], T]] = None, *, name: Optional[str] = None):
    if fn is not None:
        return Computed(fn, name=name or fn.__name__)
    else:
        # For some reason, I need to add the `/` to make `fn` a positional
        # argument for the Python type checker to be happy.
        def decorator(fn: Callable[[], T], /):
            return Computed(fn, name=name or fn.__name__)

        return decorator


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
        self.children: list[Effect] = []
        # Used to detect the first run, but useful for testing/optimization
        self.runs = 0

        if scope := SCOPE.get():
            scope.effects.add(self)

        # Will either run the effect now or add it to the current batch
        self._push_change()

    def dispose(self):
        with EnsureBatch():
            # Run children cleanups first
            for child in self.children:
                child.dispose()
            if self.cleanup:
                self.cleanup()

    def _push_change(self):
        print(f"Pushed change to {self.name}")
        if batch := BATCH.get():
            batch.effects.add(self)
        else:
            if self._should_run():
                self._run()

    def _should_run(self):
        return self.runs == 0 or self._deps_changed()

    def _deps_changed(self):
        print(f"Checking if deps of {self.name} changed")
        epoch = EPOCH.get()
        for dep in self.deps:
            print("Dep")
            if dep.last_change == epoch:
                return True
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
                if dep.last_change == epoch:
                    return True
        return False

    def _run(self):
        # Skip effects during prerendering
        if IS_PRERENDERING.get():
            return

        print(f"Running effect {self.name}")
        current_deps = set(self.deps)

        with Scope() as scope, EnsureBatch():
            self.dispose()
            self.cleanup = self.fn()
            self.children = list(scope.effects)
            self.runs += 1

        new_deps = scope.accessed
        add_deps = new_deps - current_deps
        remove_deps = current_deps - new_deps
        for dep in add_deps:
            dep.obs.append(self)
        for dep in remove_deps:
            dep.obs.remove(self)

        self.deps = list(new_deps)


@overload
def effect(fn: Callable[[], None], *, name: Optional[str] = None) -> Effect: ...
@overload
def effect(
    fn: None = None, *, name: Optional[str] = None
) -> Callable[[Callable[[], None]], Effect]: ...


def effect(fn: Optional[Callable[[], None]] = None, *, name: Optional[str] = None):
    if fn is not None:
        return Effect(fn, name=name or fn.__name__)
    else:
        # For some reason, I need to add the `/` to make `fn` a positional
        # argument for the Python type checker to be happy.
        def decorator(fn: Callable[[], None], /):
            return Effect(fn, name=name or fn.__name__)

        return decorator


class Scope:
    def __init__(self):
        self.accessed: Set[Signal | Computed] = set()
        self.effects: set[Effect] = set()

    def clear(self):
        self.accessed.clear()
        self.effects.clear()

    def __enter__(self):
        self._token = SCOPE.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        SCOPE.reset(self._token)


class Batch:
    def __init__(self) -> None:
        # self.signals: list[tuple[Signal, Any]] = []
        self.effects: set[Effect] = set()

    # def schedule_signal(self, signal: Signal[T], value: T):
    #     self.signals.append((signal, value))

    def flush(self):
        global_batch = BATCH.get()
        token = None
        if global_batch != self:
            token = BATCH.set(self)

        MAX_ITERS = 10000
        epoch = start_epoch = EPOCH.get()

        while len(self.effects) > 0:
            if epoch - start_epoch > MAX_ITERS:
                raise RuntimeError(
                    f"Pulse's reactive system registered more than {MAX_ITERS} iterations. There is likely an update cycle in your application.\n"
                    "This is most often caused through a state update during rerender or in an effect that ends up triggering the same rerender or effect."
                )

            current_effects = self.effects
            self.effects = set()

            for effect in current_effects:
                if effect._should_run():
                    effect._run()

            # This ensures the epoch is incremented *after* all the signal
            # writes and associated effects have been run.
            epoch += 1
            EPOCH.set(epoch)
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


class EnsureBatch:
    def __init__(self) -> None:
        self._token = None

    def __enter__(self):
        batch = BATCH.get()
        if batch is None:
            batch = Batch()
            self._token = BATCH.set(batch)
        return batch

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self._token is not None:
            batch = BATCH.get()
            batch.flush()  # type: ignore
            BATCH.reset(self._token)


def batch():
    return Batch()


def untrack():
    return Scope()


class InvariantError(Exception): ...
