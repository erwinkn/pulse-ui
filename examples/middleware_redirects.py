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
		request: ps.PulseRequest,
		route_info: ps.RouteInfo,
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
		request: ps.PulseRequest,
		route_info: ps.RouteInfo,
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
		ps.h1(
			"Middleware Redirect & NotFound Demo",
			className="text-4xl font-bold mb-6 text-center",
		),
		ps.p(
			"Welcome to the middleware redirect/notfound test example. Click the links below to test different middleware behaviors.",
			className="text-lg text-gray-700 mb-8 text-center max-w-2xl mx-auto",
		),
		ps.div(
			ps.h2("Test Links", className="text-2xl font-semibold mb-4"),
			ps.ul(
				ps.li(
					ps.a(
						"Visit /old-path (redirects to /new-path)",
						href="/old-path",
						className="link text-blue-600 hover:text-blue-800",
					),
					className="mb-2",
				),
				ps.li(
					ps.a(
						"Visit /blocked-path (returns NotFound)",
						href="/blocked-path",
						className="link text-red-600 hover:text-red-800",
					),
					className="mb-2",
				),
				ps.li(
					ps.a(
						"Visit /old-batch (redirects via prerender)",
						href="/old-batch",
						className="link text-blue-600 hover:text-blue-800",
					),
					className="mb-2",
				),
				ps.li(
					ps.a(
						"Visit /blocked-batch (NotFound via prerender)",
						href="/blocked-batch",
						className="link text-red-600 hover:text-red-800",
					),
					className="mb-2",
				),
				ps.li(
					ps.a(
						"Visit /new-path (works normally)",
						href="/new-path",
						className="link text-green-600 hover:text-green-800",
					),
					className="mb-2",
				),
				ps.li(
					ps.a(
						"Visit /new-batch (works normally)",
						href="/new-batch",
						className="link text-green-600 hover:text-green-800",
					),
					className="mb-2",
				),
				className="list-disc list-inside space-y-2",
			),
			className="bg-white p-6 rounded-lg shadow-md max-w-2xl mx-auto",
		),
		className="min-h-screen bg-gray-100 text-gray-800 py-12 px-4",
	)


@ps.component
def new_path():
	return ps.div(
		ps.h1("New Path", className="text-3xl font-bold mb-4"),
		ps.p(
			"You were redirected here from /old-path!",
			className="text-lg text-gray-700 mb-6",
		),
		ps.a(
			"Back to home",
			href="/",
			className="link text-blue-600 hover:text-blue-800 inline-block",
		),
		className="min-h-screen bg-gray-100 text-gray-800 py-12 px-4 container mx-auto max-w-2xl",
	)


@ps.component
def new_batch():
	return ps.div(
		ps.h1("New Batch", className="text-3xl font-bold mb-4"),
		ps.p(
			"You were redirected here from /old-batch!",
			className="text-lg text-gray-700 mb-6",
		),
		ps.a(
			"Back to home",
			href="/",
			className="link text-blue-600 hover:text-blue-800 inline-block",
		),
		className="min-h-screen bg-gray-100 text-gray-800 py-12 px-4 container mx-auto max-w-2xl",
	)


@ps.component
def normal_page():
	return ps.div(
		ps.h1("Normal Page", className="text-3xl font-bold mb-4"),
		ps.p("This page works normally.", className="text-lg text-gray-700 mb-6"),
		ps.a(
			"Back to home",
			href="/",
			className="link text-blue-600 hover:text-blue-800 inline-block",
		),
		className="min-h-screen bg-gray-100 text-gray-800 py-12 px-4 container mx-auto max-w-2xl",
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
