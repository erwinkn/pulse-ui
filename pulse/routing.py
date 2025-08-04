import re
from typing import Callable, Literal, Optional, Sequence, Union
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


# According to RFC 3986, a path segment can contain "pchar" characters, which includes:
# - Unreserved characters: A-Z a-z 0-9 - . _ ~
# - Sub-delimiters: ! $ & ' ( ) * + , ; =
# - And ':' and '@'
# - Percent-encoded characters like %20 are also allowed.
PATH_SEGMENT_REGEX = re.compile(r"^([a-zA-Z0-9\-._~!$&'()*+,;=:@]|%[0-9a-fA-F]{2})*$")


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
        self.is_dynamic = any(
            seg.is_dynamic or seg.is_optional for seg in self.segments
        )

    def path_list(self, include_layouts=False) -> list[str]:
        if self.parent:
            return [*self.parent.path_list(include_layouts=include_layouts), self.path]
        return [self.path]

    def unique_path(self):
        return ROUTE_PATH_SEPARATOR.join(self.path_list())

    def file_path(self) -> str:
        path_list = self.path_list()
        path_list = [p for p in path_list if p != LAYOUT_INDICATOR]
        path = "/".join(path_list)
        if self.is_index:
            path += "index"
        path += ".tsx"
        return path

    def __repr__(self) -> str:
        return (
            f"Route(path='{self.path or ''}'"
            + (f", children={len(self.children)}" if self.children else "")
            + ")"
        )


def filter_layouts(path_list: list[str]):
    return [p for p in path_list if p != LAYOUT_INDICATOR]


def replace_layout_indicator(path_list: list[str], value: str):
    return [value if p == LAYOUT_INDICATOR else p for p in path_list]


class Layout:
    def __init__(
        self,
        render: Component | Callable[[], Node],
        children: "Optional[list[Route | Layout]]" = None,
        components: Optional[list[ReactComponent]] = None,
    ):
        if not isinstance(render, Component):
            render = Component(render)
        self.render = render
        self.children = children or []
        self.components = components
        self.parent: Optional[Route | Layout] = None

    def path_list(self, include_layouts=False) -> list[str]:
        path_list = (
            self.parent.path_list(include_layouts=include_layouts)
            if self.parent
            else []
        )
        if include_layouts:
            path_list.append(LAYOUT_INDICATOR)
        return path_list

    def unique_path(self):
        return ROUTE_PATH_SEPARATOR.join(self.path_list(include_layouts=True))

    def file_path(self) -> str:
        path_list = self.path_list(include_layouts=True)
        path_list = ["layout" if p == LAYOUT_INDICATOR else p for p in path_list]
        # Convert all parent layout indicators to simply `layout`
        path_list = path_list[:-1] + ["_layout.tsx"]
        return "/".join(path_list)

    def __repr__(self) -> str:
        return f"Layout(children={len(self.children)})"


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


def link_parental_tree(route: Route | Layout):
    if route.children:
        for child in route.children:
            child.parent = route
            link_parental_tree(child)


class RouteTree:
    flat_tree: dict[str, Route | Layout]

    def __init__(self, routes: Sequence[Route | Layout]) -> None:
        self.tree = list(routes)
        self.flat_tree = {}

        def _flatten_route_tree(route: Route | Layout):
            self.flat_tree[route.unique_path()] = route
            for child in route.children:
                child.parent = route
                _flatten_route_tree(child)

        for route in routes:
            _flatten_route_tree(route)

    def find(self, path: str):
        route = self.flat_tree.get(path)
        if not route:
            raise ValueError(f"No route found for path '{path}'")
        return route
