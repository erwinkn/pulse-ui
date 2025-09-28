from __future__ import annotations

from typing import (
    Any,
    Callable,
    Generic,
    Literal,
    Mapping,
    NoReturn,
    Optional,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
)

from pulse.context import PulseContext
from pulse.reactive_extensions import ReactiveDict
from pulse.routing import RouteContext
from pulse.state import State

from .core import HOOK_CONTEXT


class RedirectInterrupt(Exception):
    def __init__(self, path: str, *, replace: bool = False):
        super().__init__(path)
        self.path = path
        self.replace = replace


class NotFoundInterrupt(Exception):
    pass


def route() -> RouteContext:
    ctx = PulseContext.get()
    if not ctx or not ctx.route:
        raise RuntimeError(
            "`pulse.route` can only be called within a component during rendering."
        )
    return ctx.route


def session() -> ReactiveDict[str, Any]:
    ctx = PulseContext.get()
    if not ctx.session:
        raise RuntimeError("Could not resolve user session")
    return ctx.session.data


def session_id() -> str:
    ctx = PulseContext.get()
    if not ctx.session:
        raise RuntimeError("Could not resolve user session")
    return ctx.session.sid


def websocket_id() -> str:
    ctx = PulseContext.get()
    if not ctx.render:
        raise RuntimeError("Could not resolve WebSocket session")
    return ctx.render.id


async def call_api(
    path: str,
    *,
    method: str = "POST",
    headers: Mapping[str, str] | None = None,
    body: Any | None = None,
    credentials: str = "include",
) -> dict[str, Any]:
    ctx = PulseContext.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError("call_api() must be invoked inside a Pulse callback context")

    return await ctx.render.call_api(
        path,
        method=method,
        headers=dict(headers or {}),
        body=body,
        credentials=credentials,
    )


async def set_cookie(
    name: str,
    value: str,
    domain: Optional[str] = None,
    secure: bool = True,
    samesite: Literal["lax", "strict", "none"] = "lax",
    max_age_seconds: int = 7 * 24 * 3600,
) -> None:
    ctx = PulseContext.get()
    if ctx.session is None:
        raise RuntimeError("Could not resolve the user session")
    ctx.session.set_cookie(
        name=name,
        value=value,
        domain=domain,
        secure=secure,
        samesite=samesite,
        max_age_seconds=max_age_seconds,
    )


def navigate(path: str, *, replace: bool = False) -> None:
    ctx = PulseContext.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError("navigate() must be invoked inside a Pulse callback context")
    ctx.render.send({"type": "navigate_to", "path": path, "replace": replace})


def redirect(path: str, *, replace: bool = False) -> NoReturn:
    ctx = HOOK_CONTEXT.get()
    if not ctx:
        raise RuntimeError("redirect() must be invoked during component render")
    raise RedirectInterrupt(path, replace=replace)


def not_found() -> NoReturn:
    ctx = HOOK_CONTEXT.get()
    if not ctx:
        raise RuntimeError("not_found() must be invoked during component render")
    raise NotFoundInterrupt()


def server_address() -> str:
    ctx = PulseContext.get()
    if ctx is None or ctx.render is None:
        raise RuntimeError(
            "server_address() must be called inside a Pulse render/callback context"
        )
    if not ctx.render.server_address:
        raise RuntimeError(
            "Server address unavailable. Ensure App.run_codegen/asgi_factory configured server_address."
        )
    return ctx.render.server_address


def client_address() -> str:
    ctx = PulseContext.get()
    if ctx.render is None:
        raise RuntimeError(
            "client_address() must be called inside a Pulse render/callback context"
        )
    if not ctx.render.client_address:
        raise RuntimeError(
            "Client address unavailable. It is set during prerender or socket connect."
        )
    return ctx.render.client_address


P = ParamSpec("P")
S = TypeVar("S", covariant=True, bound=State)


class GlobalStateAccessor(Protocol, Generic[P, S]):
    def __call__(
        self, id: str | None = None, *args: P.args, **kwargs: P.kwargs
    ) -> S: ...


GLOBAL_STATES: dict[str, State] = {}


def global_state(
    factory: Callable[P, S] | type[S], key: str | None = None
) -> GlobalStateAccessor[P, S]:
    if isinstance(factory, type):
        cls = factory

        def _mk(*args: P.args, **kwargs: P.kwargs) -> S:
            return cast(S, cls(*args, **kwargs))

        default_key = f"{cls.__module__}:{cls.__qualname__}"
        mk = _mk
    else:
        default_key = f"{factory.__module__}:{factory.__qualname__}"
        mk = factory

    base_key = key or default_key

    def accessor(id: str | None = None, *args: P.args, **kwargs: P.kwargs) -> S:
        if id is not None:
            shared_key = f"{base_key}|{id}"
            inst = cast(S | None, GLOBAL_STATES.get(shared_key))
            if inst is None:
                inst = mk(*args, **kwargs)
                GLOBAL_STATES[shared_key] = inst
            return cast(S, inst)

        ctx = PulseContext.get()
        if ctx is None or ctx.render is None:
            raise RuntimeError(
                "ps.global_state must be called inside a Pulse render/callback context"
            )
        return cast(
            S, ctx.render.get_global_state(base_key, lambda: mk(*args, **kwargs))
        )

    return accessor


__all__ = [
    "RedirectInterrupt",
    "NotFoundInterrupt",
    "route",
    "session",
    "session_id",
    "websocket_id",
    "call_api",
    "set_cookie",
    "navigate",
    "redirect",
    "not_found",
    "server_address",
    "client_address",
    "global_state",
    "GLOBAL_STATES",
    "GlobalStateAccessor",
]
