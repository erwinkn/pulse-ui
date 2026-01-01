"""
Example: Cookie-based auth with FastAPI endpoints.

Dev assumptions:
- Node and Python run on the same host (e.g., localhost) even if ports differ.
- Cookies are keyed by host, not port, so the cookie will be sent to both.
- In production, put both behind the same origin or use Domain=.example.com.

This example shows:
- A /secret route that redirects to /login if the user is not authenticated
- A /login page (any email/password) posting to Python endpoints to set a cookie
- A sign-out button that clears the cookie
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, override
from urllib.parse import urlparse

import pulse as ps
from fastapi import Request, Response
from fastapi.responses import JSONResponse


# Simple logging/timing middleware
class LoggingMiddleware(ps.PulseMiddleware):
	@override
	async def prerender_route(
		self,
		*,
		path: str,
		route_info: ps.RouteInfo,
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ps.RoutePrerenderResponse]],
	) -> ps.RoutePrerenderResponse:
		start = time.perf_counter()
		res = await next()
		duration_ms = (time.perf_counter() - start) * 1000
		print(f"[MW prerender] path={path} took={duration_ms:.1f}ms")
		return res

	@override
	async def connect(
		self,
		*,
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ps.ConnectResponse]],
	) -> ps.ConnectResponse:
		ua = request.headers.get("user-agent")
		ip = request.client[0] if request.client else None
		print(f"[MW connect] ip={ip} ua={(ua or '')[:60]}")
		return await next()

	@override
	async def message(
		self,
		*,
		data: ps.ClientMessage,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ps.Ok[None]]],
	) -> ps.Ok[None] | ps.Deny:
		t = data.get("type") if isinstance(data, dict) else None
		if t:
			print(f"[MW message] type={t}")
		return await next()


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
	with ps.init():
		state = LoginState()

	async def submit():
		# Use call_api helper to set the cookie without page reload
		body = {"email": state.email, "password": state.password}
		print("Calling API with body:", body)
		res = await ps.call_api("/api/login", method="POST", body=body)
		print("API result:", res)
		if res.get("ok"):
			ps.navigate("/secret")

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
	sess = ps.session()
	if not sess.get("user_email"):
		ps.redirect("/login")

	nickname = sess.get("nickname", "")

	async def sign_out():
		res = await ps.call_api("/api/logout", method="POST")
		if res.get("ok"):
			ps.navigate("/")

	def log_session_callback():
		print("[CB] session ctx", {k: v for k, v in ps.session().items()})

	async def log_session_via_api():
		await ps.call_api("/api/log-session", method="POST")

	return ps.div(
		ps.h2("Secret", className="text-2xl font-bold mb-4"),
		ps.p(f"Welcome {sess.get('user_email', '<unknown>')}"),
		ps.div(
			ps.label("Nickname", htmlFor="nickname", className="block mb-1 mt-4"),
			ps.input(
				id="nickname",
				name="nickname",
				type="text",
				className="input mb-3",
				value=nickname,
				onChange=lambda evt: sess.update({"nickname": evt["target"]["value"]}),
			),
		),
		ps.div(
			ps.button(
				"Log session on server (callback)",
				onClick=log_session_callback,
				className="btn mt-2 mr-2",
			),
			ps.button(
				"Log session via API",
				onClick=log_session_via_api,
				className="btn mt-2",
			),
		),
		ps.div(
			ps.h3("Session context", className="text-xl font-semibold mt-4 mb-2"),
			ps.pre(
				json.dumps({k: v for k, v in sess.items()}, indent=2),
				className="bg-gray-100 p-3 rounded text-sm overflow-auto",
			),
		),
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
	middleware=[LoggingMiddleware()],
)


# ---------------------- API endpoints ----------------------


@app.fastapi.post("/api/login")
async def api_login(request: Request, response: Response):
	body = await request.json()
	email = body.get("email", "guest")
	# Update Pulse session; Pulse middleware will write the cookie per configured store
	ps.session().update({"user_email": email})
	return JSONResponse({"ok": True})


@app.fastapi.post("/api/logout")
async def api_logout(request: Request, response: Response):
	# Clear user info in Pulse session; middleware updates cookie accordingly
	try:
		s = ps.session()
		if "user_email" in s:
			del s["user_email"]
		# Optionally clear other session fields here (e.g., nickname)
	except Exception:
		pass
	return JSONResponse({"ok": True})


@app.fastapi.post("/api/log-session")
async def api_log_session(request: Request):
	try:
		ctx = ps.session()
		print("[API log-session] ctx:", {k: v for k, v in ctx.items()})
	except Exception as e:
		print("[API log-session] failed to access session:", e)
	return JSONResponse({"ok": True})


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
