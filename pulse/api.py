from __future__ import annotations

from typing import Any, Mapping

from pulse.session import CURRENT_SESSION, CURRENT_ROUTE


async def call_api(
    url: str,
    *,
    method: str = "POST",
    headers: Mapping[str, str] | None = None,
    body: Any | None = None,
    credentials: str = "include",
) -> dict[str, Any]:
    """Ask the client to perform an HTTP request and await the result.

    This hides session plumbing; safe to call inside Pulse callbacks.
    """
    session = CURRENT_SESSION.get()
    route = CURRENT_ROUTE.get()
    if session is None or route is None:
        raise RuntimeError("call_api() must be invoked inside a Pulse callback context")
    return await session.call_api(
        route,
        url,
        method=method,
        headers=dict(headers or {}),
        body=body,
        credentials=credentials,
    )


def navigate(path: str) -> None:
    """Instruct the client to navigate to a new path for the current route tree.

    Non-async; sends a server message to the client to perform SPA navigation.
    """
    session = CURRENT_SESSION.get()
    if session is None:
        raise RuntimeError("navigate() must be invoked inside a Pulse callback context")
    # Emit navigate_to once; client will handle redirect at app-level
    session.notify({"type": "navigate_to", "path": path})


def update_session_context(updates: Mapping[str, Any]) -> None:
    """Update the current session's context dict.

    Convenience helper to avoid exposing the Session object in user code.
    """
    session = CURRENT_SESSION.get()
    if session is None:
        raise RuntimeError(
            "update_session_context() must be invoked inside a Pulse callback context"
        )
    session.context.update(dict(updates))
