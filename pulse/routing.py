import re
from typing import Callable, Optional, Sequence, Union
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from pulse.component import Component
from pulse.components.registry import ReactComponent
from pulse.vdom import Node

ROUTE_PATH_SEPARATOR = "|"
# angle brackets cannot appear in a regular URL path, this ensures no name conflicts
LAYOUT_INDICATOR = "<layout>"


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
        render: Component | Callable[[], Node],
        children: "Optional[list[Route | Layout]]" = None,
        components: Optional[list[ReactComponent]] = None,
    ):
        self.path = normalize_path(path)
        self.segments = parse_route_path(path)

        if not isinstance(render, Component):
            render = Component(render)
        self.render = render
        self.children = children or []
        self.components = components
        self.parent: Optional[Route | Layout] = None

        self.is_index = self.path == ""

    def path_list(self) -> Sequence[str]:
        if self.parent:
            return [*self.parent.path_list(), self.path]
        return [self.path]

    def full_path(self):
        return ROUTE_PATH_SEPARATOR.join(self.path_list())

    def file_path(self) -> str:
        path_list = self.path_list()
        path_list = [p for p in path_list if p != LAYOUT_INDICATOR]
        path = "/".join(self.path_list())
        if self.is_index:
            path += "index"
        path += ".tsx"
        return path


class Layout:
    def __init__(
        self,
        render: Component,
        children: "Optional[list[Route | Layout]]" = None,
        components: Optional[list[ReactComponent]] = None,
    ):
        self.render = render
        self.children = children or []
        self.components = components
        self.parent: Optional[Route | Layout] = None

    def path_list(self) -> Sequence[str]:
        # Layouts don't contribute to the path
        if self.parent:
            return [*self.parent.path_list(), LAYOUT_INDICATOR]
        else:
            return [LAYOUT_INDICATOR]

    def full_path(self):
        return ROUTE_PATH_SEPARATOR.join(self.path_list())

    def file_path(self) -> str:
        return "/".join(self.path_list()) + ".tsx"


route = Route
layout = Layout


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


def add_parental_links(route: Route | Layout):
    if route.children:
        for child in route.children:
            child.parent = route
            add_parental_links(child)


class RouteTree:
    routes: list[Route | Layout]

    def __init__(self, routes: Sequence[Route | Layout]) -> None:
        self.routes = list(routes)
        for route in self.routes:
            add_parental_links(route)

    def find(self, path: str) -> Union[Route, Layout]:
        parts = path.split(ROUTE_PATH_SEPARATOR)
        current_nodes: list[Route | Layout] = self.routes
        found_node: Route | Layout | None = None

        for i, path_fragment in enumerate(parts):
            path_fragment = normalize_path(path_fragment)

            node_for_fragment = None
            for node in current_nodes:
                if path_fragment == LAYOUT_INDICATOR and isinstance(node, Layout):
                    node_for_fragment = node
                    break
                elif isinstance(node, Route) and node.path == path_fragment:
                    node_for_fragment = node
                    break

            if node_for_fragment:
                if i == len(parts) - 1:
                    found_node = node_for_fragment
                current_nodes = node_for_fragment.children
            else:
                raise ValueError(f"No route found for path '{path}'")

        if found_node:
            return found_node

        raise ValueError(f"No route found for path '{path}'")

    def __iter__(self):
        return iter(self.routes)

    def __len__(self):
        return len(self.routes)
