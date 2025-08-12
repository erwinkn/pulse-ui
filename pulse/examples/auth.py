"""
Example: Cookie-based auth with middleware and FastAPI endpoints.

Dev assumptions:
- Node and Python run on the same host (e.g., localhost) even if ports differ.
- Cookies are keyed by host, not port, so the cookie will be sent to both.
- In production, put both behind the same origin or use Domain=.example.com.

This example shows:
- A middleware that protects "/secret" and populates session context
- A /login page (any email/password) posting to Python endpoints to set a cookie
- A sign-out button that clears the cookie
"""

from __future__ import annotations

import pulse as ps
from fastapi import Response, Request
from fastapi.responses import JSONResponse
from pulse.middleware import Redirect, Deny
from pulse.api import call_api, navigate


AUTH_COOKIE = "pulse_auth"


class AuthMiddleware(ps.PulseMiddleware):
    def _extract_user(self, *, headers: dict, cookies: dict) -> str | None:
        # Trivial cookie read; use a signed/secure cookie or session storage for real apps
        return cookies.get(AUTH_COOKIE)

    def prerender(self, *, path, route_info, request, context, next):
        user = self._extract_user(headers=request.headers, cookies=request.cookies)
        # Seed session context during prerender to avoid first-paint flashes
        if user:
            context["user_email"] = user

        # Protect /secret at prerender time
        if path.startswith("/secret") and not user:
            return Redirect("/login")

        return next()

    def connect(self, *, request, ctx, next):
        user = self._extract_user(headers=request.headers, cookies=request.cookies)
        if user:
            ctx["user_email"] = user
            return next()
        # Connection can still be allowed if your app shows public pages; here we allow
        return next()

    def message(self, *, ctx, data, next):
        t = data.get("type")  # type: ignore[assignment]
        if t in {"mount", "navigate"}:
            path = data.get("path")  # type: ignore[assignment]
            if (
                not ctx.get("user_email")
                and isinstance(path, str)
                and path.startswith("/secret")
            ):
                return Deny()
        return next()


# ---------------------- UI ----------------------


@ps.component
def login():
    email_state = ps.states(ps.State)

    async def submit():
        body = {"email": getattr(email_state, "email", "guest")}
        res = await call_api("/api/login", method="POST", body=body)
        if res.get("ok"):
            navigate("/secret")

    return ps.div(
        ps.h2("Login", className="text-2xl font-bold mb-4"),
        ps.div(
            ps.label("Email", htmlFor="email", className="block mb-1"),
            ps.input(
                id="email",
                name="email",
                type="email",
                required=True,
                className="input mb-3",
                onChange=lambda e: setattr(email_state, "email", e["target"]["value"]),
            ),
        ),
        ps.div(
            ps.label("Password", htmlFor="password", className="block mb-1"),
            ps.input(
                id="password",
                name="password",
                type="password",
                required=True,
                className="input mb-3",
            ),
        ),
        ps.button("Sign in", onClick=submit, className="btn-primary"),
        className="max-w-md mx-auto p-6",
    )


@ps.component
def secret():
    sess = ps.session_context()

    async def sign_out():
        res = await call_api("/api/logout", method="POST")
        if res.get("ok"):
            navigate("/")

    return ps.div(
        ps.h2("Secret", className="text-2xl font-bold mb-4"),
        ps.p(f"Welcome {sess.get('user_email', '<unknown>')}"),
        ps.button("Sign out", onClick=sign_out, className="btn-secondary"),
        className="max-w-md mx-auto p-6",
    )


@ps.component
def home():
    return ps.div(
        ps.h2("Auth Demo", className="text-2xl font-bold mb-4"),
        ps.div(
            ps.Link("Login", to="/login", className="link mr-4"),
            ps.Link("Secret", to="/secret", className="link"),
            className="mb-4",
        ),
        ps.p("This page is public."),
    )


@ps.component
def shell():
    # Minimal layout that renders children
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
    middleware=AuthMiddleware(),
)


# ---------------------- API endpoints ----------------------


@app.fastapi.post("/api/login")
async def api_login(request: Request, response: Response):
    form = await request.form()
    raw_email = form.get("email")
    # Starlette form fields may be str or UploadFile
    if hasattr(raw_email, "file") or hasattr(raw_email, "read"):
        # Uploaded file case; not expected here, fallback
        email = ""
    else:
        email = raw_email or ""
        if isinstance(email, str):
            email = email.strip()
        else:
            email = ""
    # Accept any email/password for demo; set HttpOnly cookie
    # Simple JSON response; Pulse controls navigation/UI.
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        key=AUTH_COOKIE,
        value=email or "guest",
        httponly=True,
        samesite="lax",
        secure=False,  # set True behind https
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return resp


@app.fastapi.post("/api/logout")
async def api_logout(request: Request, response: Response):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key=AUTH_COOKIE, path="/")
    return resp
