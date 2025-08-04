import pytest

from pulse.component import component
from pulse.routing import (
    InvalidRouteError,
    PathParameters,
    PathSegment,
    Route,
    Layout,
    RouteTree,
)
from pulse.vdom import Node


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
    route = route_tree.find("|about")
    assert isinstance(route, Route)
    assert route.path == "about"
    assert route.parent.path == ""


def test_route_tree_find_layout(route_tree):
    layout = route_tree.find("<layout>")
    assert isinstance(layout, Layout)


def test_route_tree_find_route_in_layout(route_tree):
    route = route_tree.find("<layout>|dashboard")
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
