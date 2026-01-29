import inspect
import logging
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar, override

from pulse.helpers import Disposable, call_flexible

logger = logging.getLogger(__name__)


class HookError(RuntimeError):
	pass


class HookAlreadyRegisteredError(HookError):
	pass


class HookNotFoundError(HookError):
	pass


class HookRenameCollisionError(HookError):
	pass


MISSING: Any = object()


@dataclass(slots=True)
class HookMetadata:
	"""Metadata for a registered hook.

	Contains optional descriptive information about a hook, useful for
	debugging and documentation.

	Attributes:
		description: Human-readable description of the hook's purpose.
		owner: Module or package that owns this hook (e.g., "pulse.core").
		version: Version string for the hook implementation.
		extra: Additional metadata as a mapping.
	"""

	description: str | None = None
	owner: str | None = None
	version: str | None = None
	extra: Mapping[str, Any] | None = None


class HookState(Disposable):
	"""Base class for hook state returned by hook factories.

	Subclass this to create custom hook state that persists across renders.
	Override lifecycle methods to respond to render events.

	Attributes:
		render_cycle: The current render cycle number.

	Example:

	```python
	class TimerHookState(ps.hooks.State):
	    def __init__(self):
	        self.start_time = time.time()

	    def elapsed(self) -> float:
	        return time.time() - self.start_time

	    def dispose(self) -> None:
	        pass

	_timer_hook = ps.hooks.create("my_app:timer", lambda: TimerHookState())

	def use_timer() -> TimerHookState:
	    return _timer_hook()
	```
	"""

	render_cycle: int = 0

	def on_render_start(self, render_cycle: int) -> None:
		"""Called before each component render.

		Args:
			render_cycle: The current render cycle number.
		"""
		self.render_cycle = render_cycle

	def on_render_end(self, render_cycle: int) -> None:
		"""Called after the component render has completed.

		Args:
			render_cycle: The current render cycle number.
		"""
		...

	@override
	def dispose(self) -> None:
		"""Called when the hook instance is discarded.

		Override to clean up resources (close connections, cancel tasks, etc.).
		"""
		...


T = TypeVar("T", bound=HookState)

HookFactory = Callable[[], T] | Callable[["HookInit[T]"], T]


def _default_factory() -> HookState:
	return HookState()


@dataclass(slots=True)
class Hook(Generic[T]):
	"""A registered hook definition.

	Hooks are created via ``ps.hooks.create()`` and can be called during
	component render to access their associated state.

	Attributes:
		name: Unique name identifying this hook.
		factory: Function that creates new HookState instances.
		metadata: Optional metadata about the hook.
	"""

	name: str
	factory: HookFactory[T]
	metadata: HookMetadata

	def __call__(self, key: str | None = None) -> T:
		"""Get or create hook state for the current component.

		Args:
			key: Optional key for multiple instances of the same hook.

		Returns:
			The hook state instance.

		Raises:
			HookError: If called outside of a render context.
		"""
		ctx = HookContext.require(self.name)
		namespace = ctx.namespace_for(self)
		state = namespace.ensure(ctx, key)
		return state


@dataclass(slots=True)
class HookInit(Generic[T]):
	"""Initialization context passed to hook factories.

	When a hook factory accepts a single argument, it receives this object
	containing context about the initialization.

	Attributes:
		key: Optional key if the hook was called with a specific key.
		render_cycle: The current render cycle number.
		definition: Reference to the Hook definition being initialized.
	"""

	key: str | None
	render_cycle: int
	definition: Hook[T]


DEFAULT_HOOK_KEY = object()


