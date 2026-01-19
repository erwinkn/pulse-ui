import asyncio
import copy
import inspect
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import (
	Any,
	Generic,
	Literal,
	ParamSpec,
	TypeVar,
	override,
)

from pulse.helpers import (
	Disposable,
	create_task,
	maybe_await,
	schedule_on_loop,
	values_equal,
)

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
P = ParamSpec("P")


class Signal(Generic[T]):
	value: T
	name: str | None
	last_change: int

	def __init__(self, value: T, name: str | None = None):
		self.value = value
		self.name = name
		self.obs: list[Computed[Any] | Effect] = []
		self._obs_change_listeners: list[Callable[[int], None]] = []
		self.last_change = -1

	def read(self) -> T:
		rc = REACTIVE_CONTEXT.get()
		if rc.scope is not None:
			rc.scope.register_dep(self)
		return self.value

	def __call__(self) -> T:
		return self.read()

	def unwrap(self) -> T:
		"""Return the current value while registering subscriptions."""
		return self.read()

	def __copy__(self):
		return self.__class__(self.value, name=self.name)

	def __deepcopy__(self, memo: dict[int, Any]):
		if id(self) in memo:
			return memo[id(self)]
		new_value = copy.deepcopy(self.value, memo)
		new_signal = self.__class__(new_value, name=self.name)
		memo[id(self)] = new_signal
		return new_signal

	def add_obs(self, obs: "Computed[Any] | Effect"):
		prev = len(self.obs)
		self.obs.append(obs)
		if prev == 0 and len(self.obs) == 1:
			for cb in list(self._obs_change_listeners):
				cb(len(self.obs))

	def remove_obs(self, obs: "Computed[Any] | Effect"):
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
		if values_equal(value, self.value):
			return
		increment_epoch()
		self.value = value
		self.last_change = epoch()
		for obs in self.obs:
			obs.push_change()


class Computed(Generic[T_co]):
	fn: Callable[..., T_co]
	name: str | None
	dirty: bool
	on_stack: bool
	accepts_prev_value: bool

	def __init__(self, fn: Callable[..., T_co], name: str | None = None):
		self.fn = fn
		self.value: T_co = None  # pyright: ignore[reportAttributeAccessIssue]
		self.name = name
		self.dirty = False
		self.on_stack = False
		self.last_change: int = -1
		# Dep -> last_change
		self.deps: dict[Signal[Any] | Computed[Any], int] = {}
		self.obs: list[Computed[Any] | Effect] = []
		self._obs_change_listeners: list[Callable[[int], None]] = []
		sig = inspect.signature(self.fn)
		params = list(sig.parameters.values())
		# Check if function has at least one positional parameter
		# (excluding *args and **kwargs, and keyword-only params)
		self.accepts_prev_value = any(
			p.kind
			in (
				inspect.Parameter.POSITIONAL_ONLY,
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
			)
			for p in params
		)

	def read(self) -> T_co:
		if self.on_stack:
			raise RuntimeError("Circular dependency detected")

		rc = REACTIVE_CONTEXT.get()
		# Ensure this computed is up-to-date before registering as a dep
		self.recompute_if_necessary()
		if rc.scope is not None:
			# Register after potential recompute so the scope records the
			# latest observed version for this computed
			rc.scope.register_dep(self)
		return self.value

	def __call__(self) -> T_co:
		return self.read()

	def unwrap(self) -> T_co:
		"""Return the current value while registering subscriptions."""
		return self.read()

	def __copy__(self):
		return self.__class__(self.fn, name=self.name)

	def __deepcopy__(self, memo: dict[int, Any]):
		if id(self) in memo:
			return memo[id(self)]
		fn_copy = copy.deepcopy(self.fn, memo)
		name_copy = copy.deepcopy(self.name, memo)
		new_computed = self.__class__(fn_copy, name=name_copy)
		memo[id(self)] = new_computed
		return new_computed

	def push_change(self):
		if self.dirty:
			return

		self.dirty = True
		for obs in self.obs:
			obs.push_change()

	def _recompute(self):
		prev_value = self.value
		prev_deps = set(self.deps)
		with Scope() as scope:
			if self.on_stack:
				raise RuntimeError("Circular dependency detected")
			self.on_stack = True
			try:
				execution_epoch = epoch()
				if self.accepts_prev_value:
					self.value = self.fn(prev_value)
				else:
					self.value = self.fn()
				if epoch() != execution_epoch:
					raise RuntimeError(
						f"Detected write to a signal in computed {self.name}. Computeds should be read-only."
					)
				self.dirty = False
				if not values_equal(prev_value, self.value):
					self.last_change = execution_epoch

				if len(scope.effects) > 0:
					raise RuntimeError(
						"An effect was created within a computed variable's function. "
						+ "This is most likely unintended. If you need to create an effect here, "
						+ "wrap the effect creation with Untrack()."
					)
			finally:
				self.on_stack = False

		# Update deps and their observed versions to the values seen during this recompute
		self.deps = scope.deps
		new_deps = set(self.deps)
		add_deps = new_deps - prev_deps
		remove_deps = prev_deps - new_deps
		for dep in add_deps:
			dep.add_obs(self)
		for dep in remove_deps:
			dep.remove_obs(self)

	def recompute_if_necessary(self):
		if self.last_change < 0:
			self._recompute()
			return
		if not self.dirty:
			return

		for dep in self.deps:
			if isinstance(dep, Computed):
				dep.recompute_if_necessary()
			# Only recompute if a dependency has changed beyond the version
			# we last observed during our previous recompute
			last_seen = self.deps.get(dep, -1)
			if dep.last_change > last_seen:
				self._recompute()
				return

		self.dirty = False

	def add_obs(self, obs: "Computed[Any] | Effect"):
		prev = len(self.obs)
		self.obs.append(obs)
		if prev == 0 and len(self.obs) == 1:
			for cb in list(self._obs_change_listeners):
				cb(len(self.obs))

	def remove_obs(self, obs: "Computed[Any] | Effect"):
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
# Split effect function types into sync and async for clearer typing
EffectFn = Callable[[], EffectCleanup | None]
AsyncEffectFn = Callable[[], Awaitable[EffectCleanup | None]]


