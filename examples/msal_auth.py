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

import msal
import pulse as ps
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pulse.helpers import get_client_address


def require_env(key: str):
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"Missing environment variable {key}")
    return value


AZURE_CLIENT_ID = require_env("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = require_env("AZURE_CLIENT_SECRET")
AZURE_TENANT_ID = require_env("AZURE_TENANT_ID")
SESSION_KEY = os.getenv("MSAL_SESSION_KEY", "msal")


def _default_authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}"


ClaimsMapper = Callable[[dict[str, Any]], dict[str, Any]]


class TokenCacheStore(Protocol):
    def load(self, request: Request, ctx: dict[str, Any]) -> msal.TokenCache: ...

    def save(
        self, request: Request, cache: msal.TokenCache, ctx: dict[str, Any]
    ) -> None: ...


def _default_claims_mapper(claims: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, JSON-serializable user dict from MSAL id_token claims."""
    user = {
        "name": claims.get("name") or claims.get("given_name"),
        "email": claims.get("preferred_username"),
    }
    # Remove keys with None values to keep payload compact
    return {k: v for k, v in user.items() if v is not None}


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


def login():
    ps.navigate("/auth/login")


def logout():
    del ps.session()[SESSION_KEY]


class MsalPlugin(ps.Plugin):
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
            try:
                result = cca.acquire_token_by_auth_code_flow(
                    ctx.get("flow", {}), dict(request.query_params)
                )
            except ValueError:
                # Likely CSRF or reused flow
                raise HTTPException(status_code=400, detail="Invalid auth flow")

            if "error" in result:
                body = f"<h1>Auth error</h1><pre>{json.dumps(result, indent=2)}</pre>"
                return HTMLResponse(content=body, status_code=400)

            # Save user claims (mapped) and token cache back into session
            claims = result.get("id_token_claims") or {}
            print("Claims:", json.dumps(claims, indent=2))
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
                    # default to storing in session cookie
                    try:
                        # SerializableTokenCache
                        ctx["token_cache"] = cache.serialize()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            return RedirectResponse(url=f"{origin}{next_path}")


@ps.component
def LoginPage():
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
def SecretPage():
    print("Rerendering secret")
    sess = ps.session()
    auth = sess.get(SESSION_KEY)
    if not auth:
        ps.redirect("/login")

    user = auth["auth"]
    name = user.get("name") or user.get("email")

    def update_session_entry(text: str):
        sess["pulse"] = text

    def logout():
        del sess[SESSION_KEY]

    return ps.div(
        ps.h2("Secret", className="text-2xl font-bold mb-4"),
        ps.p(f"Welcome {name}"),
        ps.button(
            "Sign out",
            onClick=logout,
            className="btn-secondary mt-4",
        ),
        ps.label("Modify session", htmlFor="session-input"),
        ps.input(
            id="session-input",
            value=sess.get("pulse", ""),
            onChange=lambda evt: update_session_entry(evt["target"]["value"]),
        ),
        className="max-w-md mx-auto p-6",
    )


@ps.component
def Home():
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
def Shell():
    return ps.div(
        ps.Outlet(),
        className="p-6",
    )


app = ps.App(
    routes=[
        ps.Layout(
            Shell,
            children=[
                ps.Route("/", Home),
                ps.Route("/login", LoginPage),
                ps.Route("/secret", SecretPage),
            ],
        )
    ],
    # Instantiate plugin with required credentials; authority and token store
    # are optional
    plugins=[
        MsalPlugin(
            client_id=AZURE_CLIENT_ID,
            client_secret=AZURE_CLIENT_SECRET,
            tenant_id=AZURE_TENANT_ID,
        )
    ],
)
