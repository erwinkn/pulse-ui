from collections import defaultdict
from typing import Any, Callable, Optional

from pulse.diff import VDOM, VDOMUpdate, diff_vdom
from pulse.state import ReactiveContext, State
from pulse.vdom import ReactComponent, Node


CURRENT_ACTIVE_ROUTE: "Route | None" = None


def current_active_route():
    return CURRENT_ACTIVE_ROUTE


OnRouteUpdate = Callable[[list[VDOMUpdate]], Any]


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

        # Current VDOM tree
        self.vdom: Optional[Node] = None
        self.dependencies: dict[State, set[str]] = defaultdict(set)
        self._on_update: OnRouteUpdate | None = None

    def _signal_update(self, updates: list[VDOMUpdate]):
        if self._on_update:
            self._on_update(updates)

    @property
    def state(self):
        from .reactive import ROUTE_STATES

        return ROUTE_STATES.get(self.path)

    def rerender_on_update(self):
        """Rerenders the component and notifies listeners of updates."""
        self.render()

    def render(self) -> Node:
        # Create render context to track state access
        global CURRENT_ACTIVE_ROUTE
        try:
            CURRENT_ACTIVE_ROUTE = self
            with ReactiveContext() as ctx:
                new_vdom = self.render_fn()
                # Store the new VDOM
                old_vdom = self.vdom
                self.vdom = new_vdom

                all_states = self.dependencies.keys() | ctx.accessed_states.keys()
                for state in all_states:
                    prev_deps = self.dependencies.get(state, set())
                    new_deps = ctx.accessed_states.get(state, set())
                    remove_deps = prev_deps - new_deps
                    add_deps = new_deps - prev_deps
                    for dep in remove_deps:
                        state.remove_listener(dep, self.rerender_on_update)
                    for dep in add_deps:
                        state.add_listener(dep, self.rerender_on_update)
                self.dependencies = ctx.accessed_states

                # If this is not the first render, diff and send updates
                if old_vdom is not None:
                    updates = diff_vdom(old_vdom, new_vdom)
                    if updates:
                        self._signal_update(updates)
                return new_vdom
        finally:
            CURRENT_ACTIVE_ROUTE = None

    def mount(self, on_update: Callable) -> VDOM:
        self._on_update = on_update
        return self.render()

    def unmount(self):
        self._on_update = None
        for state, deps_list in self.dependencies.items():
            for dep in deps_list:
                state.remove_listener(dep, self.rerender_on_update)


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