class Effect(Disposable):
	"""
	Synchronous effect and base class. Use AsyncEffect for async effects.
	Both are isinstance(Effect).
	"""

	fn: EffectFn
	name: str | None
	on_error: Callable[[Exception], None] | None
	runs: int
	last_run: int
	immediate: bool
	_lazy: bool
	_interval: float | None
	_interval_handle: asyncio.TimerHandle | None
	explicit_deps: bool
	batch: "Batch | None"
	paused: bool

	def __init__(
		self,
		fn: EffectFn,
		name: str | None = None,
		immediate: bool = False,
		lazy: bool = False,
		on_error: Callable[[Exception], None] | None = None,
		deps: list[Signal[Any] | Computed[Any]] | None = None,
		interval: float | None = None,
	):
		self.fn = fn  # type: ignore[assignment]
		self.name = name
		self.on_error = on_error
		self.cleanup_fn: EffectCleanup | None = None
		self.deps: dict[Signal[Any] | Computed[Any], int] = {}
		self.children: list[Effect] = []
		self.parent: Effect | None = None
		self.runs = 0
		self.last_run = -1
		self.scope: Scope | None = None
		self.batch = None
		self.explicit_deps = deps is not None
		self.immediate = immediate
		self._lazy = lazy
		self._interval = interval
		self._interval_handle = None
		self.paused = False

		if immediate and lazy:
			raise ValueError("An effect cannot be boht immediate and lazy")

		# Register explicit dependencies immediately upon initialization
		if deps is not None:
			self.deps = {dep: dep.last_change for dep in deps}
			for dep in deps:
				dep.add_obs(self)

		rc = REACTIVE_CONTEXT.get()
		if rc.scope is not None:
			rc.scope.register_effect(self)

		if immediate:
			self.run()
		elif not lazy:
			self.schedule()

	def _cleanup_before_run(self):
		for child in self.children:
			child._cleanup_before_run()
		if self.cleanup_fn:
			self.cleanup_fn()

	@override
	def dispose(self):
		self.cancel(cancel_interval=True)
		for child in self.children.copy():
			child.dispose()
		if self.cleanup_fn:
			self.cleanup_fn()
		for dep in self.deps:
			dep.obs.remove(self)
		if self.parent and self in self.parent.children:
			self.parent.children.remove(self)

	def _schedule_interval(self):
		"""Schedule the next interval run if interval is set."""
		if self._interval is not None and self._interval > 0:
			from pulse.helpers import later

			self._interval_handle = later(self._interval, self._on_interval)

	def _on_interval(self):
		"""Called when the interval timer fires."""
		if self._interval is not None:
			# Run directly instead of scheduling - interval runs are unconditional
			self.run()
			self._schedule_interval()

	def _cancel_interval(self):
		"""Cancel the interval timer."""
		if self._interval_handle is not None:
			self._interval_handle.cancel()
			self._interval_handle = None

	def pause(self):
		"""Pause the effect - it won't run when dependencies change."""
		self.paused = True
		self.cancel(cancel_interval=True)

	def resume(self):
		"""Resume a paused effect and schedule it to run."""
		if self.paused:
			self.paused = False
			self.schedule()

	def schedule(self):
		if self.paused:
			return
		# Immediate effects run right away when scheduled and do not enter a batch
		if self.immediate:
			self.run()
			return
		rc = REACTIVE_CONTEXT.get()
		batch = rc.batch
		batch.register_effect(self)
		self.batch = batch

	def cancel(self, cancel_interval: bool = True):
		"""
		Cancel the effect. For sync effects, removes from batch.
		For async effects (override), also cancels the running task.

		Args:
			cancel_interval: If True (default), also cancels the interval timer.
		"""
		if self.batch is not None:
			self.batch.effects.remove(self)
			self.batch = None
		if cancel_interval:
			self._cancel_interval()

	def push_change(self):
		if self.paused:
			return
		# Short-circuit if already scheduled in a batch.
		# This avoids redundant schedule() calls and O(n) list checks
		# when the same effect is reached through multiple dependency paths.
		if self.batch is not None:
			return
		self.schedule()

	def should_run(self):
		return self.runs == 0 or self._deps_changed_since_last_run()

	def _deps_changed_since_last_run(self):
		for dep in self.deps:
			if isinstance(dep, Computed):
				dep.recompute_if_necessary()
			last_seen = self.deps.get(dep, -1)
			if dep.last_change > last_seen:
				return True
		return False

	def __call__(self):
		self.run()

	def flush(self) -> None:
		"""If scheduled in a batch, remove and run immediately."""
		if self.batch is not None:
			self.batch.effects.remove(self)
			self.batch = None
			# Run now (respects IS_PRERENDERING and error handling)
			self.run()

	def handle_error(self, exc: Exception) -> None:
		if callable(self.on_error):
			self.on_error(exc)
			return
		handler = getattr(REACTIVE_CONTEXT.get(), "on_effect_error", None)
		if callable(handler):
			handler(self, exc)
			return
		raise exc

	def _apply_scope_results(
		self,
		scope: "Scope",
		captured_last_changes: dict[Signal[Any] | Computed[Any], int] | None = None,
	) -> None:
		# Apply captured last_change values at the end for explicit deps
		if self.explicit_deps:
			assert captured_last_changes is not None
			for dep, last_change in captured_last_changes.items():
				self.deps[dep] = last_change
			return

		self.children = scope.effects
		for child in self.children:
			child.parent = self

		prev_deps = set(self.deps)
		if not self.explicit_deps:
			self.deps = scope.deps
		new_deps = set(self.deps)
		add_deps = new_deps - prev_deps
		remove_deps = prev_deps - new_deps
		for dep in add_deps:
			dep.add_obs(self)
			is_dirty = isinstance(dep, Computed) and dep.dirty
			has_changed = isinstance(dep, Signal) and dep.last_change > self.deps.get(
				dep, -1
			)
			if is_dirty or has_changed:
				self.schedule()
		for dep in remove_deps:
			dep.remove_obs(self)

	def _copy_kwargs(self) -> dict[str, Any]:
		deps = None
		if self.explicit_deps:
			deps = list(self.deps.keys())
		return {
			"fn": self.fn,
			"name": self.name,
			"immediate": self.immediate,
			"lazy": self._lazy,
			"on_error": self.on_error,
			"deps": deps,
			"interval": self._interval,
		}

	def __copy__(self):
		kwargs = self._copy_kwargs()
		return type(self)(**kwargs)

	def __deepcopy__(self, memo: dict[int, Any]):
		if id(self) in memo:
			return memo[id(self)]
		kwargs = self._copy_kwargs()
		kwargs["fn"] = copy.deepcopy(self.fn, memo)
		kwargs["name"] = copy.deepcopy(self.name, memo)
		kwargs["on_error"] = copy.deepcopy(self.on_error, memo)
		deps = kwargs.get("deps")
		if deps is not None:
			kwargs["deps"] = list(deps)
		new_effect = type(self)(**kwargs)
		memo[id(self)] = new_effect
		return new_effect

	def run(self):
		with Untrack():
			try:
				self._cleanup_before_run()
			except Exception as e:
				self.handle_error(e)
		self._execute()

	def _execute(self) -> None:
		execution_epoch = epoch()
		# Capture last_change for explicit deps before running
		captured_last_changes: dict[Signal[Any] | Computed[Any], int] | None = None
		if self.explicit_deps:
			captured_last_changes = {dep: dep.last_change for dep in self.deps}
		with Scope() as scope:
			# Clear batch *before* running as we may update a signal that causes
			# this effect to be rescheduled.
			self.batch = None
			try:
				self.cleanup_fn = self.fn()
			except Exception as e:
				self.handle_error(e)
			self.runs += 1
			self.last_run = execution_epoch
		self._apply_scope_results(scope, captured_last_changes)
		# Start/restart interval if set and not currently scheduled
		if self._interval is not None and self._interval_handle is None:
			self._schedule_interval()