class HookNamespace(Generic[T]):
	__slots__ = ("hook", "states")  # pyright: ignore[reportUnannotatedClassAttribute]
	hook: Hook[T]

	def __init__(self, hook: Hook[T]) -> None:
		self.hook = hook
		self.states: dict[object, T] = {}

	@staticmethod
	def _normalize_key(key: str | None) -> object:
		return key if key is not None else DEFAULT_HOOK_KEY

	def on_render_start(self, render_cycle: int):
		for state in self.states.values():
			state.on_render_start(render_cycle)

	def on_render_end(self, render_cycle: int):
		for state in self.states.values():
			state.on_render_end(render_cycle)

	def ensure(self, ctx: "HookContext", key: str | None) -> T:
		normalized = self._normalize_key(key)
		state = self.states.get(normalized)
		if state is None:
			created = call_flexible(
				self.hook.factory,
				HookInit(definition=self.hook, render_cycle=ctx.render_cycle, key=key),
			)
			if inspect.isawaitable(created):
				raise HookError(
					f"Hook factory '{self.hook.name}' returned an awaitable; "
					+ "async factories are not supported"
				)
			if not isinstance(created, HookState):
				raise HookError(
					f"Hook factory '{self.hook.name}' must return a HookState instance"
				)
			state = created
			self.states[normalized] = state
			state.on_render_start(ctx.render_cycle)
		return state

	def dispose(self) -> None:
		for key, state in self.states.items():
			try:
				state.dispose()
			except Exception:
				logger.exception(
					"Error disposing hook '%s' (key=%r)",
					self.hook.name,
					key,
				)
		self.states.clear()


class HookContext:
	render_cycle: int
	namespaces: dict[str, HookNamespace[Any]]
	_token: "Token[HookContext | None] | None"
	component_id: str | None
	signature_hash: str | None
	hot_reload_mode: bool
	hook_index: int

	def __init__(self) -> None:
		self.render_cycle = 0
		self.namespaces = {}
		self._token = None
		self.component_id = None
		self.signature_hash = None
		self.hot_reload_mode = False
		self.hook_index = 0

	@staticmethod
	def require(caller: str | None = None):
		ctx = HOOK_CONTEXT.get()
		if ctx is None:
			caller = caller or "this function"
			raise HookError(
				f"Missing hook context, {caller} was likely called outside rendering"
			)
		return ctx

	def __enter__(self):
		self.render_cycle += 1
		self._token = HOOK_CONTEXT.set(self)
		for namespace in self.namespaces.values():
			namespace.on_render_start(self.render_cycle)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_val: BaseException | None,
		exc_tb: Any,
	) -> Literal[False]:
		if self._token is not None:
			HOOK_CONTEXT.reset(self._token)
			self._token = None
			for namespace in self.namespaces.values():
				namespace.on_render_end(self.render_cycle)
		return False

	def namespace_for(self, hook: Hook[T]) -> HookNamespace[T]:
		namespace = self.namespaces.get(hook.name)
		if namespace is None:
			namespace = HookNamespace(hook)
			self.namespaces[hook.name] = namespace
		return namespace

	def unmount(self) -> None:
		for namespace in self.namespaces.values():
			namespace.dispose()
		self.namespaces.clear()


def next_hot_reload_identity(
	key: str | None, *, record: bool = False
) -> tuple[str, int] | tuple[str, str] | None:
	ctx = HOOK_CONTEXT.get()
	if ctx is None:
		return None
	if ctx.component_id is None or ctx.signature_hash is None:
		return None
	index = ctx.hook_index
	ctx.hook_index += 1
	if not (ctx.hot_reload_mode or record):
		return None
	if key is not None:
		return (ctx.component_id, key)
	return (ctx.component_id, index)


HOOK_CONTEXT: ContextVar[HookContext | None] = ContextVar(
	"pulse_hook_context", default=None
)


