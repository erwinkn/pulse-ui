from __future__ import annotations

from typing import Generic, TypeVar, Callable, Any
from collections.abc import MutableMapping, Sequence
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


class MiddlewareStack(PulseMiddleware):
    """Composable stack of `PulseMiddleware` executed in order.

    Each middleware receives a `next` callable that advances the chain. If a
    middleware returns without calling `next`, the chain short-circuits.
    """

    def __init__(self, middlewares: Sequence[PulseMiddleware]):
        self._middlewares: list[PulseMiddleware] = list(middlewares)

    def prerender(
        self,
        *,
        path: str,
        route_info: RouteInfo,
        request: PulseRequest,
        context: MutableMapping[str, Any],
        next: Callable[[], PrerenderResponse],
    ) -> PrerenderResponse:
        def dispatch(index: int) -> PrerenderResponse:
            if index >= len(self._middlewares):
                return next()
            mw = self._middlewares[index]

            def _next() -> PrerenderResponse:
                return dispatch(index + 1)

            return mw.prerender(
                path=path,
                route_info=route_info,
                request=request,
                context=context,
                next=_next,
            )

        return dispatch(0)

    def connect(
        self,
        *,
        request: PulseRequest,
        ctx: MutableMapping[str, Any],
        next: Callable[[], ConnectResponse],
    ) -> ConnectResponse:
        def dispatch(index: int) -> ConnectResponse:
            if index >= len(self._middlewares):
                return next()
            mw = self._middlewares[index]

            def _next() -> ConnectResponse:
                return dispatch(index + 1)

            return mw.connect(request=request, ctx=ctx, next=_next)

        return dispatch(0)

    def message(
        self,
        *,
        ctx: MutableMapping[str, Any],
        data: ClientMessage,
        next: Callable[[], Ok[None]],
    ) -> Ok[None] | Deny:
        def dispatch(index: int) -> Ok[None] | Deny:
            if index >= len(self._middlewares):
                return next()
            mw = self._middlewares[index]

            def _next() -> Ok[None]:
                return dispatch(index + 1)  # type: ignore[return-value]

            return mw.message(ctx=ctx, data=data, next=_next)

        return dispatch(0)


def stack(*middlewares: PulseMiddleware) -> PulseMiddleware:
    """Helper to build a middleware stack in code.

    Example: `app = App(..., middleware=stack(Auth(), Logging()))`
    Prefer passing a `list`/`tuple` to `App` directly.
    """
    return MiddlewareStack(list(middlewares))
