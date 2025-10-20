from __future__ import annotations

from typing import TYPE_CHECKING

from pulse.middleware import PulseMiddleware
from pulse.routing import Layout, Route

if TYPE_CHECKING:
	from pulse.app import App


class Plugin:
	priority: int = 0

	# Optional: return a sequence; return None or [] if not contributing
	def routes(self) -> list[Route | Layout]:
		return []

	def dev_routes(self) -> list[Route | Layout]:
		return []

	def middleware(self) -> list[PulseMiddleware]:
		return []

	# Optional lifecycle
	def on_setup(self, app: App) -> None: ...
	def on_startup(self, app: App) -> None: ...