class HookRegistry:
	_locked: bool

	def __init__(self) -> None:
		self.hooks: dict[str, Hook[Any]] = {}
		self._locked = False

	@staticmethod
	def get():
		return HOOK_REGISTRY

	def create(
		self,
		name: str,
		factory: HookFactory[T] = _default_factory,
		metadata: HookMetadata | None = None,
	) -> Hook[T]:
		if not isinstance(name, str) or not name:
			raise ValueError("Hook name must be a non-empty string")
		hook_metadata = metadata or HookMetadata()
		if self._locked:
			raise HookError("Hook registry is locked")
		if name in self.hooks:
			raise HookAlreadyRegisteredError(f"Hook '{name}' is already registered")
		hook = Hook(
			name=name,
			factory=factory,
			metadata=hook_metadata,
		)
		self.hooks[name] = hook

		return hook

	def rename(self, current: str, new: str) -> None:
		if current == new:
			return
		if self._locked:
			raise HookError("Hook registry is locked")
		hook = self.hooks.get(current)
		if hook is None:
			raise HookNotFoundError(f"Hook '{current}' is not registered")
		if new in self.hooks:
			raise HookRenameCollisionError(f"Hook '{new}' is already registered")
		del self.hooks[current]
		hook.name = new
		self.hooks[new] = hook

	def list(self) -> list[str]:
		return sorted(self.hooks.keys())

	def describe(self, name: str) -> HookMetadata:
		definition = self.hooks.get(name)
		if definition is None:
			raise HookNotFoundError(f"Hook '{name}' is not registered")
		return definition.metadata

	def lock(self) -> None:
		self._locked = True


HOOK_REGISTRY: HookRegistry = HookRegistry()


class HooksAPI:
	"""Low-level API for creating custom hooks.

	Access via ``ps.hooks``. Provides methods for registering, listing,
	and managing hooks.

	Attributes:
		State: Alias for HookState base class.
		Metadata: Alias for HookMetadata dataclass.
		AlreadyRegisteredError: Exception for duplicate hook registration.
		NotFoundError: Exception for missing hook lookup.
		RenameCollisionError: Exception for hook rename conflicts.
	"""

	__slots__ = ()  # pyright: ignore[reportUnannotatedClassAttribute]

	State: type[HookState] = HookState
	Metadata: type[HookMetadata] = HookMetadata
	AlreadyRegisteredError: type[HookAlreadyRegisteredError] = (
		HookAlreadyRegisteredError
	)
	NotFoundError: type[HookNotFoundError] = HookNotFoundError
	RenameCollisionError: type[HookRenameCollisionError] = HookRenameCollisionError

	def create(
		self,
		name: str,
		factory: HookFactory[T] = _default_factory,
		*,
		metadata: HookMetadata | None = None,
	) -> "Hook[T]":
		"""Register a new hook.

		Args:
			name: Unique name for the hook (e.g., "my_app:timer").
			factory: Function that creates HookState instances. Can be a
				zero-argument callable or accept a HookInit object.
			metadata: Optional metadata describing the hook.

		Returns:
			Hook[T]: The registered hook, callable during component render.

		Raises:
			ValueError: If name is empty.
			HookAlreadyRegisteredError: If a hook with this name already exists.
			HookError: If the registry is locked.

		Example:

		```python
		class TimerHookState(ps.hooks.State):
		    def __init__(self):
		        self.start_time = time.time()

		    def elapsed(self) -> float:
		        return time.time() - self.start_time

		    def dispose(self) -> None:
		        pass

		_timer_hook = ps.hooks.create("my_app:timer", lambda: TimerHookState())

		def use_timer() -> TimerHookState:
		    return _timer_hook()
		```
		"""
		return HOOK_REGISTRY.create(name, factory, metadata)

	def rename(self, current: str, new: str) -> None:
		HOOK_REGISTRY.rename(current, new)

	def list(self) -> list[str]:
		return HOOK_REGISTRY.list()

	def describe(self, name: str) -> HookMetadata:
		return HOOK_REGISTRY.describe(name)

	def registry(self) -> HookRegistry:
		return HOOK_REGISTRY

	def lock(self) -> None:
		HOOK_REGISTRY.lock()


hooks = HooksAPI()


__all__ = [
	"HooksAPI",
	"HookContext",
	"Hook",
	"HookError",
	"HookInit",
	"HookMetadata",
	"HookNamespace",
	"HookNotFoundError",
	"HookRenameCollisionError",
	"HookState",
	"HookAlreadyRegisteredError",
	"HOOK_CONTEXT",
	"HookRegistry",
	"hooks",
	"MISSING",
]
