from __future__ import annotations

import uuid
from typing import NamedTuple, Protocol, Optional, Literal, Any
from abc import ABC, abstractmethod
import json
import hmac
import hashlib
import base64
from fastapi import Request, Response

from pulse.context import PULSE_CONTEXT
from pulse.cookies import Cookie, SetCookie, session_cookie
from pulse.reactive import Effect
from pulse.reactive_extensions import ReactiveDict
from pulse.hooks import call_api, set_cookie
from dataclasses import dataclass

Session = ReactiveDict[str, Any]


class UserSession:
    sid: str
    store: SessionStore | CookieSessionStore
    ctx: Session

    def __init__(
        self,
        sid: str,
        cookie: Optional[Cookie] = None,
        store: Optional[SessionStore] = None,
    ) -> None:
        self.sid = sid
        self.ctx: Session = ReactiveDict()
        self._processing_request = False
        self.store = store or CookieSessionStore()
        self.cookie = cookie or session_cookie()
        self._queued_cookies: dict[str, SetCookie] = {}

        def effect():
            # Read all context values
            _ = dict(self.ctx)
            if isinstance(self.store, SessionStore):
                self.store.save(sid, self.ctx)
            else:
                # TODO: encode the session into a cookiecall self.set_cookie
                encoded_ctx = self.store.cookie_value(self.sid, self.ctx)
                self.set_cookie(
                    name=self.cookie.name,
                    value=encoded_ctx,
                    domain=self.cookie.domain,
                    secure=self.cookie.secure,
                    samesite=self.cookie.samesite,
                    max_age_seconds=self.cookie.max_age_seconds,
                )

        self._effect = Effect
    
    def dispose(self):
        self._effect.dispose()

    def start_request(self):
        self.processing_request = True

    def end_request(self, req: Request):
        for cookie in self._queued_cookies.values():
            cookie.set_on_fastapi(req, cookie.value)
        self._queued_cookies.clear()
        self.processing_request = False

    def set_cookie(
        self,
        name: str,
        value: str,
        domain: Optional[str] = None,
        secure: bool = True,
        samesite: Literal["lax", "strict", "none"] = "lax",
        max_age_seconds: int = 7 * 24 * 3600,
    ):
        cookie = SetCookie(
            name=name,
            value=value,
            domain=domain,
            secure=secure,
            samesite=samesite,
            max_age_seconds=max_age_seconds,
        )
        self._queued_cookies[name] = cookie
        # Schedule a cookie refresh for this user
        if not self._processing_request:
            await call_api("/set-cookie")
            ctx = PULSE_CONTEXT.get()


class SessionStore(ABC):
    """Abstract base for server-backed session stores (DB, cache, memory).

    Implementations persist session state on the server and place only a stable
    identifier in the cookie. Override methods to integrate with your backend.
    """

    @abstractmethod
    def get(self, sid: str) -> Optional[Session]: ...

    @abstractmethod
    def create(self, sid: str) -> Session: ...

    @abstractmethod
    def delete(self, sid: str) -> None: ...

    @abstractmethod
    async def save(self, sid: str, session: Session) -> None: ...


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get(self, sid: str) -> Optional[Session]:
        return self._sessions.get(sid)

    def create(self, sid: str) -> Session:
        session: Session = ReactiveDict()
        self._sessions[sid] = session
        return session

    def save(self, sid: str, session: Session):
        # Should not matter as the session ReactiveDict is normally mutated directly
        self._sessions[sid] = session

    def delete(self, sid: str) -> None:
        self._sessions.pop(sid, None)


