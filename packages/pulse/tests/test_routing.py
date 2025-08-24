import pytest

from pulse.routing import (
    InvalidRouteError,
    PathSegment,
    Route,
    Layout,
    RouteTree,
)
import pulse as ps
from pulse.vdom import Node, component


# --- PathSegment Tests ---


def test_path_segment_static():
    segment = PathSegment("users")
    assert segment.name == "users"
    assert not segment.is_dynamic
    assert not segment.is_optional
    assert not segment.is_splat


def test_path_segment_dynamic():
    segment = PathSegment(":userId")
    assert segment.name == "userId"
    assert segment.is_dynamic
    assert not segment.is_optional
    assert not segment.is_splat


def test_path_segment_optional_static():
    segment = PathSegment("edit?")
    assert segment.name == "edit"
    assert not segment.is_dynamic
    assert segment.is_optional
    assert not segment.is_splat


def test_path_segment_optional_dynamic():
    segment = PathSegment(":lang?")
    assert segment.name == "lang"
    assert segment.is_dynamic
    assert segment.is_optional
    assert not segment.is_splat


def test_path_segment_splat():
    segment = PathSegment("*")
    assert segment.name == "*"
    assert not segment.is_dynamic
    assert not segment.is_optional
    assert segment.is_splat


def test_path_segment_invalid_characters():
    with pytest.raises(InvalidRouteError, match="contains invalid characters"):
        PathSegment("user^")  # '^' is not a valid segment char unless sub-delimiter


def test_path_segment_empty():
    with pytest.raises(InvalidRouteError, match="cannot be empty"):
        PathSegment("")


# --- RouteTree Tests ---


@component
def DummyComponent():
    return Node(tag="div")


@pytest.fixture
def route_tree():
    """Provides a sample RouteTree for testing."""
    return RouteTree(
        [
            Route(
                path="/",
                render=DummyComponent,
                children=[Route(path="about", render=DummyComponent)],
            ),
            Layout(
                render=DummyComponent,
                children=[Route(path="dashboard", render=DummyComponent)],
            ),
            Route(path="users", render=DummyComponent),
        ]
    )


def test_route_tree_find_root(route_tree):
    route = route_tree.find("")
    assert isinstance(route, Route)
    assert route.path == ""


def test_route_tree_find_nested_route(route_tree):
    route = route_tree.find("about")
    assert isinstance(route, Route)
    assert route.path == "about"
    assert isinstance(route.parent, Route)
    assert route.parent.path == ""


def test_route_tree_find_layout(route_tree):
    layout = route_tree.find("<layout>")
    assert isinstance(layout, Layout)


def test_route_tree_find_route_in_layout(route_tree):
    route = route_tree.find("dashboard")
    assert isinstance(route, Route)
    assert route.path == "dashboard"
    assert isinstance(route.parent, Layout)


def test_route_tree_find_top_level_route(route_tree):
    route = route_tree.find("users")
    assert isinstance(route, Route)
    assert route.path == "users"


def test_route_tree_find_non_existent(route_tree):
    with pytest.raises(ValueError, match="No route found for path 'nonexistent'"):
        route_tree.find("nonexistent")


def test_route_tree_find_non_existent_in_layout(route_tree):
    with pytest.raises(
        ValueError, match="No route found for path '<layout>|nonexistent'"
    ):
        route_tree.find("<layout>|nonexistent")


def test_route_tree_consecutive_layouts():
    def render():
        return ps.div()

    route_tree = RouteTree(
        [
            Layout(render, [Route("counter", render)]),
            Layout(render, [Route("/counter-2", render)]),
        ]
    )
    route = route_tree.find("counter-2")
    assert isinstance(route, Route) and route.path == "counter-2"


def test_route_tree_nested_layouts():
    def render():
        return ps.div()

    route_tree = RouteTree(
        [
            Layout(render, [Route("/counter-2", render)]),
            Layout(render, [Layout(render, [Route("/counter", render)])]),
        ]
    )
    route = route_tree.find("counter")
    assert isinstance(route, Route) and route.path == "counter"
    # This gets the two layouts
    paths = [route.unique_path() for route in route_tree.tree]
    assert paths == ["<layout>", "<layout>2"]
