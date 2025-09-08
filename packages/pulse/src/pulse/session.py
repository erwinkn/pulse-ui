from __future__ import annotations

import uuid
from typing import Protocol, Optional, Literal, Any

from pulse.reactive_extensions import ReactiveDict
from dataclasses import dataclass


class SessionStore(Protocol):
    def get(self, sid: str) -> Optional[ReactiveDict]: ...
    def create(self, sid: str) -> ReactiveDict: ...
    def delete(self, sid: str) -> None: ...
    def touch(self, sid: str) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ReactiveDict] = {}

    def get(self, sid: str) -> Optional[ReactiveDict]:
        return self._sessions.get(sid)

    def create(self, sid: str) -> ReactiveDict:
        session: ReactiveDict[str, Any] = ReactiveDict()
        self._sessions[sid] = session
        return session

    def delete(self, sid: str) -> None:
        self._sessions.pop(sid, None)

    def touch(self, sid: str) -> None:
        # No-op for in-memory store
        pass


@dataclass
class SessionCookie:
    domain: Optional[str] = None
    name: str = "pulse.sid"
    secure: bool = True
    samesite: Literal["lax", "strict", "none"] = "lax"
    max_age_seconds: int = 7 * 24 * 3600

    def get_sid_from_fastapi(self, request: Any) -> Optional[str]:
        """Extract sid from a FastAPI Request (by reading Cookie header)."""
        header = (
            getattr(request, "headers", {}).get("cookie")
            if hasattr(request, "headers")
            else None
        )
        cookies = parse_cookie_header(header)
        return cookies.get(self.name)

    def get_sid_from_socketio(self, environ: dict) -> Optional[str]:
        """Extract sid from a socket.io environ mapping."""
        raw = environ.get("HTTP_COOKIE") or environ.get("COOKIE")
        cookies = parse_cookie_header(raw)
        return cookies.get(self.name)

    def set_on_fastapi_response(self, response: Any, sid: str) -> None:
        """Set the session cookie on a FastAPI Response-like object."""
        if not hasattr(response, "set_cookie"):
            return
        response.set_cookie(
            key=self.name,
            value=sid,
            httponly=True,
            samesite=self.samesite,
            secure=self.secure,
            max_age=self.max_age_seconds,
            domain=self.domain,
            path="/",
        )


def new_sid() -> str:
    return uuid.uuid4().hex


def parse_cookie_header(header: str | None) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if not header:
        return cookies
    parts = [p.strip() for p in header.split(";") if p.strip()]
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies
