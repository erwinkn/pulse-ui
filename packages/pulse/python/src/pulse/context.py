# pyright: reportImportCycles=false
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal

from pulse.routing import RouteContext, RouteOrigin

if TYPE_CHECKING:
	from pulse.app import App
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession

_UNSET = object()


@dataclass
class PulseContext:
	"""Composite context accessible to hooks and internals.

	Manages per-request state via context variables. Provides access to the
	application instance, user session, render session, and route context.

	Attributes:
		app: Application instance.
		session: Per-user session (UserSession or None).
		render: Per-connection render session (RenderSession or None).
		route: Active live route context (RouteContext or None).
		origin: Immutable route context that originated the active callback/effect.
		mount_id: Route mount lifecycle id that originated the active callback/effect.

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
	origin: "RouteOrigin | None" = None
	mount_id: str | None = None
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
		origin: Any = _UNSET,
		mount_id: Any = _UNSET,
	) -> "PulseContext":
		"""Create a new context with updated values.

		Inherits unspecified values from the current context.

		Args:
			session: New session (optional, inherits if not provided).
			render: New render session (optional, inherits if not provided).
			route: New route context (optional, inherits if not provided).
			origin: New origin route context (optional, inherits if not provided).
			mount_id: New origin mount id (optional, inherits if not provided).

		Returns:
			New PulseContext instance with updated values.
		"""
		ctx = cls.get()
		return PulseContext(
			app=ctx.app,
			session=ctx.session if session is _UNSET else session,
			render=ctx.render if render is _UNSET else render,
			route=ctx.route if route is _UNSET else route,
			origin=ctx.origin if origin is _UNSET else origin,
			mount_id=ctx.mount_id if mount_id is _UNSET else mount_id,
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

__all__ = [
	"PULSE_CONTEXT",
]
