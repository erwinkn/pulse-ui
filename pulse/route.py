from typing import Callable
from .nodes import ReactComponent, UITreeNode, get_registered_components


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


def define_route(
    path: str, components: list[str] | None = None
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
        # Get the actual ReactComponent objects for the component keys
        all_components = get_registered_components()
        route_components = []

        if components:
            for component_key in components:
                if component_key in all_components:
                    route_components.append(all_components[component_key])
                else:
                    raise ValueError(
                        f"Component '{component_key}' not found. Make sure to define it before using in routes."
                    )

        route = Route(path, render_func, route_components)
        
        register_route(route)
        
        return route

    return decorator


# Global registry for routes
_routes: list[Route] = []

def register_route(route: Route):
    """Register a route in the global registry"""
    _routes.append(route)

def get_all_routes() -> list[Route]:
    """Get all registered routes"""
    return _routes.copy()

def clear_routes():
    """Clear all registered routes"""
    global _routes
    _routes = []