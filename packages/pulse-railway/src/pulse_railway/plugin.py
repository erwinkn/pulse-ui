from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any, override

import pulse as ps
from fastapi import HTTPException

from pulse_railway.constants import (
	AFFINITY_QUERY_PARAM,
	DEPLOYMENT_META_PATH,
	RAILWAY_DEPLOYMENT_ID_ENV,
)


class RailwayPlugin(ps.Plugin):
	"""Pulse plugin for Railway deployment affinity."""

	priority: int = 100
	deployment_id: str
	enabled: bool

	def __init__(self) -> None:
		self.deployment_id = ""
		self.enabled = False

	@override
	def on_startup(self, app: ps.App) -> None:
		deployment_id = os.environ.get(RAILWAY_DEPLOYMENT_ID_ENV)
		if not deployment_id:
			return
		self.deployment_id = deployment_id
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
