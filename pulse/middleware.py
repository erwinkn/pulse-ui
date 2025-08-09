from __future__ import annotations

from typing import Generic, TypeVar, Callable, Any
from collections.abc import MutableMapping
from pulse.messages import ClientMessage, RouteInfo
from pulse.request import PulseRequest
from pulse.vdom import VDOM


T = TypeVar("T")


class Redirect:
    path: str

    def __init__(self, path: str) -> None:
        self.path = path


class NotFound: ...


class Ok(Generic[T]):
    def __init__(self, payload: T = None) -> None:
        self.payload = payload


class Deny: ...


PrerenderResponse = Ok[VDOM] | Redirect | NotFound
ConnectResponse = Ok[None] | Deny


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
        context: MutableMapping[str, Any],
        next: Callable[[], PrerenderResponse],
    ) -> PrerenderResponse:
        return next()

    def connect(
        self,
        *,
        request: PulseRequest,
        ctx: MutableMapping[str, Any],
        next: Callable[[], ConnectResponse],
    ) -> ConnectResponse:
        return next()

    def message(
        self,
        *,
        ctx: MutableMapping[str, Any],
        data: ClientMessage,
        next: Callable[[], Ok[None]],
    ) -> Ok[None] | Deny:
        """Handle per-message authorization.

        Return Deny() to block, Ok(None) to allow.
        """
        return next()
