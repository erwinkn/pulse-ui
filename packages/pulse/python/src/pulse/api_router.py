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

PULSE_ENDPOINT_UNWRAP_MARKER = "__pulse_endpoint_unwrap__"


def _wrap_user_api_handler(
	original: Callable[[Request], Coroutine[Any, Any, Response]],
) -> Callable[[Request], Coroutine[Any, Any, Response]]:
	async def handler(request: Request) -> Response:
		# Late import: pulse.context ↔ pulse.app cycle.
		from pulse.context import PULSE_CONTEXT

		ctx = PULSE_CONTEXT.get()
		if ctx is None:
			return await original(request)

		session: dict[str, Any] = ctx.session.data if ctx.session is not None else {}

		async def _next() -> Response:
			return await original(request)

		response = await ctx.app.middleware.api(
			request=PulseRequest.from_fastapi(request),
			session=session,
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
	if endpoint.__dict__.get(PULSE_ENDPOINT_UNWRAP_MARKER):
		return endpoint

	if asyncio.iscoroutinefunction(endpoint):

		@wraps(endpoint)
		async def async_endpoint(*args: Any, **kwargs: Any) -> Any:
			return _unwrap_fastapi_response(await endpoint(*args, **kwargs))

		async_endpoint.__dict__[PULSE_ENDPOINT_UNWRAP_MARKER] = True
		return async_endpoint

	@wraps(endpoint)
	def sync_endpoint(*args: Any, **kwargs: Any) -> Any:
		return _unwrap_fastapi_response(endpoint(*args, **kwargs))

	sync_endpoint.__dict__[PULSE_ENDPOINT_UNWRAP_MARKER] = True
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
		super().__init__(path, _wrap_fastapi_endpoint(endpoint), **kwargs)


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
