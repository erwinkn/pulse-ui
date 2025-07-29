from typing import List
from .html import Route

# Global registry for routes
_routes: List[Route] = []

def register_route(route: Route):
    """Register a route in the global registry"""
    _routes.append(route)

def get_all_routes() -> List[Route]:
    """Get all registered routes"""
    return _routes.copy()

def clear_routes():
    """Clear all registered routes"""
    global _routes
    _routes = []