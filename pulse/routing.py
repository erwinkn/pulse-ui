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


# Normalize to react-router's convention: no leading and trailing slashes. Empty
# string interpreted as the root.
def normalize_path(path: str):
    if path.startswith("/"):
        path = path[1:]
    if path.endswith("/"):
        path = path[:-1]
    return path


class Route:
    """
    Represents a route definition with its component dependencies.
    """

    def __init__(
        self,
        path: str,
        render_fn: Callable[[], Node],
        children: "Optional[list[Route]]" = None,
        components: Optional[list[ReactComponent]] = None,
        parent: "Optional[Route]" = None,
    ):
        self.path = normalize_path(path)
        self.render_fn = render_fn
        self.children = children or []
        self.components = components
        self.parent = parent
        self.is_index = self.path == ""

        if self.parent:
            if self.parent.is_index:
                raise ValueError("Index routes cannot have children.")
            self.parent.children.append(self)

        self.segments = parse_route_path(path)

    def get_full_path(self) -> str:
        if self.parent:
            return f"{self.parent.get_full_path()}/{self.path}"
        return self.path

    def get_file_path(self) -> str:
        path = self.get_full_path()
        if self.is_index:
            path += "index"
        path += ".tsx"
        return path

    def get_safe_path(self) -> str:
        full_path = self.get_full_path()
        # path can contain characters that are not valid in filenames.
        safe_path = (
            full_path.replace("/", "_")
            .replace("-", "_")
            .replace(":", "param_")
            .replace("?", "opt_")
            .replace("*", "splat")
        )
        if safe_path.startswith("_"):
            safe_path = safe_path[1:]
        if not safe_path:
            safe_path = "index"
        return safe_path

    def __call__(self):
        return self.render_fn()

    def get_full_segments(self) -> list[PathSegment]:
        """Returns all segments from the root to this route."""
        if self.parent:
            return self.parent.get_full_segments() + self.segments
        return self.segments

    def match(self, request_path: str) -> Optional[PathParameters]:
        segments = self.get_full_segments()

        if request_path.startswith("/"):
            request_path = request_path[1:]
        if request_path.endswith("/") and len(request_path) > 1:
            request_path = request_path[:-1]

        url_parts = request_path.split("/") if request_path else []

        def _match_recursive(seg_idx: int, url_idx: int) -> Optional[PathParameters]:
            # If we've consumed all route segments, we have a match only if
            # we've also consumed all URL parts.
            if seg_idx == len(segments):
                if url_idx == len(url_parts):
                    return PathParameters()
                return None

            segment = segments[seg_idx]

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
                if all(s.is_optional for s in segments[seg_idx:]):
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

    fragment: str
    """Fragment identifier (e.g., 'section1')"""
    query_params: dict
    """Parsed query parameters as a dict"""
    url: str
    """The original URL string"""
    hostname: Optional[str]
    """The hostname from the netloc"""
    port: Optional[int]
    """The port number from the netloc"""

    path_parameters: dict[str, str]
    "Dynamic and optional path parameters"
    catch_all: list[str]
    "Catch-all path parameters"

    def __init__(self, url: str, path_params: PathParameters):
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
        self.path_parameters = path_params.params
        self.catch_all = path_params.splat


class RouteTree:
    routes: list[Route]

    def __init__(self, routes: list[Route]) -> None:
        seen: set[str] = set()
        self.routes = []
        for route in routes:
            if route.path in seen:
                raise ValueError(f"Duplicate routes on path '{route.path}'")
            seen.add(route.path)
            # Children will be accessible through their parent
            if route.parent:
                continue
            self.routes.append(route)

    def add(self, route: Route):
        """Add a route to the tree, checking for duplicates."""
        if route.parent:
            return  # automatically added by the constructor
        if any(r.path == route.path for r in self.routes):
            raise ValueError(f"Duplicate routes on path '{route.path}'")
        self.routes.append(route)

    def find(self, path: str):
        path = normalize_path(path)
        for route in self.routes:
            if route.path == path:
                return route

        raise ValueError(
            f"No route found for path '{path}' (hierarchical routes are not yet implemented!)"
        )

    def __iter__(self):
        return iter(self.routes)

    def __getitem__(self, idx):
        return self.routes[idx]

    def __len__(self):
        return len(self.routes)
