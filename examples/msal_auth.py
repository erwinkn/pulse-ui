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

import json
import os
from typing import Any, Optional

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
MSAL_SESSION_KEY = os.getenv("MSAL_SESSION_KEY", "msal")


def _default_authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}"


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


class MsalAuthMiddleware(ps.PulseMiddleware):
    def __init__(
        self,
        *,
        session_key: str = "msal",
        protected_prefixes: Optional[list[str]] = None,
    ):
        self.session_key = session_key
        self.protected_prefixes = protected_prefixes or ["/secret"]

    def _get_user(self, session) -> dict | None:
        return session.get(self.session_key, {}).get("user")

    def prerender(self, *, path, request, route_info, session, next):
        user = self._get_user(session)
        # Protect configured prefixes at prerender time
        if any(path.startswith(p) for p in self.protected_prefixes) and not user:
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
                not self._get_user(session)
                and isinstance(path, str)
                and any(path.startswith(p) for p in self.protected_prefixes)
            ):
                return ps.Deny()
        return next()


class MsalPlugin(ps.Plugin):
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        authority: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        session_key: str = "msal",
        protected_prefixes: Optional[list[str]] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.authority = authority or _default_authority(tenant_id)
        self.scopes: list[str] = scopes or ["User.Read"]
        self.session_key = session_key
        self.middleware_instance = MsalAuthMiddleware(
            session_key=session_key,
            protected_prefixes=protected_prefixes,
        )

    def cca(self, cache: msal.SerializableTokenCache):
        return msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=cache,
        )

    def middleware(self) -> list[ps.PulseMiddleware]:
        return [self.middleware_instance]

    def on_setup(self, app: "ps.App") -> None:
        session_key = self.session_key

        @app.fastapi.get("/auth/login")
        def auth_login(request: Request):
            sess = ps.session()
            ctx = sess.setdefault(session_key, {})
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
            ctx = sess.setdefault(session_key, {})
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

            # Save user claims and token cache back into session
            user = _extract_user_from_result(result) or {}

            ctx.pop("flow", None)
            origin = ctx.pop("client_address", None)
            next_path = ctx.pop("next", "/")
            ctx["user"] = user
            if cache.has_state_changed:
                ctx["token_cache"] = cache.serialize()
            return RedirectResponse(url=f"{origin}{next_path}")

        @app.fastapi.get("/auth/logout")
        def local_logout(request: Request):
            session = ps.session()
            print("Clearing context")
            del session[session_key]
            # Redirect back to the SPA origin or to provided next path
            origin = get_client_address(request) or ""
            next_path = request.query_params.get("next") or "/"
            if not isinstance(next_path, str) or not next_path.startswith("/"):
                next_path = "/"
            return RedirectResponse(url=f"{origin}{next_path}")


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
    print("Rerendering secret")
    sess = ps.session()
    user = (sess.get("msal") or {}).get("user", {})
    name = user.get("name") or user.get("email") or "<unknown>"
    print("Session keys:", sess.keys())

    def update_session_entry(text: str):
        sess["pulse"] = text

    return ps.div(
        ps.h2("Secret", className="text-2xl font-bold mb-4"),
        ps.p(f"Welcome {name}"),
        ps.a(
            "Sign out",
            href=f"{ps.server_address()}/auth/logout",
            className="btn-secondary mt-4",
        ),
        # ps.label("Modify session", htmlFor="session-input"),
        # ps.input(
        #     id="session-input",
        #     value=sess.get("pulse", ""),
        #     onChange=lambda evt: update_session_entry(evt["target"]["value"]),
        # ),
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
