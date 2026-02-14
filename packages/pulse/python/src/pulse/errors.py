from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
	from pulse.context import PulseContext

logger = logging.getLogger(__name__)

ErrorCode = Literal[
	"render",
	"render.loop",
	"callback",
	"navigate",
	"ref.mount",
	"ref.unmount",
	"timer.later",
	"timer.repeat",
	"channel",
	"form",
	"api",
	"middleware.prerender",
	"middleware.connect",
	"middleware.message",
	"middleware.channel",
	"setup",
	"init",
	"plugin.startup",
	"plugin.setup",
	"plugin.shutdown",
	"query.handler",
	"mutation.handler",
	"system",
]


_ROUTE_REQUIRED_CODES: set[ErrorCode] = {
	"render",
	"render.loop",
	"callback",
	"navigate",
	"ref.mount",
	"ref.unmount",
	"channel",
	"form",
}


def _format_stack(exc: BaseException) -> str:
	return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


class Errors:
	"""Error reporter bound to a PulseContext."""

	__slots__: tuple[str, ...] = ("_context",)
	_context: "PulseContext"

	def __init__(self, context: "PulseContext") -> None:
		self._context = context

	def report(
		self,
		exc: BaseException,
		*,
		code: ErrorCode,
		details: dict[str, Any] | None = None,
		message: str | None = None,
	) -> None:
		ctx = self._context
		render = ctx.render
		route = ctx.route

		route_path: str | None = None
		if route is not None:
			pulse_route = getattr(route, "pulse_route", None)
			if pulse_route is not None and hasattr(pulse_route, "unique_path"):
				route_path = pulse_route.unique_path()
			else:
				try:
					route_path = str(route.pathname)
				except AttributeError:
					route_path = None

		payload_details = dict(details) if details is not None else {}
		render_id = getattr(render, "id", None) if render is not None else None
		if render is not None:
			payload_details.setdefault("render_id", render_id)
		if route_path is not None:
			payload_details.setdefault("route", route_path)

		if render is not None and route_path is None and code in _ROUTE_REQUIRED_CODES:
			payload_details.setdefault("internal_bug", "missing_route_context")
			logger.error(
				"Internal bug: missing route context while reporting code=%s render_id=%s",
				code,
				render_id,
			)

		stack = _format_stack(exc)
		payload_message = message or str(exc)

		if render is not None and route_path is not None:
			try:
				render.send(
					{
						"type": "server_error",
						"path": route_path,
						"error": {
							"message": payload_message,
							"stack": stack,
							"code": code,
							"details": payload_details,
						},
					}
				)
			except Exception as send_exc:
				logger.exception(
					"Failed to forward error to render route",
					exc_info=send_exc,
				)

		logger.error(
			"Pulse error code=%s message=%s details=%s\n%s",
			code,
			payload_message,
			payload_details,
			stack,
		)


__all__ = ["ErrorCode", "Errors"]