class CookieSessionStore:
    """Persist session in a signed cookie (Flask-like default).

    The cookie stores a compact JSON of the session and is signed using
    HMAC-SHA256 to prevent tampering. Keep the session small (<4KB).
    """

    def __init__(
        self,
        secret: str,
        *,
        salt: str = "pulse.session",
        digestmod: str = "sha256",
        max_cookie_bytes: int = 3800,
    ) -> None:
        if not secret:
            raise ValueError("CookieSessionStore requires a non-empty secret")
        self._secret = secret.encode("utf-8")
        self._salt = salt.encode("utf-8")
        self._digest = getattr(hashlib, digestmod)
        self._max_cookie_bytes = max_cookie_bytes

    # In cookie-backed mode, the incoming "sid" is actually the cookie payload
    def get(self, sid: str) -> Optional[ReactiveDict]:
        try:
            if not sid:
                return None
            payload = self._unsign(sid)
            if payload is None:
                return None
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None
            # Create a ReactiveDict seeded with data
            session: ReactiveDict[str, Any] = ReactiveDict()
            session.update(data)
            return session
        except Exception:
            # On any failure, act like no session
            return None

    def create(self, sid: str) -> ReactiveDict:
        # Start with an empty session
        session: ReactiveDict[str, Any] = ReactiveDict()
        self._sessions[sid] = session
        return session

    def delete(self, sid: str) -> None:
        # Cookie will be cleared by setting an expired cookie at the framework level
        return None

    def cookie_value(self, sid: str, session: ReactiveDict) -> str:
        # Encode the entire session into the cookie
        try:
            # Convert to a plain dict for JSON serialization
            data = dict(session)
            payload = json.dumps(data, separators=(",", ":"))
        except Exception:
            # Best effort: fallback to an empty session if it's not serializable
            data = {}
        signed = self._sign(payload)
        if len(signed) > self._max_cookie_bytes:
            # If too large, fall back to an empty session to avoid breaking cookies
            signed = self._sign("{}")
        return signed

    async def save(self, sid: str, session: ReactiveDict) -> None:
        # For cookie sessions, use the Pulse hook to refresh cookie in a render context
        # Refresh the Pulse session cookie; name/value are resolved server-side
        await set_cookie(name=self.__class__.__name__, value=sid)

    # --- signing helpers ---
    def _mac(self, payload: bytes) -> bytes:
        return hmac.new(
            self._secret + b"|" + self._salt, payload, self._digest
        ).digest()

    def _sign(self, payload: str) -> str:
        raw = payload.encode("utf-8")
        mac = self._mac(raw)
        b64 = base64.urlsafe_b64encode(raw).rstrip(b"=")
        sig = base64.urlsafe_b64encode(mac).rstrip(b"=")
        return f"v1.{b64.decode('ascii')}.{sig.decode('ascii')}"

    def _unsign(self, token: str) -> Optional[str]:
        try:
            if not token.startswith("v1."):
                return None
            _, b64, sig = token.split(".", 2)

            # Pad base64
            def _pad(s: str) -> bytes:
                return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

            raw = _pad(b64)
            mac = _pad(sig)
            expected = self._mac(raw)
            if not hmac.compare_digest(mac, expected):
                return None
            return raw.decode("utf-8")
        except Exception:
            return None


@dataclass
class SessionCookie:
    domain: Optional[str] = None
    name: str = "pulse.sid"
    secure: bool = True
    samesite: Literal["lax", "strict", "none"] = "lax"
    max_age_seconds: int = 7 * 24 * 3600

    def get_from_fastapi(self, request: Any) -> Optional[str]:
        """Extract sid from a FastAPI Request (by reading Cookie header)."""
        header = (
            getattr(request, "headers", {}).get("cookie")
            if hasattr(request, "headers")
            else None
        )
        cookies = parse_cookie_header(header)
        return cookies.get(self.name)

    def get_from_socketio(self, environ: dict) -> Optional[str]:
        """Extract sid from a socket.io environ mapping."""
        raw = environ.get("HTTP_COOKIE") or environ.get("COOKIE")
        cookies = parse_cookie_header(raw)
        return cookies.get(self.name)

    def set_on_fastapi(self, response: Any, value: str) -> None:
        """Set the session cookie on a FastAPI Response-like object."""
        if not hasattr(response, "set_cookie"):
            return
        response.set_cookie(
            key=self.name,
            value=value,
            httponly=True,
            samesite=self.samesite,
            secure=self.secure,
            max_age=self.max_age_seconds,
            domain=self.domain,
            path="/",
        )


def new_sid() -> str:
    return uuid.uuid4().hex
