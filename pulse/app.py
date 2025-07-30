"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

from typing import List, Optional, Callable, Any, Dict, TypeVar
from .route import Route
from .state import State, RenderContext, set_render_context
from .vdom import Node, prepare_ui_response
import copy

T = TypeVar('T')

# Global registry for init functions per route
_route_init_registry: Dict[str, Dict[str, Any]] = {}

# Global context for the current route being rendered
_current_active_route: Optional['ActiveRoute'] = None


def init(init_func: Callable[[], T]) -> T:
    """
    Initialize state or other objects that should persist across re-renders.
    
    The init function is only called once per route. Subsequent calls return 
    the same cached result.
    
    Args:
        init_func: Function that returns the object to initialize
        
    Returns:
        The initialized object (same instance across re-renders)
    """
    if _current_active_route is None:
        raise RuntimeError("pulse.init() can only be called during route rendering")
    
    route_path = _current_active_route.path
    
    # Initialize route registry if needed  
    if route_path not in _route_init_registry:
        _route_init_registry[route_path] = {}
    
    # Use the function's id as the key (only one init call per route allowed)
    init_key = "single_init"
    
    if init_key in _route_init_registry[route_path]:
        # Return cached result
        return _route_init_registry[route_path][init_key]
    else:
        # Call init function and cache result
        result = init_func()
        _route_init_registry[route_path][init_key] = result
        
        # If it's a state, track it
        if isinstance(result, State):
            _current_active_route.state = result
            
        return result


class ActiveRoute:
    """
    Represents an active route instance with its current state and VDOM.
    """
    
    def __init__(self, route: Route, path: str, on_update: Optional[Callable] = None):
        self.route = route
        self.path = path
        self.on_update = on_update
        
        # Current VDOM tree
        self.vdom: Optional[Node] = None
        
        # State instance (if any)
        self.state: Optional[State] = None
        
        # Track which states this route depends on
        self.dependent_states: Dict[State, set[str]] = {}
        
        # Render the route initially
        self._render()
    
    def _render(self):
        """Render the route with state tracking."""
        global _current_active_route
        
        # Set this as the current active route
        old_active_route = _current_active_route
        _current_active_route = self
        
        try:
            # Create render context to track state access
            context = RenderContext(active_route=self)
            set_render_context(context)
            
            try:
                # Call the route function to get VDOM
                new_vdom = self.route.render_func()
                
                # Store the accessed states
                self.dependent_states = copy.deepcopy(context.accessed_states)
                
                # Store the new VDOM
                old_vdom = self.vdom
                self.vdom = new_vdom
                
                # If this is not the first render, diff and send updates
                if old_vdom is not None and self.on_update:
                    updates = self._diff_vdom(old_vdom, new_vdom)
                    if updates:
                        self.on_update(updates)
                
            finally:
                # Clear render context
                set_render_context(None)
                
        finally:
            # Restore previous active route
            _current_active_route = old_active_route
    
    def _trigger_rerender(self):
        """Triggered when dependent state changes."""
        self._render()
    
    def _diff_vdom(self, old_vdom: Node, new_vdom: Node) -> List[Dict[str, Any]]:
        """
        Generate updates by diffing old and new VDOM trees.
        
        For now, this is a simple implementation that replaces the entire tree.
        In the future, this should be a more sophisticated diff algorithm.
        """
        # Simple implementation: if anything changed, replace the root
        if self._vdom_to_dict(old_vdom) != self._vdom_to_dict(new_vdom):
            return [{
                "type": "replace",
                "path": [],
                "data": {
                    "node": self._vdom_to_dict(new_vdom)
                }
            }]
        
        return []
    
    def _vdom_to_dict(self, vdom: Node) -> Dict[str, Any]:
        """Convert VDOM node to dictionary for comparison and updates."""
        return vdom.to_dict()


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
    
    def render_route(self, path: str, on_update: Optional[Callable[[List[Dict[str, Any]]], None]] = None) -> 'ActiveRoute':
        """
        Render a route and return an ActiveRoute instance for managing state and updates.
        
        Args:
            path: The route path to render
            on_update: Optional callback to receive VDOM updates when state changes
            
        Returns:
            ActiveRoute instance managing the rendered route
            
        Raises:
            ValueError: If no route matches the given path
        """
        # Find the route that matches this path
        matching_route = None
        for route in self.get_routes():
            if route.path == path:
                matching_route = route
                break
        
        if matching_route is None:
            raise ValueError(f"No route found for path: {path}")
        
        # Create and return an ActiveRoute instance
        return ActiveRoute(matching_route, path, on_update)