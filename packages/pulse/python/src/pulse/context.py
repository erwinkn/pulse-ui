# pyright: reportImportCycles=false
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal

from pulse.errors import Errors
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
	errors: Errors = field(init=False, repr=False)
	_token: "Token[PulseContext | None] | None" = None

	def __post_init__(self) -> None:
		self.errors = Errors(self)

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
		**kwargs: Any,
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
		invalid = set(kwargs) - {"session", "render", "route"}
		if invalid:
			key = next(iter(invalid))
			raise TypeError(f"update() got an unexpected keyword argument '{key}'")

		ctx = cls.get()
		session = kwargs["session"] if "session" in kwargs else ctx.session
		render = kwargs["render"] if "render" in kwargs else ctx.render
		route = kwargs["route"] if "route" in kwargs else ctx.route
		return PulseContext(
			app=ctx.app,
			session=session,
			render=render,
			route=route,
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
		if exc_val is not None:
			render = self.render
			route = self.route
			render_id = getattr(render, "id", None) if render is not None else None
			route_path: str | None = None
			if route is not None:
				pulse_route = getattr(route, "pulse_route", None)
				if pulse_route is not None and hasattr(pulse_route, "unique_path"):
					route_path = pulse_route.unique_path()
				else:
					try:
						route_path = str(route.pathname)
					except AttributeError:
						route_path = None
			if render_id is not None:
				try:
					exc_val.__pulse_render_id__ = render_id  # pyright: ignore[reportAttributeAccessIssue]
				except Exception:
					pass
			if route_path is not None:
				try:
					exc_val.__pulse_route_path__ = route_path  # pyright: ignore[reportAttributeAccessIssue]
				except Exception:
					pass
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
