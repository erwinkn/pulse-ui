from dataclasses import KW_ONLY, dataclass
from typing import Literal, Optional
from fastapi import Request, Response
from pulse.hooks import set_cookie


@dataclass
class Cookie:
    name: str
    _: KW_ONLY
    domain: Optional[str] = None
    secure: bool = True
    samesite: Literal["lax", "strict", "none"] = "lax"
    max_age_seconds: int = 7 * 24 * 3600

    def get_from_fastapi(self, request: Request) -> Optional[str]:
        """Extract sid from a FastAPI Request (by reading Cookie header)."""
        header = request.headers.get("cookie")
        cookies = parse_cookie_header(header)
        return cookies.get(self.name)

    def get_from_socketio(self, environ: dict) -> Optional[str]:
        """Extract sid from a socket.io environ mapping."""
        raw = environ.get("HTTP_COOKIE") or environ.get("COOKIE")
        cookies = parse_cookie_header(raw)
        return cookies.get(self.name)

    async def set_through_api(self, value: str):
        await set_cookie(
            name=self.name,
            value=value,
            domain=self.domain,
            secure=self.secure,
            samesite=self.samesite,
            max_age_seconds=self.max_age_seconds,
        )

    def set_on_fastapi(self, response: Response, value: str) -> None:
        """Set the session cookie on a FastAPI Response-like object."""
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

@dataclass
class SetCookie(Cookie):
    value: str

    @classmethod
    def from_cookie(cls, cookie: Cookie, value: str) -> "SetCookie":
        return cls(
            name=cookie.name,
            value=value,
            domain=cookie.domain,
            secure=cookie.secure,
            samesite=cookie.samesite,
            max_age_seconds=cookie.max_age_seconds,
        )

def session_cookie(
    name: str = "pulse.sid",
    domain: Optional[str] = None,
    secure: bool = True,
    samesite: Literal["lax", "strict", "none"] = "lax",
    max_age_seconds: int = 7 * 24 * 3600,
):
    return Cookie(
        name,
        domain=domain,
        secure=secure,
        samesite=samesite,
        max_age_seconds=max_age_seconds,
    )


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
