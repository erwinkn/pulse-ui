from typing import Callable
from .nodes import ReactComponent, UITreeNode


class Route:
    """
    Represents a route definition with its component dependencies.
    """

    def __init__(
        self,
        path: str,
        render_func: Callable[[], UITreeNode],
        components: list[ReactComponent],
    ):
        self.path = path
        self.render_func = render_func
        self.components = components


def route(
    path: str, components: list[ReactComponent] | None = None
) -> Callable[[Callable[[], UITreeNode]], Route]:
    """
    Decorator to define a route with its component dependencies.

    Args:
        path: URL path for the route
        components: List of component keys used by this route

    Returns:
        Decorator function
    """

    def decorator(render_func: Callable[[], UITreeNode]) -> Route:
        route = Route(path, render_func, components=components or [])
        add_route(route)
        return route

    return decorator


# Global registry for routes
ROUTES: list[Route] = []


def add_route(route: Route):
    """Register a route in the global registry"""
    ROUTES.append(route)


def decorated_routes() -> list[Route]:
    """Get all registered routes"""
    return ROUTES.copy()


def clear_routes():
    """Clear all registered routes"""
    global ROUTES
    ROUTES = []
