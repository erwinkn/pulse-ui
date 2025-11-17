"""
Example: Testing Redirect and NotFound responses from middleware.

This example demonstrates:
- Middleware returning Redirect from prerender()
- Middleware returning NotFound from prerender()
- Middleware returning Redirect from prerender_route()
- Middleware returning NotFound from prerender_route()
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, override

import pulse as ps
from pulse.middleware import (
	NotFound,
	PrerenderResponse,
	Redirect,
	RoutePrerenderResponse,
)


# Middleware that tests prerender_route redirects
class RouteRedirectMiddleware(ps.PulseMiddleware):
	"""Redirects /old-path to /new-path at prerender_route level."""

	@override
	async def prerender_route(
		self,
		*,
		path: str,
		route_info: ps.RouteInfo,
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[RoutePrerenderResponse]],
	) -> RoutePrerenderResponse:
		print(f"[RouteRedirectMiddleware] prerender_route path={path}")
		if path == "/old-path":
			print(f"[RouteRedirectMiddleware] Redirecting {path} -> /new-path")
			return Redirect("/new-path")
		return await next()


# Middleware that tests prerender_route not found
class RouteNotFoundMiddleware(ps.PulseMiddleware):
	"""Returns NotFound for /blocked-path at prerender_route level."""

	@override
	async def prerender_route(
		self,
		*,
		path: str,
		route_info: ps.RouteInfo,
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[RoutePrerenderResponse]],
	) -> RoutePrerenderResponse:
		if path == "/blocked-path":
			print(f"[RouteNotFoundMiddleware] Blocking {path} with NotFound")
			return NotFound()
		return await next()


# Middleware that tests prerender redirects
class PrerenderRedirectMiddleware(ps.PulseMiddleware):
	"""Redirects /old-batch to /new-batch at prerender level."""

	@override
	async def prerender(
		self,
		*,
		payload: "ps.PrerenderPayload",
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[PrerenderResponse]],
	) -> PrerenderResponse:
		# Check if any path in the batch should be redirected
		if "/old-batch" in payload["paths"]:
			print("[PrerenderRedirectMiddleware] Redirecting /old-batch -> /new-batch")
			return Redirect("/new-batch")

		return await next()


# Middleware that tests prerender not found
class PrerenderNotFoundMiddleware(ps.PulseMiddleware):
	"""Returns NotFound for /blocked-batch at prerender level."""

	@override
	async def prerender(
		self,
		*,
		payload: "ps.PrerenderPayload",
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[PrerenderResponse]],
	) -> PrerenderResponse:
		# Check if any path in the batch should be blocked
		if "/blocked-batch" in payload["paths"]:
			print("[PrerenderNotFoundMiddleware] Blocking /blocked-batch with NotFound")
			return NotFound()

		return await next()


# ---------------------- UI Components ----------------------


@ps.component
def home():
	return ps.div(
		ps.h1("Home"),
		ps.p("Welcome to the middleware redirect/notfound test example."),
		ps.ul(
			ps.li(
				ps.a({"href": "/old-path"}, "Visit /old-path (redirects to /new-path)")
			),
			ps.li(
				ps.a(
					{"href": "/blocked-path"}, "Visit /blocked-path (returns NotFound)"
				)
			),
			ps.li(
				ps.a(
					{"href": "/old-batch"}, "Visit /old-batch (redirects via prerender)"
				)
			),
			ps.li(
				ps.a(
					{"href": "/blocked-batch"},
					"Visit /blocked-batch (NotFound via prerender)",
				)
			),
			ps.li(ps.a({"href": "/new-path"}, "Visit /new-path (works normally)")),
			ps.li(ps.a({"href": "/new-batch"}, "Visit /new-batch (works normally)")),
		),
	)


@ps.component
def new_path():
	return ps.div(
		ps.h1("New Path"),
		ps.p("You were redirected here from /old-path!"),
		ps.a({"href": "/"}, "Back to home"),
	)


@ps.component
def new_batch():
	return ps.div(
		ps.h1("New Batch"),
		ps.p("You were redirected here from /old-batch!"),
		ps.a({"href": "/"}, "Back to home"),
	)


@ps.component
def normal_page():
	return ps.div(
		ps.h1("Normal Page"),
		ps.p("This page works normally."),
		ps.a({"href": "/"}, "Back to home"),
	)


# Placeholder components for routes that middleware will intercept
# These will never actually render, but ensure React Router matches the routes
@ps.component
def placeholder_old_path():
	"""Placeholder for /old-path - middleware redirects before this renders."""
	return ps.div("This should never render")


@ps.component
def placeholder_blocked_path():
	"""Placeholder for /blocked-path - middleware returns NotFound before this renders."""
	return ps.div("This should never render")


@ps.component
def placeholder_old_batch():
	"""Placeholder for /old-batch - middleware redirects before this renders."""
	return ps.div("This should never render")


@ps.component
def placeholder_blocked_batch():
	"""Placeholder for /blocked-batch - middleware returns NotFound before this renders."""
	return ps.div("This should never render")


# Routing
app = ps.App(
	routes=[
		ps.Route("/", home),
		ps.Route("/new-path", new_path),
		ps.Route("/new-batch", new_batch),
		ps.Route("/normal", normal_page),
		# Placeholder routes to ensure React Router matches them
		# Middleware will intercept these before components render
		ps.Route("/old-path", placeholder_old_path),
		ps.Route("/blocked-path", placeholder_blocked_path),
		ps.Route("/old-batch", placeholder_old_batch),
		ps.Route("/blocked-batch", placeholder_blocked_batch),
	],
	middleware=[
		RouteRedirectMiddleware(),
		RouteNotFoundMiddleware(),
		PrerenderRedirectMiddleware(),
		PrerenderNotFoundMiddleware(),
	],
)
