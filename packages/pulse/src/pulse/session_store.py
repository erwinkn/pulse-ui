from __future__ import annotations

import uuid
from typing import Protocol, Optional

from pulse.reactive_extensions import ReactiveDict


class SessionStore(Protocol):
    def get(self, sid: str) -> Optional[ReactiveDict]: ...
    def create(self, sid: str) -> ReactiveDict: ...
    def delete(self, sid: str) -> None: ...
    def touch(self, sid: str) -> None: ...


class InMemorySessionStore:
    def __init__(self):
        self._sessions: dict[str, ReactiveDict] = {}

    def get(self, sid: str) -> Optional[ReactiveDict]:
        return self._sessions.get(sid)

    def create(self, sid: str) -> ReactiveDict:
        print(f"Creating session {sid}")
        ctx = ReactiveDict()
        self._sessions[sid] = ctx
        return ctx

    def delete(self, sid: str) -> None:
        self._sessions.pop(sid, None)

    def touch(self, sid: str) -> None:
        # No-op for in-memory store
        pass


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
