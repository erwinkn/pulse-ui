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
	INTERNAL_SESSIONS_PATH,
	INTERNAL_TOKEN_HEADER,
	PULSE_DEPLOYMENT_ID,
	PULSE_INTERNAL_TOKEN,
)


class RailwayPlugin(ps.Plugin):
	"""Pulse plugin for Railway deployment affinity."""

	priority: int = 100
	deployment_id: str
	internal_token: str
	enabled: bool

	def __init__(self) -> None:
		self.deployment_id = ""
		self.internal_token = ""
		self.enabled = False

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
		def deployment_sessions(
			x_internal_token: str | None = Header(
				default=None, alias=INTERNAL_TOKEN_HEADER
			),
		):  # pyright: ignore[reportUnusedFunction]
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
		return res


__all__ = ["RailwayPlugin"]
