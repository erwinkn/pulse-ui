"""FastAPI route/router classes for user APIs and Pulse built-in endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from functools import wraps
from typing import Any, Callable, override

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response

from pulse.reactive_extensions import unwrap
from pulse.request import PulseRequest


def _wrap_user_api_handler(
	original: Callable[[Request], Coroutine[Any, Any, Response]],
) -> Callable[[Request], Coroutine[Any, Any, Response]]:
	async def handler(request: Request) -> Response:
		# Late import: pulse.context ↔ pulse.app cycle.
		from pulse.context import PULSE_CONTEXT

		ctx = PULSE_CONTEXT.get()
		if ctx is None or ctx.session is None:
			# No Pulse request: raw FastAPI, or session_middleware hasn't run.
			return await original(request)

		async def _next() -> Response:
			return await original(request)

		response = await ctx.app.middleware.api(
			request=PulseRequest.from_fastapi(request),
			session=ctx.session.data,
			next=_next,
		)
		if not isinstance(response, Response):
			raise TypeError(
				"PulseMiddleware.api() must return a Response, "
				+ f"got {type(response).__name__}"
			)
		return response

	return handler


def _wrap_fastapi_endpoint(endpoint: Callable[..., Any]) -> Callable[..., Any]:
	if asyncio.iscoroutinefunction(endpoint):

		@wraps(endpoint)
		async def async_endpoint(*args: Any, **kwargs: Any) -> Any:
			return _unwrap_fastapi_response(await endpoint(*args, **kwargs))

		return async_endpoint

	@wraps(endpoint)
	def sync_endpoint(*args: Any, **kwargs: Any) -> Any:
		return _unwrap_fastapi_response(endpoint(*args, **kwargs))

	return sync_endpoint


def _unwrap_fastapi_response(value: Any) -> Any:
	if isinstance(value, Response):
		return value
	return unwrap(value, untrack=True)


class PulseFrameworkAPIRoute(APIRoute):
	"""Pulse built-in FastAPI routes: unwrap reactives, no ``api`` hook."""

	def __init__(
		self,
		path: str,
		endpoint: Callable[..., Any],
		**kwargs: Any,
	) -> None:
		# Leave endpoint as the user function. include_router copies route.endpoint
		# into a new route; wrapping that would stack wrappers. Unwrap the call
		# FastAPI actually invokes — rebuilt per copy.
		super().__init__(path, endpoint, **kwargs)
		call = self.dependant.call
		if call is None:
			raise TypeError("FastAPI route has no endpoint")
		self.dependant.call = _wrap_fastapi_endpoint(call)


class PulseAPIRoute(PulseFrameworkAPIRoute):
	"""User-defined FastAPI routes: unwrap reactives and run ``PulseMiddleware.api``."""

	@override
	def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
		return _wrap_user_api_handler(super().get_route_handler())


class PulseAPIRouter(APIRouter):
	"""App router that keeps ``PulseAPIRoute`` when including foreign routers.

	``APIRouter.include_router`` copies routes with ``route_class_override=type(source)``,
	which would drop ``PulseMiddleware.api``. Ignore that override unless the
	source is a Pulse framework route.
	"""

	@override
	def add_api_route(
		self,
		path: str,
		endpoint: Callable[..., Any],
		**kwargs: Any,
	) -> None:
		override = kwargs.get("route_class_override")
		if override is not None and not issubclass(override, PulseFrameworkAPIRoute):
			kwargs["route_class_override"] = None
		super().add_api_route(path, endpoint, **kwargs)


class PulseFastAPI(FastAPI):
	def __init__(self, *args: Any, **kwargs: Any) -> None:
		super().__init__(*args, **kwargs)
		# FastAPI hardcodes APIRouter(); adopt it in place so include_router
		# keeps PulseAPIRoute. PulseAPIRouter is stateless — methods only.
		if type(self.router) is not APIRouter:
			raise TypeError(
				"Expected FastAPI to construct a stock APIRouter, "
				+ f"got {type(self.router).__name__}"
			)
		self.router.__class__ = PulseAPIRouter
		self.router.route_class = PulseAPIRoute
