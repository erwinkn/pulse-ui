# This is more for documentation than actually importing from here
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any

from .reactive_extensions import ReactiveDict
from .routing import RouteContext
from .reactive import REACTIVE_CONTEXT
from .hooks import HOOK_CONTEXT
from .react_component import COMPONENT_REGISTRY

if TYPE_CHECKING:
    from .render_session import RenderSession
    from .app import App


@dataclass
class PulseContext:
    """Composite context accessible to hooks and internals.

    - session: per-user session ReactiveDict
    - render: per-connection RenderSession
    - route: active RouteContext for this render/effect scope
    """

    session: ReactiveDict[str, Any]  # pyright: ignore[reportExplicitAny]
    render: "RenderSession | None"
    route: RouteContext | None
    app: "App"
    _token: "Token[PulseContext | None] | None" = None

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
    "REACTIVE_CONTEXT",
    "PULSE_CONTEXT",
    "HOOK_CONTEXT",
    "COMPONENT_REGISTRY",
]
