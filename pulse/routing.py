import re
from typing import Callable, Optional, Sequence
from dataclasses import dataclass, field

from pulse.components.registry import ReactComponent
from pulse.vdom import Node, Component

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

    def _path_list(self, include_layouts=False) -> list[str]:
        # Question marks cause problems for the URL of our prerendering requests +
        # React-Router file loading
        path = self.path.replace("?", "^")
        if self.parent:
            return [*self.parent._path_list(include_layouts=include_layouts), path]
        return [path]

    def unique_path(self):
        # Ensure consistent keys without accidental leading/trailing slashes
        return normalize_path("/".join(self._path_list()))

    def file_path(self) -> str:
        path = "/".join(self._path_list(include_layouts=False))
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
        # 1-based sibling index assigned by RouteTree at each level
        self.idx: int = 1

    def _path_list(self, include_layouts=False) -> list[str]:
        path_list = (
            self.parent._path_list(include_layouts=include_layouts)
            if self.parent
            else []
        )
        if include_layouts:
            nb = "" if self.idx == 1 else str(self.idx)
            path_list.append(LAYOUT_INDICATOR + nb)
        return path_list

    def unique_path(self):
        return "/".join(self._path_list(include_layouts=True))

    def file_path(self) -> str:
        path_list = self._path_list(include_layouts=True)
        path_list = ["layout" if p == LAYOUT_INDICATOR else p for p in path_list]
        # Convert all parent layout indicators to simply `layout`
        path_list = path_list[:-1] + ["_layout.tsx"]
        return "/".join(path_list)

    def __repr__(self) -> str:
        return f"Layout(children={len(self.children)})"


class InvalidRouteError(Exception): ...


class RouteTree:
    flat_tree: dict[str, Route | Layout]

    def __init__(self, routes: Sequence[Route | Layout]) -> None:
        self.tree = list(routes)
        self.flat_tree = {}

        def _flatten_route_tree(route: Route | Layout):
            key = route.unique_path()
            if key in self.flat_tree:
                if isinstance(route, Layout):
                    raise RuntimeError(f"Multiple layouts have the same path '{key}'")
                else:
                    raise RuntimeError(f"Multiple routes have the same path '{key}'")

            self.flat_tree[key] = route
            layout_count = 0
            for child in route.children:
                if isinstance(child, Layout):
                    layout_count += 1
                    child.idx = layout_count
                child.parent = route
                _flatten_route_tree(child)

        layout_count = 0
        for route in routes:
            if isinstance(route, Layout):
                layout_count += 1
                print(f"Marking layout with idx = {layout_count}")
                route.idx = layout_count
            _flatten_route_tree(route)
        print("Route tree:", self.flat_tree)

    def find(self, path: str):
        path = normalize_path(path)
        route = self.flat_tree.get(path)
        if not route:
            raise ValueError(f"No route found for path '{path}'")
        return route
