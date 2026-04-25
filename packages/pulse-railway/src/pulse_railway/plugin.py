from __future__ import annotations

import hmac
import os
from collections.abc import Awaitable, Callable
from typing import Any, override

import pulse as ps
from fastapi import Header, HTTPException

from pulse_railway.constants import (
	AFFINITY_QUERY_PARAM,
	DEPLOYMENT_META_PATH,
	INTERNAL_RELOAD_PATH,
	INTERNAL_SESSIONS_PATH,
	INTERNAL_TOKEN_HEADER,
	PULSE_DEPLOYMENT_ID,
	PULSE_INTERNAL_TOKEN,
	STALE_AFFINITY_RELOAD_QUERY_PARAM,
)
from pulse_railway.railway import (
	normalize_service_name,
	normalize_service_prefix,
)


class RailwayPlugin(ps.Plugin):
	"""Pulse plugin for Railway deployment affinity."""

	priority: int = 100
	project: str | None
	environment: str | None
	deployment_name: str | None
	image_repository: str | None
	dockerfile: str | None
	router_service: str
	janitor_service: str
	redis_service: str
	service_prefix: str | None
	deployment_id: str
	internal_token: str
	enabled: bool

	def __init__(
		self,
		*,
		dockerfile: str | os.PathLike[str] | None = None,
		project: str | None = None,
		environment: str | None = None,
		deployment_name: str | None = None,
		image_repository: str | None = None,
		router_service: str = "pulse-router",
		janitor_service: str = "pulse-janitor",
		redis_service: str = "pulse-redis",
		service_prefix: str | None = None,
	) -> None:
		self.project = _clean_optional(project)
		self.environment = _clean_optional(environment)
		self.deployment_name = _clean_optional(deployment_name)
		self.image_repository = _clean_optional(image_repository)
		self.dockerfile = _clean_optional(
			os.fspath(dockerfile) if dockerfile is not None else None
		)
		self.router_service = normalize_service_name(router_service)
		self.janitor_service = normalize_service_name(janitor_service)
		self.redis_service = normalize_service_name(redis_service)
		clean_service_prefix = _clean_optional(service_prefix)
		self.service_prefix = (
			normalize_service_prefix(clean_service_prefix)
			if clean_service_prefix is not None
			else None
		)
		self.deployment_id = ""
		self.internal_token = ""
		self.enabled = False

	@property
	def router_service_name(self) -> str:
		return self._service_name(self.router_service)

	@property
	def janitor_service_name(self) -> str:
		return self._service_name(self.janitor_service)

	@property
	def redis_service_name(self) -> str:
		return self._service_name(self.redis_service)

	def _service_name(self, name: str) -> str:
		if self.service_prefix is None:
			return name
		if name.startswith("pulse-"):
			name = name.removeprefix("pulse-")
		return f"{self.service_prefix}{name}"

	@override
	def on_startup(self, app: ps.App) -> None:
		deployment_id = os.environ.get(PULSE_DEPLOYMENT_ID)
		if not deployment_id:
			return
		self.deployment_id = deployment_id
		self.internal_token = os.environ.get(PULSE_INTERNAL_TOKEN, "")
		self.enabled = True

	@override
	def middleware(self) -> list[ps.PulseMiddleware]:
		return [RailwayDirectivesMiddleware(self)]

	@override
	def on_setup(self, app: ps.App) -> None:
		@app.fastapi.get(DEPLOYMENT_META_PATH)
		def deployment_info():  # pyright: ignore[reportUnusedFunction]
			if not self.enabled:
				raise HTTPException(
					status_code=503, detail="Railway plugin is disabled"
				)
			return {
				"status": "ok",
				"deployment_id": self.deployment_id,
				"api_prefix": app.api_prefix,
			}

		@app.fastapi.get(INTERNAL_SESSIONS_PATH)
		def deployment_sessions(  # pyright: ignore[reportUnusedFunction]
			x_internal_token: str | None = Header(
				default=None, alias=INTERNAL_TOKEN_HEADER
			),  # pyright: ignore[reportCallInDefaultInitializer]
		):
			if not self.enabled:
				raise HTTPException(
					status_code=503, detail="Railway plugin is disabled"
				)
			if not self.internal_token or x_internal_token is None:
				raise HTTPException(status_code=403, detail="forbidden")
			if not hmac.compare_digest(x_internal_token, self.internal_token):
				raise HTTPException(status_code=403, detail="forbidden")
			connected_render_count = 0
			resumable_render_count = 0
			for render in app.render_sessions.values():
				if render.connected:
					connected_render_count += 1
				else:
					resumable_render_count += 1
			return {
				"deployment_id": self.deployment_id,
				"connected_render_count": connected_render_count,
				"resumable_render_count": resumable_render_count,
				"drainable": connected_render_count == 0
				and resumable_render_count == 0,
				"session_timeout_seconds": app.session_timeout,
			}

		@app.fastapi.post(INTERNAL_RELOAD_PATH)
		async def reload_deployment_clients(  # pyright: ignore[reportUnusedFunction]
			x_internal_token: str | None = Header(
				default=None, alias=INTERNAL_TOKEN_HEADER
			),  # pyright: ignore[reportCallInDefaultInitializer]
		):
			if not self.enabled:
				raise HTTPException(
					status_code=503, detail="Railway plugin is disabled"
				)
			if not self.internal_token or x_internal_token is None:
				raise HTTPException(status_code=403, detail="forbidden")
			if not hmac.compare_digest(x_internal_token, self.internal_token):
				raise HTTPException(status_code=403, detail="forbidden")
			connected_render_count = 0
			for render in app.render_sessions.values():
				if render.connected:
					connected_render_count += 1
			reloaded_socket_count = await app.reload_connected_clients()
			return {
				"deployment_id": self.deployment_id,
				"connected_render_count": connected_render_count,
				"reloaded_socket_count": reloaded_socket_count,
			}


class RailwayDirectivesMiddleware(ps.PulseMiddleware):
	plugin: RailwayPlugin

	def __init__(self, plugin: RailwayPlugin):
		self.plugin = plugin
		super().__init__()

	@override
	async def prerender(
		self,
		*,
		payload: ps.PrerenderPayload,
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ps.PrerenderResponse]],
	) -> ps.PrerenderResponse:
		if not self.plugin.enabled:
			return await next()
		res = await next()
		if isinstance(res, ps.Ok):
			directives = res.payload["directives"]
			directives["query"][AFFINITY_QUERY_PARAM] = self.plugin.deployment_id
			directives["socketio"]["query"][AFFINITY_QUERY_PARAM] = (
				self.plugin.deployment_id
			)
			directives["socketio"]["query"][STALE_AFFINITY_RELOAD_QUERY_PARAM] = "1"
		return res


__all__ = ["RailwayPlugin"]


def _clean_optional(value: str | None) -> str | None:
	if value is None:
		return None
	candidate = value.strip()
	return candidate or None
