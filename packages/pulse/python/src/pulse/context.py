# pyright: reportImportCycles=false
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import MappingProxyType, TracebackType
from typing import TYPE_CHECKING, Any, Literal

from pulse.routing import RouteContext

if TYPE_CHECKING:
	from pulse.app import App
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession


@dataclass
class PulseContext:
	"""Composite context accessible to hooks and internals.

	- session: per-user session ReactiveDict
	- render: per-connection RenderSession
	- route: active RouteContext for this render/effect scope
	"""

	app: "App"
	session: "UserSession | None" = None
	render: "RenderSession | None" = None
	route: "RouteContext | None" = None
	_token: "Token[PulseContext | None] | None" = None

	@classmethod
	def get(cls):
		ctx = PULSE_CONTEXT.get()
		if ctx is None:
			raise RuntimeError("Internal error: PULSE_CONTEXT is not set")
		return ctx

	@classmethod
	def update(
		cls,
		session: "UserSession | None" = None,
		render: "RenderSession | None" = None,
		route: "RouteContext | None" = None,
	):
		ctx = cls.get()
		return PulseContext(
			app=ctx.app,
			session=session or ctx.session,
			render=render or ctx.render,
			route=route or ctx.route,
		)

	def __enter__(self):
		self._token = PULSE_CONTEXT.set(self)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None = None,
		exc_val: BaseException | None = None,
		exc_tb: TracebackType | None = None,
	) -> Literal[False]:
		if self._token is not None:
			PULSE_CONTEXT.reset(self._token)
			self._token = None
		return False


PULSE_CONTEXT: ContextVar["PulseContext | None"] = ContextVar(
	"pulse_context", default=None
)


# User-facing Pulse Context system
# Similar to React Context but Python-side


class PulseUserContextError(RuntimeError):
	"""Raised when use_pulse_context fails to find a key."""


# Stack of immutable context values, each entry is an immutable mapping
_USER_CONTEXT_STACK: ContextVar[tuple[MappingProxyType[str, Any], ...]] = ContextVar(
	"_user_context_stack", default=()
)


@contextmanager
def pulse_context(
	**kwargs: Any,
) -> Generator[MappingProxyType[str, Any], None, None]:
	"""Provide context values to child components.

	Values are immutable snapshots - changes require re-render.
	Nested pulse_context() calls stack, with inner values shadowing outer ones.

	Example:
		with pulse_context(theme="dark", user_id=123):
			# Components rendered here can access theme and user_id
			render_component()
	"""
	# Create immutable snapshot of provided values
	snapshot = MappingProxyType(kwargs)

	# Push onto stack
	stack = _USER_CONTEXT_STACK.get()
	new_stack = (*stack, snapshot)
	token = _USER_CONTEXT_STACK.set(new_stack)

	try:
		yield snapshot
	finally:
		_USER_CONTEXT_STACK.reset(token)


def use_pulse_context(key: str) -> Any:
	"""Consume a value from the nearest parent pulse_context.

	Searches the context stack from innermost to outermost, returning the
	first match. Raises PulseUserContextError if the key is not found.

	Example:
		theme = use_pulse_context("theme")  # Returns "dark" from example above
	"""
	stack = _USER_CONTEXT_STACK.get()

	# Search from innermost (last) to outermost (first)
	for context in reversed(stack):
		if key in context:
			return context[key]

	raise PulseUserContextError(
		f"Key '{key}' not found in any parent pulse_context. "
		+ f"Ensure the value is provided via pulse_context({key}=...) in a parent scope."
	)


# Type alias for context snapshot (tuple of immutable mappings)
UserContextSnapshot = tuple[MappingProxyType[str, Any], ...]


def get_user_context_snapshot() -> UserContextSnapshot:
	"""Capture current user context stack as a snapshot.

	Used by RenderSession to track context per route path.
	"""
	return _USER_CONTEXT_STACK.get()


@contextmanager
def restore_user_context(
	snapshot: UserContextSnapshot,
) -> Generator[None, None, None]:
	"""Restore user context stack from a snapshot.

	Used by RenderSession to restore parent route's context when
	rendering child routes, enabling context inheritance.

	Example:
		# In parent route, context is provided
		with pulse_context(theme="dark"):
			parent_snapshot = get_user_context_snapshot()

		# Later, when rendering child route
		with restore_user_context(parent_snapshot):
			# Child can access parent's context
			theme = use_pulse_context("theme")  # Returns "dark"
	"""
	token = _USER_CONTEXT_STACK.set(snapshot)
	try:
		yield
	finally:
		_USER_CONTEXT_STACK.reset(token)


__all__ = [
	"PULSE_CONTEXT",
	"PulseUserContextError",
	"UserContextSnapshot",
	"get_user_context_snapshot",
	"pulse_context",
	"restore_user_context",
	"use_pulse_context",
]