class AsyncEffect(Effect):
	fn: AsyncEffectFn  # pyright: ignore[reportIncompatibleMethodOverride]
	batch: None  # pyright: ignore[reportIncompatibleVariableOverride]
	_task: asyncio.Task[None] | None
	_task_started: bool

	def __init__(
		self,
		fn: AsyncEffectFn,
		name: str | None = None,
		lazy: bool = False,
		on_error: Callable[[Exception], None] | None = None,
		deps: list[Signal[Any] | Computed[Any]] | None = None,
		interval: float | None = None,
	):
		# Track an async task when running async effects
		self._task = None
		self._task_started = False
		super().__init__(
			fn=fn,  # pyright: ignore[reportArgumentType]
			name=name,
			immediate=False,
			lazy=lazy,
			on_error=on_error,
			deps=deps,
			interval=interval,
		)

	@override
	def push_change(self):
		# Short-circuit if task exists but hasn't started executing yet.
		# This avoids cancelling and recreating tasks multiple times when reached
		# through multiple dependency paths before the event loop runs.
		# Once the task starts running, new push_change calls will cancel and restart.
		if self._task is not None and not self._task.done() and not self._task_started:
			return
		self.schedule()

	@override
	def schedule(self):
		"""
		Schedule the async effect. Unlike synchronous effects, async effects do not
		go through batches, they cancel the previous run and create a new task
		immediately..
		"""
		self.run()

	@property
	def is_scheduled(self) -> bool:
		return self._task is not None

	@override
	def _copy_kwargs(self):
		kwargs = super()._copy_kwargs()
		kwargs.pop("immediate", None)
		return kwargs

	@override
	def run(self) -> asyncio.Task[Any]:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""
		Run the async effect immediately, cancelling any previous run.
		Returns the asyncio.Task.
		"""
		execution_epoch = epoch()

		# Cancel any previous run still in flight, but preserve the interval
		self.cancel(cancel_interval=False)
		this_task: asyncio.Task[None] | None = None

		async def _runner():
			nonlocal execution_epoch, this_task
			try:
				self._task_started = True
				# Perform cleanups in the new task
				with Untrack():
					try:
						self._cleanup_before_run()
					except Exception as e:
						self.handle_error(e)

				# Capture last_change for explicit deps before running
				captured_last_changes: dict[Signal[Any] | Computed[Any], int] | None = (
					None
				)
				if self.explicit_deps:
					captured_last_changes = {dep: dep.last_change for dep in self.deps}

				with Scope() as scope:
					try:
						result = self.fn()
						self.cleanup_fn = await maybe_await(result)
					except asyncio.CancelledError:
						# Re-raise so finally block executes to clear task reference
						raise
					except Exception as e:
						self.handle_error(e)
					self.runs += 1
					self.last_run = execution_epoch
				self._apply_scope_results(scope, captured_last_changes)
				# Start/restart interval if set and not currently scheduled
				if self._interval is not None and self._interval_handle is None:
					self._schedule_interval()
			finally:
				# Clear the task reference when it finishes
				if self._task is this_task:
					self._task = None
					self._task_started = False

		this_task = create_task(_runner(), name=f"effect:{self.name or 'unnamed'}")
		self._task = this_task
		return this_task

	@override
	async def __call__(self):  # pyright: ignore[reportIncompatibleMethodOverride]
		await self.run()

	@override
	def cancel(self, cancel_interval: bool = True) -> None:
		"""
		Cancel the async effect. Cancels the running task and optionally the interval.

		Args:
			cancel_interval: If True (default), also cancels the interval timer.
		"""
		if self._task:
			t = self._task
			self._task = None
			if not t.cancelled():
				t.cancel()
		if cancel_interval:
			self._cancel_interval()

	async def wait(self) -> None:
		"""
		Wait until the completion of the current task if it's already running.
		Does not start a new task if none is running.
		If the task is cancelled while waiting, waits for a new task if one is started.
		"""
		while True:
			if self._task is None or self._task.done():
				# No task running, return immediately
				return
			try:
				await self._task
				return
			except asyncio.CancelledError:
				# If wait() itself is cancelled, propagate it
				current_task = asyncio.current_task()
				if current_task is not None and (
					current_task.cancelling() > 0 or current_task.cancelled()
				):
					raise
				# Effect task was cancelled, check if a new task was started
				# and continue waiting if so
				continue

	@override
	def dispose(self):
		# Run children cleanups first, then cancel in-flight task and interval
		self.cancel(cancel_interval=True)
		for child in self.children.copy():
			child.dispose()
		if self.cleanup_fn:
			self.cleanup_fn()
		for dep in self.deps:
			dep.obs.remove(self)
		if self.parent and self in self.parent.children:
			self.parent.children.remove(self)


class Batch:
	name: str | None
	flush_id: int

	def __init__(
		self, effects: list[Effect] | None = None, name: str | None = None
	) -> None:
		self.effects: list[Effect] = effects or []
		self.name = name
		self.flush_id = 0
		self._token: "Token[ReactiveContext] | None" = None

	def register_effect(self, effect: Effect):
		if effect not in self.effects:
			self.effects.append(effect)

	def flush(self):
		token = None
		rc = REACTIVE_CONTEXT.get()
		if rc.batch is not self:
			token = REACTIVE_CONTEXT.set(ReactiveContext(rc.epoch, self, rc.scope))

		self.flush_id += 1
		MAX_ITERS = 10000
		iters = 0

		while len(self.effects) > 0:
			if iters > MAX_ITERS:
				raise RuntimeError(
					f"Pulse's reactive system registered more than {MAX_ITERS} iterations. There is likely an update cycle in your application.\n"
					+ "This is most often caused through a state update during rerender or in an effect that ends up triggering the same rerender or effect."
				)

			# This ensures the epoch is incremented *after* all the signal
			# writes and associated effects have been run.

			current_effects = self.effects
			self.effects = []

			for effect in current_effects:
				effect.batch = None
				if not effect.should_run():
					continue
				try:
					effect.run()
				except Exception as exc:
					effect.handle_error(exc)

			iters += 1

		if token:
			REACTIVE_CONTEXT.reset(token)

	def __enter__(self):
		rc = REACTIVE_CONTEXT.get()
		# Create a new immutable reactive context with updated batch
		self._token = REACTIVE_CONTEXT.set(
			ReactiveContext(rc.epoch, self, rc.scope, rc.on_effect_error)
		)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		exc_traceback: Any,
	) -> Literal[False]:
		self.flush()
		# Restore previous reactive context
		if self._token:
			REACTIVE_CONTEXT.reset(self._token)
		return False


class GlobalBatch(Batch):
	is_scheduled: bool

	def __init__(self) -> None:
		self.is_scheduled = False
		super().__init__()

	@override
	def register_effect(self, effect: Effect):
		if not self.is_scheduled:
			schedule_on_loop(self.flush)
			self.is_scheduled = True
		return super().register_effect(effect)

	@override
	def flush(self):
		super().flush()
		self.is_scheduled = False


class IgnoreBatch(Batch):
	"""
	A batch that ignores effect registrations and does nothing when flushed.
	Used during State initialization to prevent effects from running during setup.
	"""

	@override
	def register_effect(self, effect: Effect):
		# Silently ignore effect registrations during initialization
		pass

	@override
	def flush(self):
		# No-op: don't run any effects
		pass


class Epoch:
	current: int

	def __init__(self, current: int = 0) -> None:
		self.current = current


# Used to track dependencies and effects created within a certain function or
# context.
class Scope:
	def __init__(self):
		# Dict preserves insertion order. Maps dependency -> last_change
		self.deps: dict[Signal[Any] | Computed[Any], int] = {}
		self.effects: list[Effect] = []
		self._token: "Token[ReactiveContext] | None" = None

	def register_effect(self, effect: "Effect"):
		if effect not in self.effects:
			self.effects.append(effect)

	def register_dep(self, value: "Signal[Any] | Computed[Any]"):
		self.deps[value] = value.last_change

	def __enter__(self):
		rc = REACTIVE_CONTEXT.get()
		# Create a new immutable reactive context with updated scope
		self._token = REACTIVE_CONTEXT.set(
			ReactiveContext(rc.epoch, rc.batch, self, rc.on_effect_error)
		)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		exc_traceback: Any,
	) -> Literal[False]:
		# Restore previous reactive context
		if self._token:
			REACTIVE_CONTEXT.reset(self._token)
		return False


class Untrack(Scope): ...


# --- Reactive Context (composite of epoch, batch, scope) ---
class ReactiveContext:
	epoch: Epoch
	batch: Batch
	scope: Scope | None
	on_effect_error: Callable[[Effect, Exception], None] | None
	_tokens: list[Any]

	def __init__(
		self,
		epoch: Epoch | None = None,
		batch: Batch | None = None,
		scope: Scope | None = None,
		on_effect_error: Callable[[Effect, Exception], None] | None = None,
	) -> None:
		self.epoch = epoch or Epoch()
		self.batch = batch or GlobalBatch()
		self.scope = scope
		# Optional effect error handler set by integrators (e.g., session)
		self.on_effect_error = on_effect_error
		self._tokens = []

	def get_epoch(self) -> int:
		return self.epoch.current

	def increment_epoch(self) -> None:
		self.epoch.current += 1

	def __enter__(self):
		self._tokens.append(REACTIVE_CONTEXT.set(self))
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		exc_tb: Any,
	) -> Literal[False]:
		REACTIVE_CONTEXT.reset(self._tokens.pop())
		return False


def epoch():
	return REACTIVE_CONTEXT.get().get_epoch()


def increment_epoch():
	return REACTIVE_CONTEXT.get().increment_epoch()


# Default global context (used in tests / outside app)
REACTIVE_CONTEXT: ContextVar[ReactiveContext] = ContextVar(
	"pulse_reactive_context",
	default=ReactiveContext(Epoch(), GlobalBatch()),  # noqa: B039
)


def flush_effects():
	REACTIVE_CONTEXT.get().batch.flush()


class InvariantError(Exception): ...
