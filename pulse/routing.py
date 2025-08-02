import re
from typing import Callable, Optional
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from pulse.components.registry import ReactComponent, registered_react_components
from pulse.vdom import Node


@dataclass
class PathParameters:
    """
    Represents the parameters extracted from a URL path.
    """

    params: dict[str, str] = field(default_factory=dict)
    splat: list[str] = field(default_factory=list)


class PathSegment:
    def __init__(self, part: str):
        if not part:
            raise InvalidRouteError("Route path segment cannot be empty.")

        self.is_splat = part == "*"
        self.is_optional = part.endswith("?")

        value = part[:-1] if self.is_optional else part

        self.is_dynamic = value.startswith(":")

        self.name = value[1:] if self.is_dynamic else value

        # Validate characters
        # The value to validate is the part without ':', '?', or being a splat
        if not self.is_splat and not PATH_SEGMENT_REGEX.match(self.name):
            raise InvalidRouteError(
                f"Path segment '{part}' contains invalid characters."
            )

    def __repr__(self) -> str:
        return f"PathSegment('{self.name}', dynamic={self.is_dynamic}, optional={self.is_optional}, splat={self.is_splat})"


def parse_route_path(path: str) -> list[PathSegment]:
    if path.startswith("/"):
        path = path[1:]
    if path.endswith("/"):
        path = path[:-1]

    if not path:
        return []

    parts = path.split("/")
    segments: list[PathSegment] = []
    for i, part in enumerate(parts):
        segment = PathSegment(part)
        if segment.is_splat and i != len(parts) - 1:
            raise InvalidRouteError(
                f"Splat segment '*' can only be at the end of path '{path}'."
            )
        segments.append(segment)
    return segments


class Route:
    """
    Represents a route definition with its component dependencies.
    """

    def __init__(
        self,
        path: str,
        render_fn: Callable[[], Node],
        components: list[ReactComponent],
        parent: "Optional[Route]" = None,
    ):
        self.path = path
        self.render_fn = render_fn
        self.components = components
        self.parent = parent
        self.is_index = self.path in ["", "/"]

        if self.parent and self.parent.is_index:
            raise ValueError("Index routes cannot have children.")

        self.segments = parse_route_path(path)

    def __call__(self):
        return self.render_fn()

    def get_full_segments(self) -> list[PathSegment]:
        """Returns all segments from the root to this route."""
        if self.parent:
            return self.parent.get_full_segments() + self.segments
        return self.segments

    def match(self, request_path: str) -> Optional[PathParameters]:
        full_segments = self.get_full_segments()

        if request_path.startswith("/"):
            request_path = request_path[1:]
        if request_path.endswith("/") and len(request_path) > 1:
            request_path = request_path[:-1]

        url_parts = request_path.split("/") if request_path else []

        def _match_recursive(seg_idx: int, url_idx: int) -> Optional[PathParameters]:
            # If we've consumed all route segments, we have a match only if
            # we've also consumed all URL parts.
            if seg_idx == len(full_segments):
                if url_idx == len(url_parts):
                    return PathParameters()
                return None

            segment = full_segments[seg_idx]

            # A splat segment matches everything that remains.
            if segment.is_splat:
                return PathParameters(splat=url_parts[url_idx:])

            # If the current segment is optional, we first try to match the
            # rest of the route without consuming this segment.
            if segment.is_optional:
                result = _match_recursive(seg_idx + 1, url_idx)
                if result:
                    return result

            # If we've run out of URL parts, the rest of the route segments
            # must be optional to be a match.
            if url_idx >= len(url_parts):
                if all(s.is_optional for s in full_segments[seg_idx:]):
                    return PathParameters()
                return None

            url_part = url_parts[url_idx]

            # If the segment is dynamic or its name matches the URL part,
            # we consume both and recurse.
            if segment.is_dynamic or segment.name == url_part:
                result = _match_recursive(seg_idx + 1, url_idx + 1)
                if result:
                    if segment.is_dynamic:
                        result.params[segment.name] = url_part
                    return result

            return None

        return _match_recursive(0, 0)


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
    if components is None:
        components = registered_react_components()

    def decorator(render_func: Callable[[], Node]) -> Route:
        route = Route(path, render_func, components=components)
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


# According to RFC 3986, a path segment can contain "pchar" characters, which includes:
# - Unreserved characters: A-Z a-z 0-9 - . _ ~
# - Sub-delimiters: ! $ & ' ( ) * + , ; =
# - And ':' and '@'
# - Percent-encoded characters like %20 are also allowed.
PATH_SEGMENT_REGEX = re.compile(r"^([a-zA-Z0-9\-._~!$&'()*+,;=:@]|%[0-9a-fA-F]{2})*$")


class InvalidRouteError(Exception): ...


class RouteInfo:
    """
    Represents all the parts of a URL.
    """

    scheme: str  # URL scheme specifier (e.g., 'http', 'https')
    netloc: str  # Network location part (e.g., 'example.com:80')
    path: str  # Hierarchical path (e.g., '/foo/bar')
    params: str  # Parameters for last path element
    query: str  # Query component (e.g., 'a=1&b=2')
    fragment: str  # Fragment identifier (e.g., 'section1')
    query_params: dict  # Parsed query parameters as a dict
    url: str  # The original URL string
    hostname: Optional[str]  # The hostname from the netloc
    port: Optional[int]  # The port number from the netloc

    def __init__(self, url: str):
        self.url = url
        parsed_url = urlparse(url)
        self.scheme = parsed_url.scheme
        self.netloc = parsed_url.netloc
        self.path = parsed_url.path
        self.params = parsed_url.params
        self.query = parsed_url.query
        self.fragment = parsed_url.fragment
        self.query_params = parse_qs(self.query)
        self.hostname = parsed_url.hostname
        self.port = parsed_url.port
