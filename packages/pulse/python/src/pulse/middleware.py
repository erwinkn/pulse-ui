from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Generic, TypeVar, overload, override

from pulse.env import env
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
	"""Redirect response. Causes navigation to the specified path.

	Attributes:
		path: The path to redirect to.

	Example:
		>>> return ps.Redirect("/login")
	"""

	path: str

	def __init__(self, path: str) -> None:
		"""Initialize a redirect response.

		Args:
			path: The path to redirect to.
		"""
		self.path = path


class NotFound:
	"""Not found response. Returns 404."""


class Ok(Generic[T]):
	"""Success response wrapper.

	Use ``Ok(None)`` for void success, or ``Ok(payload)`` to wrap a value.

	Attributes:
		payload: The wrapped success value.

	Example:
		>>> return ps.Ok(None)  # Allow request
		>>> return ps.Ok(prerender_result)  # Return with payload
	"""

	payload: T

	@overload
	def __init__(self, payload: T) -> None: ...
	@overload
	def __init__(self, payload: None = None) -> None: ...
	def __init__(self, payload: T | None = None) -> None:
		"""Initialize a success response.

		Args:
			payload: The success value (optional, defaults to None).
		"""
		self.payload = payload  # pyright: ignore[reportAttributeAccessIssue]


class Deny:
	"""Denial response. Blocks the request."""


RoutePrerenderResponse = Ok[ServerInitMessage] | Redirect | NotFound
"""Response type for individual route prerender: ``Ok[ServerInitMessage] | Redirect | NotFound``."""

PrerenderResponse = Ok[Prerender] | Redirect | NotFound
"""Response type for batch prerender: ``Ok[Prerender] | Redirect | NotFound``."""

ConnectResponse = Ok[None] | Deny
"""Response type for WebSocket connection: ``Ok[None] | Deny``."""


class PulseMiddleware:
	"""Base middleware class with pass-through defaults.

	Subclass and override hooks to implement custom behavior. Each hook receives
	a ``next`` callable to continue the middleware chain.

	Attributes:
		dev: If True, middleware is only active in dev environments.

	Example:
		>>> class AuthMiddleware(ps.PulseMiddleware):
		...     async def prerender_route(
		...         self,
		...         *,
		...         path: str,
		...         request: ps.PulseRequest,
		...         route_info: ps.RouteInfo,
		...         session: dict[str, Any],
		...         next,
		...     ):
		...         if path.startswith("/admin") and not session.get("is_admin"):
		...             return ps.Redirect("/login")
		...         return await next()
		...
		...     async def connect(self, *, request, session, next):
		...         if not session.get("user_id"):
		...             return ps.Deny()
		...         return await next()
	"""

	dev: bool

	def __init__(self, dev: bool = False) -> None:
		"""Initialize middleware.

		Args:
			dev: If True, this middleware is only active in dev environments.
		"""
		self.dev = dev

	async def prerender(
		self,
		*,
		payload: "PrerenderPayload",
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[PrerenderResponse]],
	) -> PrerenderResponse:
		"""Handle batch prerender at the top level (HTTP request).

		Args:
			payload: Full prerender payload.
			request: Normalized request object.
			session: Session data dictionary.
			next: Callable to continue the middleware chain.

		Returns:
			``Ok[Prerender]``, ``Redirect``, or ``NotFound``.
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
		"""Handle individual route prerender.

		Args:
			path: Route path being prerendered.
			request: Normalized request object.
			route_info: Route information.
			session: Session data dictionary.
			next: Callable to continue the middleware chain.

		Returns:
			``Ok[ServerInitMessage]``, ``Redirect``, or ``NotFound``.
		"""
		return await next()

	async def connect(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ConnectResponse]],
	) -> ConnectResponse:
		"""Handle WebSocket connection establishment.

		Args:
			request: Normalized request object.
			session: Session data dictionary.
			next: Callable to continue the middleware chain.

		Returns:
			``Ok[None]`` to allow, ``Deny`` to reject.
		"""
		return await next()

	async def message(
		self,
		*,
		data: ClientMessage,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None]]],
	) -> Ok[None] | Deny:
		"""Handle per-message authorization.

		Args:
			data: Client message data.
			session: Session data dictionary.
			next: Callable to continue the middleware chain.

		Returns:
			``Ok[None]`` to allow, ``Deny`` to block.
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
		"""Handle channel message authorization.

		Args:
			channel_id: Channel identifier.
			event: Event name.
			payload: Event payload.
			request_id: Request ID if awaiting response.
			session: Session data dictionary.
			next: Callable to continue the middleware chain.

		Returns:
			``Ok[None]`` to allow, ``Deny`` to block.
		"""
		return await next()


