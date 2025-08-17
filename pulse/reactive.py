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


class Signal(Generic[T]):
    def __init__(self, value: T, name: Optional[str] = None):
        self.value = value
        self.name = name
        self.obs: list[Computed | Effect] = []
        self._obs_change_listeners: list[Callable[[int], None]] = []
        self.last_change = -1

    def read(self) -> T:
        rc = REACTIVE_CONTEXT.get()
        if rc.scope is not None:
            rc.scope.register_dep(self)
        return self.value

    def __call__(self) -> T:
        return self.read()

    def _add_obs(self, obs: "Computed | Effect"):
        prev = len(self.obs)
        self.obs.append(obs)
        if prev == 0 and len(self.obs) == 1:
            for cb in list(self._obs_change_listeners):
                cb(len(self.obs))

    def _remove_obs(self, obs: "Computed | Effect"):
        if obs in self.obs:
            self.obs.remove(obs)
            if len(self.obs) == 0:
                for cb in list(self._obs_change_listeners):
                    cb(0)

    def on_observer_change(self, cb: Callable[[int], None]) -> Callable[[], None]:
        self._obs_change_listeners.append(cb)

        def off():
            try:
                self._obs_change_listeners.remove(cb)
            except ValueError:
                pass

        return off

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
        # Dep -> last_change
        self.deps: dict[Signal | Computed, int] = {}
        self.obs: list[Computed | Effect] = []
        self._obs_change_listeners: list[Callable[[int], None]] = []

    def read(self) -> T:
        if self.on_stack:
            raise RuntimeError("Circular dependency detected")

        rc = REACTIVE_CONTEXT.get()
        # Ensure this computed is up-to-date before registering as a dep
        self._recompute_if_necessary()
        if rc.scope is not None:
            # Register after potential recompute so the scope records the
            # latest observed version for this computed
            rc.scope.register_dep(self)
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

        # Update deps and their observed versions to the values seen during this recompute
        self.deps = scope.deps
        new_deps = set(self.deps)
        add_deps = new_deps - prev_deps
        remove_deps = prev_deps - new_deps
        for dep in add_deps:
            dep._add_obs(self)
        for dep in remove_deps:
            dep._remove_obs(self)

    def _recompute_if_necessary(self):
        if self.last_change < 0:
            self._recompute()
            return
        if not self.dirty:
            return

        for dep in self.deps:
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
            # Only recompute if a dependency has changed beyond the version
            # we last observed during our previous recompute
            last_seen = self.deps.get(dep, -1)
            if dep.last_change > last_seen:
                self._recompute()
                return

        self.dirty = False

    def _add_obs(self, obs: "Computed | Effect"):
        prev = len(self.obs)
        self.obs.append(obs)
        if prev == 0 and len(self.obs) == 1:
            for cb in list(self._obs_change_listeners):
                cb(len(self.obs))

    def _remove_obs(self, obs: "Computed | Effect"):
        if obs in self.obs:
            self.obs.remove(obs)
            if len(self.obs) == 0:
                for cb in list(self._obs_change_listeners):
                    cb(0)

    def on_observer_change(self, cb: Callable[[int], None]) -> Callable[[], None]:
        self._obs_change_listeners.append(cb)

        def off():
            try:
                self._obs_change_listeners.remove(cb)
            except ValueError:
                pass

        return off


EffectCleanup = Callable[[], None]
EffectFn = Callable[[], Optional[EffectCleanup]]


