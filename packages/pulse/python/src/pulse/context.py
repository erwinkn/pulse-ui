# pyright: reportImportCycles=false
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Literal

from pulse.routing import RouteContext

if TYPE_CHECKING:
	from pulse.app import App
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession


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
		session: "UserSession | None" = None,
		render: "RenderSession | None" = None,
		route: "RouteContext | None" = None,
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

__all__ = [
	"PULSE_CONTEXT",
]
