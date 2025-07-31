"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

from typing import List, Optional, Callable, Any, Dict, TypeVar

from .route import Route

T = TypeVar("T")


class App:
    """
    Pulse UI Application - the main entry point for defining your app.

    Similar to FastAPI, users create an App instance and define their routes.

    Example:
        ```python
        import pulse as ps

        app = ps.App()

        @app.route("/")
        def home():
            return ps.div("Hello World!")
        ```
    """

    def __init__(self, routes: Optional[List[Route]] = None):
        """
        Initialize a new Pulse App.

        Args:
            routes: Optional list of Route objects to register
        """
        self.routes: List[Route] = routes or []
        self._route_registry: List[Route] = []

    def route(self, path: str, components: Optional[List] = None):
        """
        Decorator to define a route on this app instance.

        Args:
            path: URL path for the route
            components: List of component keys used by this route

        Returns:
            Decorator function
        """

        def decorator(render_func):
            route = Route(path, render_func, components=components or [])
            self.add_route(route)
            return route

        return decorator

    def add_route(self, route: Route):
        """Add a route to this app instance."""
        self._route_registry.append(route)

    def get_routes(self) -> List[Route]:
        """Get all routes registered on this app (both via constructor and decorator)."""
        return self.routes + self._route_registry

    def clear_routes(self):
        """Clear all routes from this app instance."""
        self.routes.clear()
        self._route_registry.clear()

    def get_route(self, path: str):
        for route in self.get_routes():
            if route.path == path:
                return route
        raise ValueError(f"No route found for path '{path}'")