class Effect:
    def __init__(
        self,
        fn: EffectFn,
        name: Optional[str] = None,
        immediate: bool = False,
        lazy: bool = False,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        self.fn: EffectFn = fn
        self.name: Optional[str] = name
        self.on_error: Optional[Callable[[Exception], None]] = on_error
        self.cleanup_fn: Optional[EffectCleanup] = None
        self.deps: dict[Signal | Computed, int] = {}
        self.children: list[Effect] = []
        self.parent: Optional[Effect] = None
        # Used to detect the first run, but useful for testing/optimization
        self.runs: int = 0
        self.last_run: int = -1
        self.scope: Optional[Scope] = None
        self.batch: Optional[Batch] = None

        if immediate and lazy:
            raise ValueError("An effect cannot be boht immediate and lazy")

        rc = REACTIVE_CONTEXT.get()
        if rc.scope is not None:
            rc.scope.register_effect(self)

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
        # Prefer composite reactive context if set
        rc = REACTIVE_CONTEXT.get()
        batch = rc.batch
        batch.register_effect(self)
        self.batch = batch

    def _push_change(self):
        self.schedule()

    def _should_run(self):
        return self.runs == 0 or self._deps_changed_since_last_run()

    def _deps_changed_since_last_run(self):
        for dep in self.deps:
            if isinstance(dep, Computed):
                dep._recompute_if_necessary()
            last_seen = self.deps.get(dep, -1)
            if dep.last_change > last_seen:
                return True
        return False

    def __call__(self):
        self.run()

    def _handle_error(self, exc: Exception) -> None:
        """Handle an exception raised during this effect's execution.

        Preference order:
        1) This effect's on_error handler, if provided
        2) Reactive context's on_effect_error handler, if provided
        3) Re-raise the exception
        """
        if callable(self.on_error):
            self.on_error(exc)
            return
        # Report via reactive context if a handler is present
        handler = getattr(REACTIVE_CONTEXT.get(), "on_effect_error", None)
        if callable(handler):
            handler(self, exc)
            return
        raise exc

    def run(self):
        # Skip effects during prerendering
        if IS_PRERENDERING.get():
            return

        # Don't track what happens in the cleanup
        with Untrack():
            # Run children cleanup first
            try:
                self._cleanup_before_run()
            except Exception as e:
                self._handle_error(e)

        prev_deps = set(self.deps)
        execution_epoch = epoch()
        with Scope() as scope:
            # Clear batch *before* running as we may update a signal that causes
            # this effect to be rescheduled.
            self.batch = None
            try:
                self.cleanup_fn = self.fn()
            except Exception as e:
                self._handle_error(e)
            self.runs += 1
            self.last_run = execution_epoch

        # Update children
        self.children = scope.effects
        for child in self.children:
            child.parent = self

        # Update deps
        self.deps = scope.deps
        new_deps = set(self.deps)
        add_deps = new_deps - prev_deps
        remove_deps = prev_deps - new_deps
        for dep in add_deps:
            dep._add_obs(self)
            # New dependencies may have been affected by this run of the effect.
            # If that's the case, we should reschedule it.
            is_dirty = isinstance(dep, Computed) and dep.dirty
            has_changed = isinstance(dep, Signal) and dep.last_change > self.deps.get(
                dep, -1
            )
            if is_dirty or has_changed:
                self.schedule()
        for dep in remove_deps:
            dep._remove_obs(self)


class Batch:
    def __init__(
        self, effects: Optional[list[Effect]] = None, name: Optional[str] = None
    ) -> None:
        self.effects: list[Effect] = effects or []
        self.name = name

    def register_effect(self, effect: Effect):
        if effect not in self.effects:
            self.effects.append(effect)

    def flush(self):
        token = None
        rc = REACTIVE_CONTEXT.get()
        if rc.batch is not self:
            token = REACTIVE_CONTEXT.set(ReactiveContext(rc.epoch, self, rc.scope))

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
                if not effect._should_run():
                    continue
                try:
                    effect.run()
                except Exception as exc:
                    effect._handle_error(exc)

            iters += 1

        if token:
            REACTIVE_CONTEXT.reset(token)

    def __enter__(self):
        rc = REACTIVE_CONTEXT.get()
        self._parent = rc.batch
        rc.batch = self
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.flush()
        rc = REACTIVE_CONTEXT.get()
        rc.batch = self._parent


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


class IgnoreBatch(Batch):
    """
    A batch that ignores effect registrations and does nothing when flushed.
    Used during State initialization to prevent effects from running during setup.
    """

    def register_effect(self, effect: Effect):
        # Silently ignore effect registrations during initialization
        pass

    def flush(self):
        # No-op: don't run any effects
        pass


class Epoch:
    def __init__(self, current: int = 0) -> None:
        self.current = current


# Used to track dependencies and effects created within a certain function or
# context.
class Scope:
    def __init__(self):
        # Dict preserves insertion order. Maps dependency -> last_change
        self.deps: dict[Signal | Computed, int] = {}
        self.effects: list[Effect] = []

    def register_effect(self, effect: "Effect"):
        if effect not in self.effects:
            self.effects.append(effect)

    def register_dep(self, value: "Signal | Computed"):
        self.deps[value] = value.last_change

    def __enter__(self):
        rc = REACTIVE_CONTEXT.get()
        self._parent = rc.scope
        rc.scope = self
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        rc = REACTIVE_CONTEXT.get()
        rc.scope = self._parent


class Untrack(Scope): ...


# --- Reactive Context (composite of epoch, batch, scope) ---
class ReactiveContext:
    def __init__(
        self,
        epoch: Optional[Epoch] = None,
        batch: Optional[Batch] = None,
        scope: Optional[Scope] = None,
        on_effect_error: Optional[Callable[[Effect, Exception], None]] = None,
    ) -> None:
        self.epoch = epoch or Epoch()
        self.batch = batch or GlobalBatch()
        self.scope = scope
        # Optional effect error handler set by integrators (e.g., session)
        self.on_effect_error = on_effect_error

    def get_epoch(self) -> int:
        return self.epoch.current

    def increment_epoch(self) -> None:
        self.epoch.current += 1

    def __enter__(self):
        self._tok_rc = REACTIVE_CONTEXT.set(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        REACTIVE_CONTEXT.reset(self._tok_rc)


def epoch():
    return REACTIVE_CONTEXT.get().get_epoch()


def increment_epoch():
    return REACTIVE_CONTEXT.get().increment_epoch()


# Default global context (used in tests / outside app)
REACTIVE_CONTEXT: ContextVar[ReactiveContext] = ContextVar(
    "pulse_reactive_context", default=ReactiveContext(Epoch(), GlobalBatch())
)


def flush_effects():
    REACTIVE_CONTEXT.get().batch.flush()


class InvariantError(Exception): ...
