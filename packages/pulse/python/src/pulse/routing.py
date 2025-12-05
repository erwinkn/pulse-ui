import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict, cast, override

from pulse.env import env
from pulse.react_component import ReactComponent
from pulse.reactive_extensions import ReactiveDict
from pulse.vdom import Component

if TYPE_CHECKING:
	from pulse.javascript.function import AnyJsFunction

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
	is_splat: bool
	is_optional: bool
	is_dynamic: bool
	name: str

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

	@override
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
def ensure_relative_path(path: str):
	if path.startswith("/"):
		path = path[1:]
	if path.endswith("/"):
		path = path[:-1]
	return path


def ensure_absolute_path(path: str):
	if not path.startswith("/"):
		path = "/" + path
	return path


# ---- Shared helpers ----------------------------------------------------------
def segments_are_dynamic(segments: list[PathSegment]) -> bool:
	"""Return True if any segment is dynamic, optional, or a catch-all."""
	return any(s.is_dynamic or s.is_optional or s.is_splat for s in segments)


def _sanitize_filename(path: str) -> str:
	"""Replace Windows-invalid characters in filenames with safe alternatives."""
	import hashlib

	# Split path into segments to handle each part individually
	segments = path.split("/")
	sanitized_segments: list[str] = []

	for segment in segments:
		if not segment:
			continue

		# Check if segment contains Windows-invalid characters
		invalid_chars = '<>:"|?*'
		has_invalid = any(char in segment for char in invalid_chars)

		if has_invalid:
			# Create a collision-safe filename by replacing invalid chars and adding hash
			# Remove extension temporarily for hashing
			name, ext = segment.rsplit(".", 1) if "." in segment else (segment, "")

			# Replace invalid characters with underscores
			sanitized_name = name
			for char in invalid_chars:
				sanitized_name = sanitized_name.replace(char, "_")

			# Add hash of original segment to prevent collisions
			original_hash = hashlib.md5(segment.encode()).hexdigest()[:8]
			sanitized_name = f"{sanitized_name}_{original_hash}"

			# Reattach extension
			segment = f"{sanitized_name}.{ext}" if ext else sanitized_name

		sanitized_segments.append(segment)

	return "/".join(sanitized_segments)


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

	path: str
	segments: list[PathSegment]
	render: Component[[]]
	children: Sequence["Route | Layout"]
	components: Sequence[ReactComponent[...]] | None
	functions: "Sequence[AnyJsFunction] | None"
	is_index: bool
	is_dynamic: bool
	dev: bool

	def __init__(
		self,
		path: str,
		render: Component[[]],
		children: "Sequence[Route | Layout] | None" = None,
		components: "Sequence[ReactComponent[...]] | None" = None,
		functions: "Sequence[AnyJsFunction] | None" = None,
		dev: bool = False,
	):
		self.path = ensure_relative_path(path)
		self.segments = parse_route_path(path)

		self.render = render
		self.children = children or []
		self.components = components
		self.functions = functions
		self.dev = dev
		self.parent: Route | Layout | None = None

		self.is_index = self.path == ""
		self.is_dynamic = any(
			seg.is_dynamic or seg.is_optional for seg in self.segments
		)

	def _path_list(self, include_layouts: bool = False) -> list[str]:
		# Question marks cause problems for the URL of our prerendering requests +
		# React-Router file loading
		path = self.path.replace("?", "^")
		if self.parent:
			return [*self.parent._path_list(include_layouts=include_layouts), path]  # pyright: ignore[reportPrivateUsage]
		return [path]

	def unique_path(self):
		# Return absolute path with leading '/'
		return ensure_absolute_path("/".join(self._path_list()))

	def file_path(self) -> str:
		path = "/".join(self._path_list(include_layouts=False))
		if self.is_index:
			path += "index"
		path += ".jsx"
		# Replace Windows-invalid characters in filenames
		return _sanitize_filename(path)

	@override
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

		pathname = self.unique_path()
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
	render: Component[...]
	children: Sequence["Route | Layout"]
	components: Sequence[ReactComponent[...]] | None
	functions: "Sequence[AnyJsFunction] | None"
	dev: bool

	def __init__(
		self,
		render: "Component[...]",
		children: "Sequence[Route | Layout] | None" = None,
		components: "Sequence[ReactComponent[...]] | None" = None,
		functions: "Sequence[AnyJsFunction] | None" = None,
		dev: bool = False,
	):
		self.render = render
		self.children = children or []
		self.components = components
		self.functions = functions
		self.dev = dev
		self.parent: Route | Layout | None = None
		# 1-based sibling index assigned by RouteTree at each level
		self.idx: int = 1

	def _path_list(self, include_layouts: bool = False) -> list[str]:
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
		# Return absolute path with leading '/'
		path = "/".join(self._path_list(include_layouts=True))
		return f"/{path}"

	def file_path(self) -> str:
		path_list = self._path_list(include_layouts=True)
		# Map layout indicators (with optional numeric suffix) to directory names
		# e.g., "<layout>" -> "layout" and "<layout>2" -> "layout2"
		converted: list[str] = []
		for seg in path_list:
			if seg.startswith(LAYOUT_INDICATOR):
				suffix = seg[len(LAYOUT_INDICATOR) :]
				converted.append("layout" + suffix)
			else:
				converted.append(seg)
		# Place file within the current layout's directory
		path = "/".join([*converted, "_layout.tsx"])
		# Replace Windows-invalid characters in filenames
		return _sanitize_filename(path)

	@override
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
		pathname = ensure_absolute_path("/".join(path_list))
		return {
			"pathname": pathname,
			"hash": "",
			"query": "",
			"queryParams": {},
			"pathParams": {},
			"catchall": [],
		}


