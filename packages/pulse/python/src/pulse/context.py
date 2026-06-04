# pyright: reportImportCycles=false
import inspect
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from functools import wraps
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar, cast

from pulse.routing import RouteContext

if TYPE_CHECKING:
	from pulse.app import App
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession

P = ParamSpec("P")
T = TypeVar("T")
_UNSET = object()
_WRAPPED_ATTR = "__pulse_forked_context__"


@dataclass
class PulseContext:
	"""Composite context accessible to hooks and internals.

	Manages per-request state via context variables. Provides access to the
	application instance, user session, render session, and route context.

	Attributes:
		app: Application instance.
		session: Per-user session (UserSession or None).
		render: Per-connection render session (RenderSession or None).
		route: Active route context (RouteContext or None).

	Example:
		```python
		ctx = PulseContext(app=app, session=session)
		with ctx:
			# Context is active here
			current = PulseContext.get()
		# Previous context restored
		```
	"""

	app: "App"
	session: "UserSession | None" = None
	render: "RenderSession | None" = None
	route: "RouteContext | None" = None
	_token: "Token[PulseContext | None] | None" = None

	@classmethod
	def get(cls) -> "PulseContext":
		"""Get the current context.

		Returns:
			Current PulseContext instance.

		Raises:
			RuntimeError: If no context is active.
		"""
		ctx = PULSE_CONTEXT.get()
		if ctx is None:
			raise RuntimeError("Internal error: PULSE_CONTEXT is not set")
		return ctx

	@classmethod
	def update(
		cls,
		session: Any = _UNSET,
		render: Any = _UNSET,
		route: Any = _UNSET,
	) -> "PulseContext":
		"""Create a new context with updated values.

		Inherits unspecified values from the current context.

		Args:
			session: New session (optional, inherits if not provided).
			render: New render session (optional, inherits if not provided).
			route: New route context (optional, inherits if not provided).

		Returns:
			New PulseContext instance with updated values.
		"""
		ctx = cls.get()
		return PulseContext(
			app=ctx.app,
			session=ctx.session if session is _UNSET else session,
			render=ctx.render if render is _UNSET else render,
			route=ctx.route if route is _UNSET else route,
		)

	def copy(self) -> "PulseContext":
		return PulseContext(
			app=self.app,
			session=self.session,
			render=self.render,
			route=self.route,
		)

	@classmethod
	def fork(cls) -> "PulseContext":
		return cls.get().forked()

	def forked(self) -> "PulseContext":
		return PulseContext(
			app=self.app,
			session=self.session,
			render=self.render,
			route=self.route.snapshot() if self.route is not None else None,
		)

	def snapshot(self) -> "PulseContext":
		return self.forked()

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


def wrap_with_forked_context(fn: Callable[P, T]) -> Callable[P, T]:
	if getattr(fn, _WRAPPED_ATTR, False):
		return fn
	if inspect.iscoroutinefunction(fn):

		@wraps(fn)
		async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
			with PulseContext.fork():
				return await fn(*args, **kwargs)

		setattr(async_wrapper, _WRAPPED_ATTR, True)
		return cast(Callable[P, T], async_wrapper)

	@wraps(fn)
	def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
		ctx = PulseContext.fork()
		with ctx:
			result = fn(*args, **kwargs)
		if inspect.isawaitable(result):

			async def await_result() -> Any:
				with ctx:
					return await result

			return cast(T, await_result())
		return result

	setattr(wrapper, _WRAPPED_ATTR, True)
	return wrapper


__all__ = [
	"PULSE_CONTEXT",
	"wrap_with_forked_context",
]
