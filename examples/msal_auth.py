"""
Example: Microsoft Entra ID (Azure AD) auth using MSAL with token caching.

Dev assumptions:
- Node and Python run on same host in dev (localhost) so cookies work for both
- In prod, serve under the same origin or set Domain=.example.com on cookies

Highlights:
- Middleware sets `ctx["user"]` from MSAL ID token claims
- Protects `/secret` at prerender and on websocket `navigate`
- Auth endpoints implement Authorization Code Flow
- Token cache stored server-side and referenced by an HttpOnly cookie
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse, quote_plus
from pathlib import Path

import msal
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import pulse as ps
from pulse.helpers import get_client_address


# ---------------------- Env (configure here) ----------------------


AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")


# ---------------------- Constants ----------------------


MSAL_COOKIE = "msal_session"


# ---------------------- Token cache store ----------------------


class TokenCacheStore:
    """In-memory cache store keyed by a cookie value.

    Useful for local dev or tests. For production or multi-process, prefer
    a persistent store such as `FileTokenCacheStore` or Redis-backed store.
    """

    def __init__(self):
        self._store: dict[str, str] = {}

    def new_key(self) -> str:
        return uuid.uuid4().hex

    def load_cache(self, key: str) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        data = self._store.get(key)
        if data:
            try:
                cache.deserialize(data)
            except Exception:
                pass
        return cache

    def save_cache(self, key: str, cache: msal.SerializableTokenCache) -> None:
        print(f"Saving to cache, key = {key}")
        if cache.has_state_changed:
            self._store[key] = cache.serialize()

    def clear(self, key: str) -> None:
        self._store.pop(key, None)


class FileTokenCacheStore:
    """File-backed token cache store under a directory (default: .cache/msal).

    Each cookie key maps to a file containing the serialized MSAL cache.
    """

    def __init__(self, directory: str | Path | None = None):
        base = Path(directory) if directory is not None else Path(".cache") / "msal"
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # very simple filename sanitation: hex keys only in our generator
        return self._dir / f"{key}.json"

    def new_key(self) -> str:
        return uuid.uuid4().hex

    def load_cache(self, key: str) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        p = self._path(key)
        if p.exists():
            try:
                data = p.read_text(encoding="utf-8")
                if data:
                    cache.deserialize(data)
            except Exception:
                pass
        return cache

    def save_cache(self, key: str, cache: msal.SerializableTokenCache) -> None:
        if cache.has_state_changed:
            p = self._path(key)
            try:
                p.write_text(cache.serialize(), encoding="utf-8")
            except Exception:
                # swallow write errors to avoid breaking request flow
                pass

    def clear(self, key: str) -> None:
        p = self._path(key)
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


@runtime_checkable
class TokenCacheStoreProtocol(Protocol):
    def new_key(self) -> str: ...
    def load_cache(self, key: str) -> msal.SerializableTokenCache: ...
    def save_cache(self, key: str, cache: msal.SerializableTokenCache) -> None: ...
    def clear(self, key: str) -> None: ...


def _default_authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}"


def app_origin(req: Request) -> str:
    h = req.headers
    xf_proto = h.get("x-forwarded-proto")
    xf_host = h.get("x-forwarded-host")
    if xf_proto and xf_host:
        return f"{xf_proto}://{xf_host}".rstrip("/")
    origin = h.get("origin")
    if origin:
        return origin.rstrip("/")
    referer = h.get("referer")
    if referer:
        p = urlparse(referer)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}".rstrip("/")
    return str(req.base_url).rstrip("/")


def _extract_user_from_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    claims = result.get("id_token_claims") or {}
    if not claims:
        return None
    return {
        "name": claims.get("name") or claims.get("given_name"),
        "email": claims.get("preferred_username"),
        "oid": claims.get("oid"),
        "tid": claims.get("tid"),
    }


# ---------------------- Middleware ----------------------


class MsalAuthMiddleware(ps.PulseMiddleware):
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        authority: Optional[str] = None,
        scopes: Optional[list[str]] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.authority = authority or _default_authority(tenant_id)
        self._scopes_override = scopes
        self.scopes: list[str] = scopes or ["User.Read"]

    def cca(self, cache: msal.SerializableTokenCache):
        return msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=cache,
        )

    def prerender(self, *, path, request, route_info, session, next):
        user = session.get("user")
        # Protect /secret at prerender time
        if path.startswith("/secret") and not user:
            # Send to our login route
            return ps.Redirect("/login")
        return next()

    def connect(self, *, request, session, next):
        # No-op; session already contains user if authenticated
        return next()

    def message(self, *, data, session, next):
        t = data.get("type") if isinstance(data, dict) else None
        if t in {"mount", "navigate"}:
            path = data.get("path")
            if (
                not session.get("user")
                and isinstance(path, str)
                and path.startswith("/secret")
            ):
                return ps.Deny()
        return next()


# ---------------------- UI ----------------------


@ps.component
def login():
    # Just render a link that starts the server-side login redirect flow
    return ps.div(
        ps.h2("Sign in", className="text-2xl font-bold mb-4"),
        ps.p("You will be redirected to Microsoft to sign in."),
        ps.a(
            "Sign in with Microsoft",
            href=f"{ps.server_address()}/auth/login",
            className="btn-primary inline-block mt-4",
        ),
        className="max-w-md mx-auto p-6",
    )


@ps.component
def secret():
    sess = ps.session()
    user = sess.get("user", {})
    name = user.get("name") or user.get("email") or "<unknown>"
    print("Session keys:", sess.keys())
    return ps.div(
        ps.h2("Secret", className="text-2xl font-bold mb-4"),
        ps.p(f"Welcome {name}"),
        ps.a(
            "Sign out",
            href=f"{ps.server_address()}/auth/logout",
            className="btn-secondary mt-4",
        ),
        className="max-w-md mx-auto p-6",
    )


@ps.component
def home():
    return ps.div(
        ps.h2("MSAL Auth Demo", className="text-2xl font-bold mb-4"),
        ps.div(
            ps.Link("Login", to="/login", className="link mr-4"),
            ps.Link("Secret", to="/secret", className="link"),
            className="mb-4",
        ),
        ps.p("This page is public."),
    )


@ps.component
def shell():
    return ps.div(
        ps.Outlet(),
        className="p-6",
    )


# Instantiate middleware with required credentials; authority and token store are optional
msal_mw = MsalAuthMiddleware(
    client_id=AZURE_CLIENT_ID,
    client_secret=AZURE_CLIENT_SECRET,
    tenant_id=AZURE_TENANT_ID,
)

app = ps.App(
    routes=[
        ps.Layout(
            shell,
            children=[
                ps.Route("/", home),
                ps.Route("/login", login),
                ps.Route("/secret", secret),
            ],
        )
    ],
    middleware=[msal_mw],
)


# ---------------------- Auth endpoints ----------------------


@app.fastapi.get("/auth/login")
def auth_login(request: Request):
    sess = ps.session()
    cache = msal.SerializableTokenCache()
    if serialized := sess.get("token_cache"):
        try:
            cache.deserialize(serialized)
        except Exception:
            pass

    cca = msal_mw.cca(cache)
    origin = app.server_address or app_origin(request)
    redirect_uri = f"{origin}/auth/callback"

    flow = cca.initiate_auth_code_flow(
        scopes=msal_mw.scopes,
        redirect_uri=redirect_uri,
        prompt="select_account",
    )
    sess["msal_flow"] = flow
    next_path = request.query_params.get("next") or "/secret"
    sess["post_auth_next"] = next_path
    sess["client_address"] = get_client_address(request)
    return RedirectResponse(url=flow["auth_uri"])  # type: ignore[index]


@app.fastapi.get("/auth/callback")
def auth_callback(request: Request):
    sess = ps.session()
    cache = msal.SerializableTokenCache()
    if serialized := sess.get("token_cache"):
        try:
            cache.deserialize(serialized)
        except Exception:
            pass

    cca = msal_mw.cca(cache)
    try:
        result = cca.acquire_token_by_auth_code_flow(
            sess.get("msal_flow", {}), dict(request.query_params)
        )
    except ValueError:
        # Likely CSRF or reused flow
        raise HTTPException(status_code=400, detail="Invalid auth flow")

    if "error" in result:
        body = f"<h1>Auth error</h1><pre>{json.dumps(result, indent=2)}</pre>"
        return HTMLResponse(content=body, status_code=400)

    # Save user claims and token cache back into session
    user = _extract_user_from_result(result) or {}
    sess["user"] = user
    if cache.has_state_changed:
        sess["token_cache"] = cache.serialize()
    # Clear one-time flow state
    if "msal_flow" in sess:
        del sess["msal_flow"]

    origin = sess.pop("client_address")
    next_path = sess.pop("post_auth_next", "/")
    return RedirectResponse(url=f"{origin}{next_path}")


@app.fastapi.get("/auth/logout")
def auth_logout(request: Request):
    """Optional: also end Azure web session."""
    session = ps.session()
    for k in ["user", "token_cache", "msal_flow", "post_auth_next"]:
        if k in session:
            del session[k]
    post_logout = app.server_address or app_origin(request)
    url = (
        f"{msal_mw.authority}/oauth2/v2.0/logout?post_logout_redirect_uri="
        f"{quote_plus(post_logout)}"
    )
    return RedirectResponse(url=url)