def filter_dev_routes(routes: Sequence[Route | Layout]) -> list[Route | Layout]:
	"""
	Filter out routes with dev=True.

	This function removes all routes marked with dev=True from the route tree.
	Should only be called when env != "dev".
	"""
	filtered: list[Route | Layout] = []
	for route in routes:
		# Skip dev-only routes
		if route.dev:
			continue

		# Recursively filter children
		if route.children:
			filtered_children = filter_dev_routes(route.children)
			# Create a copy of the route with filtered children
			if isinstance(route, Route):
				filtered_route = Route(
					path=route.path,
					render=route.render,
					children=filtered_children,
					components=route.components,
					dev=route.dev,
				)
			else:  # Layout
				filtered_route = Layout(
					render=route.render,
					children=filtered_children,
					components=route.components,
					dev=route.dev,
				)
			filtered.append(filtered_route)
		else:
			filtered.append(route)
	return filtered


class InvalidRouteError(Exception): ...


class RouteTree:
	tree: list[Route | Layout]
	flat_tree: dict[str, Route | Layout]

	def __init__(self, routes: Sequence[Route | Layout]) -> None:
		# Filter out dev routes when not in dev environment
		if env.pulse_env != "dev":
			routes = filter_dev_routes(routes)
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
		path = ensure_absolute_path(path)
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
	info: RouteInfo
	pulse_route: Route | Layout

	def __init__(self, info: RouteInfo, pulse_route: Route | Layout):
		self.info = cast(RouteInfo, cast(object, ReactiveDict(info)))
		self.pulse_route = pulse_route

	def update(self, info: RouteInfo):
		self.info.update(info)

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

	@override
	def __str__(self) -> str:
		return f"RouteContext(pathname='{self.pathname}', params={self.pathParams})"

	@override
	def __repr__(self) -> str:
		return (
			f"RouteContext(pathname='{self.pathname}', hash='{self.hash}', "
			f"query='{self.query}', queryParams={self.queryParams}, "
			f"pathParams={self.pathParams}, catchall={self.catchall})"
		)
