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

import os
from pulse_msal import MSALPlugin
import pulse as ps
from pulse_msal.plugin import auth, logout


def require_env(key: str):
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"Missing environment variable {key}")
    return value


AZURE_CLIENT_ID = require_env("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = require_env("AZURE_CLIENT_SECRET")
AZURE_TENANT_ID = require_env("AZURE_TENANT_ID")


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
    user = auth()
    if not user:
        ps.redirect("/login")

    name = user.get("name") or user.get("email")

    def update_session_entry(text: str):
        print(f"Updating session entry to {text}")
        print("session entry = ", sess["pulse"])
        sess["pulse"] = text

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
        MSALPlugin(
            client_id=AZURE_CLIENT_ID,
            client_secret=AZURE_CLIENT_SECRET,
            tenant_id=AZURE_TENANT_ID,
        )
    ],
)
