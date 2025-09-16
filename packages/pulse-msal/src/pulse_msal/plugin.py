"""
Example: Microsoft Entra ID (Azure AD) auth using MSAL with token caching.

Dev assumptions:
- Node and Python run on same host in dev (localhost) so cookies work for both
- In prod, serve under the same origin or set Domain=.example.com on cookies

Highlights:
- Middleware sets `ctx["auth"]` from MSAL ID token claims
- Protects `/secret` at prerender and on websocket `navigate`
- Auth endpoints implement Authorization Code Flow
- Token cache stored server-side and referenced by an HttpOnly cookie
"""

import json
import os
from typing import Any, Optional, Callable, Protocol, cast
from pathlib import Path
import secrets

import msal
from urllib.parse import quote
import pulse as ps
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pulse.helpers import get_client_address


SESSION_KEY = os.getenv("MSAL_SESSION_KEY", "msal")


def _default_authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}"


ClaimsMapper = Callable[[dict[str, Any]], dict[str, Any]]


class TokenCacheStore(Protocol):
    def load(
        self, request: Request, ctx: dict[str, Any]
    ) -> msal.SerializableTokenCache: ...

    def save(
        self, request: Request, cache: msal.SerializableTokenCache, ctx: dict[str, Any]
    ) -> None: ...


def _default_claims_mapper(claims: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, JSON-serializable user dict from MSAL id_token claims."""
    # Remove keys with None values to keep payload compact
    return {k: v for k, v in claims.items() if v is not None}


def _json_clean(value: Any) -> Any:
    """Convert value to JSON-serializable primitives for cookie-backed sessions."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_clean(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_clean(v) for k, v in value.items()}
    # Fallback: string representation
    return str(value)


def auth(session_key=SESSION_KEY) -> dict[str, Any] | None:
    return cast(dict[str, Any] | None, ps.session().get(session_key, {}).get("auth"))


def login(next: str | None = None):
    url = "/auth/login"
    if next:
        url += f"?next={quote(next)}"
    ps.navigate(url)


def logout():
    del ps.session()[SESSION_KEY]


class MSALPlugin(ps.Plugin):
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        authority: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        session_key: Optional[str] = None,
        claims_mapper: Optional[ClaimsMapper] = None,
        token_cache_store: Optional[TokenCacheStore] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.authority = authority or _default_authority(tenant_id)
        self.scopes: list[str] = scopes or ["User.Read"]
        self.session_key = session_key or SESSION_KEY
        self.claims_mapper = claims_mapper or _default_claims_mapper
        self.token_cache_store = token_cache_store

    def cca(self, cache: msal.TokenCache):
        return msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=cache,
        )

    def on_setup(self, app: "ps.App") -> None:
        # Default selection:
        # - If using CookieSessionStore (cookie-backed), we cannot store MSAL cache in the cookie.
        #   In dev: default to file store under <web_root>/.pulse/msal_cache.
        #   In prod: require an explicit token_cache_store.
        # - If using a server-side SessionStore, leave token_cache_store=None so we persist
        #   the cache into the session by default.
        if self.token_cache_store is None:
            if isinstance(app.session_store, ps.CookieSessionStore):
                if app.mode == "prod":
                    raise RuntimeError(
                        "MSALPlugin requires a token_cache_store in production when using CookieSessionStore."
                    )
                base_dir = Path(app.codegen.cfg.web_root) / ".pulse" / "msal_cache"
                self.token_cache_store = FileTokenCacheStore(base_dir)

        @app.fastapi.get("/auth/login")
        def auth_login(request: Request):
            sess = ps.session()
            ctx = sess.setdefault(self.session_key, {})
            if self.token_cache_store:
                cache = self.token_cache_store.load(request, ctx)
            else:
                cache = msal.SerializableTokenCache()
                if serialized := ctx.get("token_cache"):
                    try:
                        cache.deserialize(serialized)
                    except Exception:
                        pass

            cca = self.cca(cache)
            redirect_uri = f"{app.server_address}/auth/callback"

            flow = cca.initiate_auth_code_flow(
                scopes=self.scopes,
                redirect_uri=redirect_uri,
                prompt="select_account",
            )
            next_path = request.query_params.get("next") or "/secret"
            ctx["flow"] = flow
            ctx["next"] = next_path
            ctx["client_address"] = get_client_address(request)
            return RedirectResponse(url=flow["auth_uri"])  # type: ignore[index]

        @app.fastapi.get("/auth/callback")
        def auth_callback(request: Request):
            sess = ps.session()
            ctx: dict = sess.setdefault(self.session_key, {})
            if self.token_cache_store:
                cache = self.token_cache_store.load(request, ctx)
            else:
                cache = msal.SerializableTokenCache()
                if serialized := ctx.get("token_cache"):
                    try:
                        cache.deserialize(serialized)
                    except Exception:
                        pass

            cca = self.cca(cache)
            try:
                result = cca.acquire_token_by_auth_code_flow(
                    ctx.get("flow", {}), dict(request.query_params)
                )
            except (KeyError, ValueError):
                # Likely CSRF, missing or reused flow
                raise HTTPException(status_code=400, detail="Invalid auth flow")

            if "error" in result:
                body = f"<h1>Auth error</h1><pre>{json.dumps(result, indent=2)}</pre>"
                return HTMLResponse(content=body, status_code=400)

            # Save user claims (mapped) and token cache back into session
            claims = result.get("id_token_claims") or {}
            user = self.claims_mapper(claims) if claims else {}
            user = _json_clean(user)

            ctx.pop("flow", None)
            origin = ctx.pop("client_address", None)
            next_path = ctx.pop("next", "/")
            ctx["auth"] = user
            if getattr(cache, "has_state_changed", False):
                if self.token_cache_store:
                    self.token_cache_store.save(request, cache, ctx)
                else:
                    # default to storing in the session (server-side SessionStore)
                    try:
                        # SerializableTokenCache
                        ctx["token_cache"] = cache.serialize()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            return RedirectResponse(url=f"{origin}{next_path}")


class FileTokenCacheStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _path_for_ctx(self, ctx: dict[str, Any]) -> Path:
        cache_id = ctx.get("token_cache_id")
        if not isinstance(cache_id, str) or not cache_id:
            cache_id = secrets.token_urlsafe(16)
            ctx["token_cache_id"] = cache_id
        # Avoid extremely long names; simple .json payload
        return self.base_dir / f"{cache_id}.json"

    def load(
        self, request: Request, ctx: dict[str, Any]
    ) -> msal.SerializableTokenCache:
        path = self._path_for_ctx(ctx)
        cache = msal.SerializableTokenCache()
        try:
            if path.exists():
                data = path.read_text()
                if data:
                    cache.deserialize(data)
        except Exception:
            # Ignore corrupted caches; start fresh
            pass
        return cache

    def save(
        self, request: Request, cache: msal.SerializableTokenCache, ctx: dict[str, Any]
    ) -> None:
        # Only write if state changed to limit IO
        if not cache.has_state_changed:
            return
        path = self._path_for_ctx(ctx)
        try:
            serialized = cache.serialize()
        except Exception:
            return
        try:
            path.write_text(serialized)
        except Exception:
            # Best effort
            pass


class RedisTokenCacheStore:
    def __init__(
        self,
        *,
        url: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 6379,
        db: int = 0,
        prefix: str = "msal:cache:",
        ttl_seconds: Optional[int] = None,
    ) -> None:
        try:
            import redis  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "RedisTokenCacheStore requires the 'redis' package. Install it to use this store."
            ) from exc
        if url:
            self.client = redis.Redis.from_url(url)
        else:
            self.client = redis.Redis(host=host or "127.0.0.1", port=port, db=db)
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds

    def _key_for_ctx(self, ctx: dict[str, Any]) -> str:
        cache_id = ctx.get("token_cache_id")
        if not isinstance(cache_id, str) or not cache_id:
            cache_id = secrets.token_urlsafe(16)
            ctx["token_cache_id"] = cache_id
        return f"{self.prefix}{cache_id}"

    def load(
        self, request: Request, ctx: dict[str, Any]
    ) -> msal.SerializableTokenCache:
        key = self._key_for_ctx(ctx)
        cache = msal.SerializableTokenCache()
        try:
            data = self.client.get(key)
            if data:
                cache.deserialize(data.decode("utf-8"))
        except Exception:
            pass
        return cache

    def save(
        self, request: Request, cache: msal.SerializableTokenCache, ctx: dict[str, Any]
    ) -> None:
        if not cache.has_state_changed:
            return
        key = self._key_for_ctx(ctx)
        try:
            serialized = cache.serialize()
        except Exception:
            return
        try:
            if self.ttl_seconds and self.ttl_seconds > 0:
                self.client.setex(key, self.ttl_seconds, serialized)
            else:
                self.client.set(key, serialized)
        except Exception:
            pass
