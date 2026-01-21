from __future__ import annotations

from typing import TYPE_CHECKING

from pulse.middleware import PulseMiddleware
from pulse.routing import Layout, Route

if TYPE_CHECKING:
	from pulse.app import App


class Plugin:
	"""Base class for application plugins.

	Plugins extend application functionality by contributing routes,
	middleware, and lifecycle hooks. Create a subclass and override
	the methods you need.

	Attributes:
		priority: Plugin execution order. Higher values run first.
			Defaults to 0. Use positive values for plugins that should
			initialize early (e.g., auth), negative for late initialization.

	Example:
		```python
		class AuthPlugin(ps.Plugin):
		    priority = 10  # Higher priority runs first

		    def routes(self):
		        return [ps.Route("/login", render=login_page)]

		    def middleware(self):
		        return [AuthMiddleware()]

		    def on_startup(self, app):
		        print("Auth plugin started")
		```
	"""

	priority: int = 0

	def routes(self) -> list[Route | Layout]:
		"""Return routes to add to the application.

		Override to contribute routes from this plugin. Routes are added
		after user-defined routes in the App constructor.

		Returns:
			List of Route or Layout objects to register.
		"""
		return []

	def middleware(self) -> list[PulseMiddleware]:
		"""Return middleware to add to the application.

		Override to contribute middleware from this plugin. Middleware
		is added after user-defined middleware.

		Returns:
			List of PulseMiddleware instances to register.
		"""
		return []

	def on_setup(self, app: App) -> None:
		"""Called after FastAPI routes are configured.

		Override to perform setup that requires FastAPI routes to exist,
		such as adding custom endpoints or middleware.

		Args:
			app: The Pulse application instance.
		"""
		...

	def on_startup(self, app: App) -> None:
		"""Called when the application starts.

		Override to perform initialization when the server begins
		accepting connections, such as connecting to databases or
		initializing caches.

		Args:
			app: The Pulse application instance.
		"""
		...

	def on_shutdown(self, app: App) -> None:
		"""Called when the application shuts down.

		Override to perform cleanup when the server is stopping,
		such as closing database connections or flushing caches.

		Args:
			app: The Pulse application instance.
		"""
		...
