import inspect
from collections.abc import Callable
from types import CodeType, FrameType
from typing import Any, TypeVar, override

from pulse.component import is_component_code
from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.resources import suspend_resource_scope
from pulse.state.state import State

S = TypeVar("S", bound=State)


class StateHookState(HookState):
	"""Internal hook state for managing State instances across renders.

	Stores State instances keyed by string identifier and tracks which keys
	have been accessed during the current render cycle.
	"""

	__slots__ = ("instances", "called_keys")  # pyright: ignore[reportUnannotatedClassAttribute]
	instances: dict[tuple[str, Any], State]
	called_keys: set[tuple[str, Any]]

	def __init__(self) -> None:
		super().__init__()
		self.instances = {}
		self.called_keys = set()

	def _make_key(self, identity: Any, key: str | None) -> tuple[str, Any]:
		if key is None:
			return ("code", identity)
		return ("key", key)

	@override
	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		self.called_keys.clear()

	@override
	def on_render_end(self, render_cycle: int, error: BaseException | None) -> None:
		super().on_render_end(render_cycle, error)
		# A failed render stopped at the raise, so `called_keys` is a partial set:
		# keys after the failure point are still live. Keep every instance; the
		# next successful render decides. `called_keys` is rebuilt from scratch on
		# render start, so the partial set never leaks into that decision.
		if error is not None:
			return
		# Unseen keys only, and only here. Mid-render `called_keys` is "reached
		# so far", not "live this render" — evicting then would dispose a key
		# reused later in a loop, or an unkeyed sibling after a keyed replacement.
		for key in list(self.instances.keys()):
			if key in self.called_keys:
				continue
			instance = self.instances.pop(key)
			if instance.__disposed__:
				continue
			try:
				instance.dispose()
			except RuntimeError:
				pass

	def get_or_create_state(
		self,
		identity: Any,
		key: str | None,
		arg: State | Callable[[], State],
	) -> State:
		full_identity = self._make_key(identity, key)
		if full_identity in self.called_keys:
			if key is None:
				raise RuntimeError(
					"`pulse.state` can only be called once per component render at the same location. "
					+ "Use the `key` parameter to disambiguate: ps.state(..., key=unique_value)"
				)
			raise RuntimeError(
				f"`pulse.state` can only be called once per component render with key='{key}'"
			)
		self.called_keys.add(full_identity)

		existing = self.instances.get(full_identity)
		if existing is not None:
			# Dispose any State instances passed directly as args that aren't being used
			if isinstance(arg, State) and arg is not existing:
				arg.dispose()
			if existing.__disposed__:
				key_label = f"key='{key}'" if key is not None else "callsite"
				raise RuntimeError(
					"`pulse.state` found a disposed cached State for "
					+ key_label
					+ ". Do not dispose states returned by `pulse.state`."
				)
			return existing

		# Create new state
		instance = _instantiate_state(arg)
		if instance.__disposed__:
			raise RuntimeError(
				"`pulse.state` received a disposed State instance. "
				+ "Do not dispose states passed to `pulse.state`."
			)
		# The hook owns cached states, wherever they were constructed.
		self.resources.own(instance)
		self.instances[full_identity] = instance
		return instance

	@override
	def on_dispose(self) -> None:
		self.instances.clear()


def _instantiate_state(arg: State | Callable[[], State]) -> State:
	if callable(arg):
		with suspend_resource_scope():
			instance = arg()
	else:
		instance = arg
	if not isinstance(instance, State):
		raise TypeError(
			"`pulse.state` expects a State instance or a callable returning a State instance"
		)
	return instance


def _frame_offset(frame: FrameType) -> int:
	offset = frame.f_lasti
	if offset < 0:
		offset = frame.f_lineno
	return offset


def collect_component_identity(
	frame: FrameType,
) -> tuple[tuple[CodeType, int], ...]:
	identity: list[tuple[CodeType, int]] = []
	cursor: FrameType | None = frame
	while cursor is not None:
		identity.append((cursor.f_code, _frame_offset(cursor)))
		if is_component_code(cursor.f_code):
			return tuple(identity)
		cursor = cursor.f_back
	return tuple(identity[:1])


state_hook = hooks.create(
	"pulse:core.state",
	factory=StateHookState,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.state hook",
	),
)


def state(
	arg: S | Callable[[], S],
	*,
	key: str | None = None,
) -> S:
	"""Get or create a state instance associated with a key or callsite.

	Args:
		arg: A State instance or a callable that returns a State instance.
		key: Optional key to disambiguate multiple calls from the same location.

	Returns:
		The same State instance on subsequent renders with the same key.

	Raises:
		ValueError: If key is empty.
		RuntimeError: If called more than once per render with the same key.
		TypeError: If arg is not a State or callable returning a State.

	Example:

	```python
	def counter():
	    s = ps.state("counter", lambda: CounterState())
	    return m.Button(f"Count: {s.count}", on_click=lambda: s.increment())
	```

	Notes:
		- Key must be non-empty string
		- Can only be called once per render with the same key
		- Factory is only called on first render; subsequent renders return cached instance
		- State is disposed when the component unmounts, the key changes, or
		  the call is skipped (e.g. a false conditional)
	"""
	if key is not None and not isinstance(key, str):
		raise TypeError("state() key must be a string")

	if key == "":
		raise ValueError("state() requires a non-empty string key")

	resolved_key = key
	resolved_arg = arg

	identity: Any
	if resolved_key is None:
		frame = inspect.currentframe()
		assert frame is not None
		caller = frame.f_back
		assert caller is not None
		identity = collect_component_identity(caller)
	else:
		identity = resolved_key

	hook_state = state_hook()
	return hook_state.get_or_create_state(identity, resolved_key, resolved_arg)  # pyright: ignore[reportReturnType]


__all__ = ["state", "StateHookState"]
