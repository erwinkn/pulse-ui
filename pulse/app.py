"""
Pulse UI App class - similar to FastAPI's App.

This module provides the main App class that users instantiate in their main.py
to define routes and configure their Pulse application.
"""

from typing import List, Optional, Callable, Any, TypeVar

from pulse.diff import VDOMUpdate, diff_vdom
from pulse.reactive import ReactiveContext
from pulse.vdom import Node, ReactComponent


T = TypeVar("T")


class Route:
    """
    Represents a route definition with its component dependencies.
    """

    def __init__(
        self,
        path: str,
        render_fn: Callable[[], Node],
        components: list[ReactComponent],
    ):
        self.path = path
        self.render_fn = render_fn
        self.components = components



def route(
    path: str, components: list[ReactComponent] | None = None
) -> Callable[[Callable[[], Node]], Route]:
    """
    Decorator to define a route with its component dependencies.

    Args:
        path: URL path for the route
        components: List of component keys used by this route

    Returns:
        Decorator function
    """

    def decorator(render_func: Callable[[], Node]) -> Route:
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
        routes = routes or []
        self.routes: dict[str, Route] = {}
        for route in routes:
            if route.path in self.routes:
                raise ValueError(f"Duplicate routes on path '{route.path}'")
            self.routes[route.path] = route
        self.sessions: dict[str, Session] = {}

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
        if route.path in self.routes:
            raise ValueError(f"Duplicate routes on path '{route.path}'")
        self.routes[route.path] = route

    def list_routes(self) -> List[Route]:
        """Get all routes registered on this app (both via constructor and decorator)."""
        return list(self.routes.values())

    def clear_routes(self):
        """Clear all routes from this app instance."""
        self.routes.clear()

    def get_route(self, path: str):
        if path not in self.routes:
            raise ValueError(f"No route found for path '{path}'")
        return self.routes[path]

    def create_session(self, id: str):
        if id in self.sessions:
            raise ValueError(f"Session {id} already exists")
        self.sessions[id] = Session(id, self)
        return self.sessions[id]

    def get_session(self, id: str):
        if id not in self.sessions:
            raise KeyError(f"Session {id} does not exist")
        return self.sessions[id]

    def close_session(self, id: str):
        if id not in self.sessions:
            raise KeyError(f"Session {id} does not exist")
        self.sessions[id].close()
        del self.sessions[id]

PulseListener = Callable[[list[VDOMUpdate]], Any]

class Session:
    def __init__(self, id: str, app: App) -> None:
        self.id = id
        self.app = app
        self.listeners: set[PulseListener] = set()

        self.current_route: str | None = None
        self.ctx = ReactiveContext()
        self.callback_registry: dict[str, Callable] = {}
        self.vdom: Node | None = None

    def connect(self, listener: PulseListener):
        self.listeners.add(listener)
        # Return a disconnect function
        return lambda: self.listeners.remove(listener)

    def notify(self, updates: list[VDOMUpdate]):
        for listener in self.listeners:
            listener(updates)

    def close(self):
        self.listeners.clear()
        self.vdom = None
        self.callback_registry.clear()
        for state, fields in self.ctx.client_states.items():
            state.remove_listener(fields, self.rerender)

    def execute_callback(self, key: str):
        self.callback_registry[key]()

    def rerender(self):
        if self.current_route is None:
            raise RuntimeError("Failed to rerender: no route set for the session!")
        return self.render(self.current_route)

    def render(self, path: str):
        route = self.app.get_route(path)
        # Reinitialize render state
        if self.current_route != path:
            self.current_route = path
            self.ctx = ReactiveContext.empty()
            self.callback_registry.clear()
            # don't reset VDOM, it represents what exists on the client


        with self.ctx.next_render() as new_ctx:
            vdom = route.render_fn()
            diff = diff_vdom(self.vdom, vdom)

            # Update callbacks
            remove_callbacks = self.callback_registry.keys() - diff.callbacks.keys()
            add_callbacks = diff.callbacks.keys() - self.callback_registry.keys()
            for key in remove_callbacks:
                del self.callback_registry[key]
            for key in add_callbacks:
                self.callback_registry[key] = diff.callbacks[key]

            # Update state subscriptions
            # TODO: this is the lazy way, can probably be optimized
            for state, fields in self.ctx.client_states.items():
                state.remove_listener(fields, self.rerender)
            for state, fields in new_ctx.client_states.items():
                state.add_listener(fields, self.rerender)

            self.ctx = new_ctx