class MiddlewareStack(PulseMiddleware):
	"""Composable stack of ``PulseMiddleware`` executed in order.

	Each middleware receives a ``next`` callable that advances the chain. If a
	middleware returns without calling ``next``, the chain short-circuits.

	Args:
		middlewares: Sequence of middleware instances.

	Example:
		>>> app = ps.App(
		...     middleware=ps.stack(
		...         AuthMiddleware(),
		...         LoggingMiddleware(),
		...     )
		... )
	"""

	def __init__(self, middlewares: Sequence[PulseMiddleware]) -> None:
		"""Initialize middleware stack.

		Args:
			middlewares: Sequence of middleware instances.
		"""
		super().__init__(dev=False)
		# Filter out dev middlewares when not in dev environment
		if env.pulse_env != "dev":
			middlewares = [mw for mw in middlewares if not mw.dev]
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
	"""Compose multiple middlewares into a single middleware stack.

	Args:
		*middlewares: Middleware instances to compose.

	Returns:
		``MiddlewareStack`` instance.

	Example:
		>>> import pulse as ps
		>>>
		>>> app = ps.App(
		...     middleware=ps.stack(
		...         AuthMiddleware(),
		...         LoggingMiddleware(),
		...     )
		... )
	"""
	return MiddlewareStack(list(middlewares))


class LatencyMiddleware(PulseMiddleware):
	"""Middleware that adds artificial latency to simulate network conditions.

	Useful for testing and development to simulate real-world network delays.
	Defaults are realistic for typical web applications.

	Example:
	    ```python
	    app = ps.App(
	        middleware=ps.LatencyMiddleware(
	            prerender_ms=100,
	            connect_ms=50,
	        )
	    )
	    ```
	"""

	prerender_ms: float
	prerender_route_ms: float
	connect_ms: float
	message_ms: float
	channel_ms: float

	def __init__(
		self,
		*,
		prerender_ms: float = 80.0,
		prerender_route_ms: float = 60.0,
		connect_ms: float = 40.0,
		message_ms: float = 25.0,
		channel_ms: float = 20.0,
	) -> None:
		"""Initialize latency middleware.

		Args:
			prerender_ms: Latency for batch prerender requests (HTTP). Default: 80ms
			prerender_route_ms: Latency for individual route prerenders. Default: 60ms
			connect_ms: Latency for WebSocket connections. Default: 40ms
			message_ms: Latency for WebSocket messages (including API calls). Default: 25ms
			channel_ms: Latency for channel messages. Default: 20ms
			dev: If True, only active in dev environments. Default: True
		"""
		super().__init__(dev=True)
		self.prerender_ms = prerender_ms
		self.prerender_route_ms = prerender_route_ms
		self.connect_ms = connect_ms
		self.message_ms = message_ms
		self.channel_ms = channel_ms

	@override
	async def prerender(
		self,
		*,
		payload: "PrerenderPayload",
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[PrerenderResponse]],
	) -> PrerenderResponse:
		if self.prerender_ms > 0:
			await asyncio.sleep(self.prerender_ms / 1000.0)
		return await next()

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
		if self.prerender_route_ms > 0:
			await asyncio.sleep(self.prerender_route_ms / 1000.0)
		return await next()

	@override
	async def connect(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ConnectResponse]],
	) -> ConnectResponse:
		if self.connect_ms > 0:
			await asyncio.sleep(self.connect_ms / 1000.0)
		return await next()

	@override
	async def message(
		self,
		*,
		data: ClientMessage,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None]]],
	) -> Ok[None] | Deny:
		if self.message_ms > 0:
			await asyncio.sleep(self.message_ms / 1000.0)
		return await next()

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
		if self.channel_ms > 0:
			await asyncio.sleep(self.channel_ms / 1000.0)
		return await next()
