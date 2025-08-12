from contextvars import ContextVar
import re
from typing import Callable, Optional, Sequence, TypedDict
from dataclasses import dataclass, field

from pulse.components.registry import ReactComponent
from pulse.reactive import Untrack
from pulse.reactive_extensions import ReactiveDict
from pulse.state import State
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


# ---- Shared helpers ----------------------------------------------------------
def segments_are_dynamic(segments: list[PathSegment]) -> bool:
    """Return True if any segment is dynamic, optional, or a catch-all."""
    return any(s.is_dynamic or s.is_optional or s.is_splat for s in segments)


def route_or_ancestors_have_dynamic(node: "Route | Layout") -> bool:
    """Check whether this node or any ancestor Route contains dynamic segments."""
    current = node
    while current is not None:
        if isinstance(current, Route) and segments_are_dynamic(current.segments):
            return True
        current = current.parent
    return False


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

    def default_route_info(self) -> "RouteInfo":
        """Return a default RouteInfo for this route.

        Only valid for non-dynamic routes. Raises InvalidRouteError if the
        route contains any dynamic (":name"), optional ("segment?"), or
        catch-all ("*") segments. Also rejects if any ancestor Route is dynamic.
        """

        # Disallow optional, dynamic, and catch-all segments on self and ancestors
        if route_or_ancestors_have_dynamic(self):
            raise InvalidRouteError(
                f"Cannot build default RouteInfo for dynamic route '{self.path}'."
            )

        unique = self.unique_path()
        pathname = "/" if unique == "" else f"/{unique}"
        return {
            "pathname": pathname,
            "hash": "",
            "query": "",
            "queryParams": {},
            "pathParams": {},
            "catchall": [],
        }


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

    def default_route_info(self) -> "RouteInfo":
        """Return a default RouteInfo corresponding to this layout's URL path.

        The layout itself does not contribute a path segment. The resulting
        pathname is the URL path formed by its ancestor routes. This method
        raises InvalidRouteError if any ancestor route includes dynamic,
        optional, or catch-all segments because defaults cannot be derived.
        """
        # Walk up the tree to ensure there are no dynamic segments in ancestor routes
        if route_or_ancestors_have_dynamic(self):
            raise InvalidRouteError(
                "Cannot build default RouteInfo for layout under a dynamic route."
            )

        # Build pathname from ancestor route path segments (exclude layout indicators)
        path_list = self._path_list(include_layouts=False)
        unique = normalize_path("/".join(path_list))
        pathname = "/" if unique == "" else f"/{unique}"
        return {
            "pathname": pathname,
            "hash": "",
            "query": "",
            "queryParams": {},
            "pathParams": {},
            "catchall": [],
        }


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
                route.idx = layout_count
            _flatten_route_tree(route)

    def find(self, path: str):
        path = normalize_path(path)
        route = self.flat_tree.get(path)
        if not route:
            raise ValueError(f"No route found for path '{path}'")
        return route


class RouteInfo(TypedDict):
    pathname: str
    hash: str
    query: str
    queryParams: dict[str, str]
    pathParams: dict[str, str]
    catchall: list[str]


class RouteContext:
    @property
    def pathname(self) -> str:
        return self.info["pathname"]

    @property
    def hash(self) -> str:
        return self.info["hash"]

    @property
    def query(self) -> str:
        return self.info["query"]

    @property
    def queryParams(self) -> dict[str, str]:
        return self.info["queryParams"]

    @property
    def pathParams(self) -> dict[str, str]:
        return self.info["pathParams"]

    @property
    def catchall(self) -> list[str]:
        return self.info["catchall"]

    def __init__(self, info: RouteInfo):
        self.info = ReactiveDict(info)

    def update(self, info: RouteInfo):
        self.info.update(info)

    def __enter__(self):
        self._token = ROUTE_CONTEXT.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ROUTE_CONTEXT.reset(self._token)


ROUTE_CONTEXT: ContextVar[RouteContext | None] = ContextVar(
    "pulse_route_context", default=None
)
