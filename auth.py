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
from urllib.parse import urlparse
import time

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
            print("[Prerender] Redirecting to login")
            return Redirect("/login")

        return next()

    def connect(self, *, request, ctx, next):
        user = self._extract_user(headers=request.headers, cookies=request.cookies)
        if user:
            ctx["user_email"] = user
            return next()
        # Allow connection for public pages in this demo
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


# Simple logging/timing middleware
class LoggingMiddleware(ps.PulseMiddleware):
    def prerender(self, *, path, route_info, request, context, next):
        start = time.perf_counter()
        res = next()
        duration_ms = (time.perf_counter() - start) * 1000
        print(f"[MW prerender] path={path} took={duration_ms:.1f}ms")
        return res

    def connect(self, *, request, ctx, next):
        ua = request.headers.get("user-agent")
        ip = request.client[0] if request.client else None
        print(f"[MW connect] ip={ip} ua={(ua or '')[:60]}")
        return next()

    def message(self, *, ctx, data, next):
        t = data.get("type") if isinstance(data, dict) else None
        if t:
            print(f"[MW message] type={t}")
        return next()


# ---------------------- UI ----------------------


class LoginState(ps.State):
    email: str = ""
    password: str = ""

    def set_email(self, email: str):
        self.email = email

    def set_password(self, password: str):
        self.password = password


@ps.component
def login():
    state = ps.states(LoginState)

    async def submit():
        # Use call_api helper to set the cookie without page reload
        body = {"email": state.email, "password": state.password}
        print("Calling API with body:", body)
        res = await call_api(
            "http://localhost:8000/api/login", method="POST", body=body
        )
        print("API result:", res)
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
                onChange=lambda evt: state.set_email(evt["target"]["value"]),
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
                onChange=lambda evt: state.set_password(evt["target"]["value"]),
            ),
        ),
        ps.button("Sign in", onClick=submit, className="btn-primary"),
        className="max-w-md mx-auto p-6",
    )


@ps.component
def secret():
    sess = ps.session_context()

    async def sign_out():
        res = await call_api("http://localhost:8000/api/logout", method="POST")
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
    middleware=[LoggingMiddleware(), AuthMiddleware()],
)


# ---------------------- API endpoints ----------------------


@app.fastapi.post("/api/login")
async def api_login(request: Request, response: Response):
    body = await request.json()
    email = body.get("email", "guest")
    # Simple JSON response; Pulse app controls navigation/UI.
    # Optionally update session server-side if the session id is provided
    sess_id = request.headers.get("x-pulse-session-id")
    if sess_id:
        sess = app.sessions.get(sess_id)
        if sess and sess.id == sess_id:
            sess.update_context({"user_email": email})
    resp = JSONResponse({"ok": True})
    # Accept any email/password for demo; set HttpOnly cookie on the same response we return
    resp.set_cookie(
        key=AUTH_COOKIE,
        value=email,
        httponly=True,
        samesite="lax",
        secure=False,  # set True behind https
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return resp


@app.fastapi.post("/api/logout")
async def api_logout(request: Request, response: Response):
    sess_id = request.headers.get("x-pulse-session-id")
    if sess_id:
        sess = app.sessions.get(sess_id)
        if sess and sess.id == sess_id:
            sess.update_context({"user_email": None})
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key=AUTH_COOKIE, path="/")
    return resp


def app_origin(req: Request) -> str:
    h = req.headers
    # Prefer proxy headers
    xf_proto = h.get("x-forwarded-proto")
    xf_host = h.get("x-forwarded-host")
    if xf_proto and xf_host:
        return f"{xf_proto}://{xf_host}".rstrip("/")
    # Then Origin
    origin = h.get("origin")
    if origin:
        return origin.rstrip("/")
    # Then Referer
    referer = h.get("referer")
    if referer:
        p = urlparse(referer)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}".rstrip("/")
    # Fallback
    return str(req.base_url).rstrip("/")
