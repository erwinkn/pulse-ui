from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Generic, TypeVar, overload, override

from pulse.messages import (
	ClientMessage,
	Prerender,
	PrerenderPayload,
	ServerInitMessage,
)
from pulse.request import PulseRequest
from pulse.routing import RouteInfo

T = TypeVar("T")


class Redirect:
	path: str

	def __init__(self, path: str) -> None:
		self.path = path


class NotFound: ...


class Ok(Generic[T]):
	payload: T

	@overload
	def __init__(self, payload: T) -> None: ...
	@overload
	def __init__(self, payload: None = None) -> None: ...
	def __init__(self, payload: T | None = None) -> None:
		self.payload = payload  # pyright: ignore[reportAttributeAccessIssue]


class Deny: ...


RoutePrerenderResponse = Ok[ServerInitMessage] | Redirect | NotFound
PrerenderResponse = Ok[Prerender] | Redirect | NotFound
ConnectResponse = Ok[None] | Deny


class PulseMiddleware:
	"""Base middleware with pass-through defaults and short-circuiting.

	Subclass and override any of the hooks. Mutate `context` to attach values
	for later use. Return a decision to allow or short-circuit the flow.
	"""

	async def prerender(
		self,
		*,
		payload: "PrerenderPayload",
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[PrerenderResponse]],
	) -> PrerenderResponse:
		"""Handle batch prerender at the top level.

		Receives the full PrerenderPayload. Call next() to get the PrerenderResult
		and can modify it (views and directives) before returning to the client.
		"""
		return await next()

	async def prerender_route(
		self,
		*,
		path: str,
		request: PulseRequest,
		route_info: RouteInfo,
		session: dict[str, Any],
		next: Callable[[], Awaitable[RoutePrerenderResponse]],
	) -> RoutePrerenderResponse:
		return await next()

	async def connect(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ConnectResponse]],
	) -> ConnectResponse:
		return await next()

	async def message(
		self,
		*,
		data: ClientMessage,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None]]],
	) -> Ok[None] | Deny:
		"""Handle per-message authorization.

		Return Deny() to block, Ok(None) to allow.
		"""
		return await next()

	async def channel(
		self,
		*,
		channel_id: str,
		event: str,
		payload: Any,
		request_id: str | None,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None]]],
	) -> Ok[None] | Deny:
		return await next()


class MiddlewareStack(PulseMiddleware):
	"""Composable stack of `PulseMiddleware` executed in order.

	Each middleware receives a `next` callable that advances the chain. If a
	middleware returns without calling `next`, the chain short-circuits.
	"""

	def __init__(self, middlewares: Sequence[PulseMiddleware]):
		self._middlewares: list[PulseMiddleware] = list(middlewares)

	@override
	async def prerender(
		self,
		*,
		payload: "PrerenderPayload",
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[PrerenderResponse]],
	) -> PrerenderResponse:
		async def dispatch(index: int) -> PrerenderResponse:
			if index >= len(self._middlewares):
				return await next()
			mw = self._middlewares[index]

			async def _next() -> PrerenderResponse:
				return await dispatch(index + 1)

			return await mw.prerender(
				payload=payload,
				request=request,
				session=session,
				next=_next,
			)

		return await dispatch(0)

	@override
	async def prerender_route(
		self,
		*,
		path: str,
		request: PulseRequest,
		route_info: RouteInfo,
		session: dict[str, Any],
		next: Callable[[], Awaitable[RoutePrerenderResponse]],
	) -> RoutePrerenderResponse:
		async def dispatch(index: int) -> RoutePrerenderResponse:
			if index >= len(self._middlewares):
				return await next()
			mw = self._middlewares[index]

			async def _next() -> RoutePrerenderResponse:
				return await dispatch(index + 1)

			return await mw.prerender_route(
				path=path,
				route_info=route_info,
				request=request,
				session=session,
				next=_next,
			)

		return await dispatch(0)

	@override
	async def connect(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ConnectResponse]],
	) -> ConnectResponse:
		async def dispatch(index: int) -> ConnectResponse:
			if index >= len(self._middlewares):
				return await next()
			mw = self._middlewares[index]

			async def _next() -> ConnectResponse:
				return await dispatch(index + 1)

			return await mw.connect(request=request, session=session, next=_next)

		return await dispatch(0)

	@override
	async def message(
		self,
		*,
		data: ClientMessage,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None]]],
	) -> Ok[None] | Deny:
		async def dispatch(index: int) -> Ok[None] | Deny:
			if index >= len(self._middlewares):
				return await next()
			mw = self._middlewares[index]

			async def _next() -> Ok[None]:
				result = await dispatch(index + 1)
				# If dispatch returns Deny, the middleware should have short-circuited
				# This should only be called when continuing the chain
				if isinstance(result, Deny):
					# This shouldn't happen, but handle it gracefully
					return Ok(None)
				return result

			return await mw.message(session=session, data=data, next=_next)

		return await dispatch(0)

	@override
	async def channel(
		self,
		*,
		channel_id: str,
		event: str,
		payload: Any,
		request_id: str | None,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None]]],
	) -> Ok[None] | Deny:
		async def dispatch(index: int) -> Ok[None] | Deny:
			if index >= len(self._middlewares):
				return await next()
			mw = self._middlewares[index]

			async def _next() -> Ok[None]:
				result = await dispatch(index + 1)
				# If dispatch returns Deny, the middleware should have short-circuited
				# This should only be called when continuing the chain
				if isinstance(result, Deny):
					# This shouldn't happen, but handle it gracefully
					return Ok(None)
				return result

			return await mw.channel(
				channel_id=channel_id,
				event=event,
				payload=payload,
				request_id=request_id,
				session=session,
				next=_next,
			)

		return await dispatch(0)


def stack(*middlewares: PulseMiddleware) -> PulseMiddleware:
	"""Helper to build a middleware stack in code.

	Example: `app = App(..., middleware=stack(Auth(), Logging()))`
	Prefer passing a `list`/`tuple` to `App` directly.
	"""
	return MiddlewareStack(list(middlewares))
