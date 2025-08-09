from __future__ import annotations

from typing import TypedDict, Literal, Callable, Union
from pulse.messages import ClientMessage, RouteInfo
from pulse.request import PulseRequest
from pulse.vdom import VDOM


class RequestContext(TypedDict, total=False):
    """A generic, mutable context bag propagated through prerender and WS.

    Middleware can read and write keys on this object to share information with
    later phases and with rendering code (via RenderContext hooks).
    """


class SessionContext(TypedDict, total=False):
    """Per-session context stored on WS connect and exposed to routes/hooks."""


class PrerenderOk(TypedDict):
    kind: Literal["ok"]
    vdom: VDOM


class PrerenderRedirect(TypedDict):
    kind: Literal["redirect"]
    location: str


class PrerenderUnauthorized(TypedDict):
    kind: Literal["unauthorized"]


class PrerenderNotFound(TypedDict):
    kind: Literal["not_found"]


PrerenderResponse = Union[
    PrerenderOk, PrerenderRedirect, PrerenderUnauthorized, PrerenderNotFound
]


class ConnectOk(TypedDict):
    kind: Literal["ok"]


class ConnectUnauthorized(TypedDict):
    kind: Literal["unauthorized"]


ConnectResult = Union[ConnectOk, ConnectUnauthorized]


class MessageOk(TypedDict):
    kind: Literal["ok"]


class MessageDeny(TypedDict):
    kind: Literal["deny"]


MessageResult = Union[MessageOk, MessageDeny]


class PulseMiddleware:
    """Base middleware with pass-through defaults and short-circuiting.

    Subclass and override any of the hooks. Mutate `context` to attach values
    for later use. Return a decision to allow or short-circuit the flow.
    """

    def prerender(
        self,
        *,
        path: str,
        route_info: RouteInfo,
        request: PulseRequest,
        context: dict,
        next: Callable[[], PrerenderResponse],
    ) -> PrerenderResponse:
        return next()

    def connect(
        self,
        *,
        request: PulseRequest,
        ctx: dict,
        next: Callable[[], ConnectResult],
    ) -> ConnectResult:
        return next()

    def message(
        self,
        *,
        ctx: dict,
        data: ClientMessage,
        next: Callable[[], MessageResult],
    ) -> MessageResult:
        return next()
