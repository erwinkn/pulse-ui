# pyright: reportImportCycles=false
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING

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
	):
		if self._token is not None:
			PULSE_CONTEXT.reset(self._token)
			self._token = None


PULSE_CONTEXT: ContextVar["PulseContext | None"] = ContextVar(
	"pulse_context", default=None
)

__all__ = [
	"PULSE_CONTEXT",
]
