import pytest

from pulse.routing import (
    InvalidRouteError,
    PathParameters,
    PathSegment,
    Route,
    clear_routes,
    parse_route_path,
)
from pulse.vdom import Node


def mock_render() -> Node:
    return Node("div", {}, [])


@pytest.fixture(autouse=True)
def run_around_tests():
    # Before each test, clear the routes
    clear_routes()
    yield
    # After each test, clear them again
    clear_routes()


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


# --- parse_route_path Tests ---


def test_parse_route_path_simple():
    segments = parse_route_path("/users/profile")
    assert len(segments) == 2
    assert segments[0].name == "users"
    assert segments[1].name == "profile"


def test_parse_route_path_with_dynamic_segment():
    segments = parse_route_path("users/:id")
    assert len(segments) == 2
    assert segments[0].name == "users"
    assert segments[1].is_dynamic
    assert segments[1].name == "id"


def test_parse_route_path_handles_slashes():
    assert len(parse_route_path("users/profile")) == 2
    assert len(parse_route_path("/users/profile")) == 2
    assert len(parse_route_path("users/profile/")) == 2
    assert len(parse_route_path("/users/profile/")) == 2
    assert len(parse_route_path("/")) == 0
    assert len(parse_route_path("")) == 0


def test_parse_route_path_with_misplaced_splat():
    with pytest.raises(InvalidRouteError, match="can only be at the end"):
        parse_route_path("/assets/*/images")


# --- Route.match Tests ---


@pytest.mark.parametrize(
    "route_path,request_path,should_match",
    [
        # Static routes
        ("/", "/", True),
        ("/", "", True),
        ("", "/", True),
        ("", "", True),
        ("about", "/about", True),
        ("about", "/about/", True),
        ("about", "/about/us", False),
        ("about/us", "/about", False),
        # Dynamic segments
        ("users/:id", "/users/123", True),
        ("users/:id", "/users/abc", True),
        ("users/:id", "/users/", False),
        ("users/:id", "/users/123/profile", False),
        ("c/:catId/p/:prodId", "/c/electronics/p/456", True),
        # Optional segments
        ("users/:id/edit?", "/users/123/edit", True),
        ("users/:id/edit?", "/users/123", True),
        (":lang?/categories", "/en/categories", True),
        (":lang?/categories", "/categories", True),
        (":lang?/categories", "/fr/categories", True),
        (":lang?/categories", "/fr/other", False),
        # Splat routes
        ("files/*", "/files/image.jpg", True),
        ("files/*", "/files/docs/report.pdf", True),
        ("files/*", "/files/", True),
        ("files/*", "/files", True),
        ("assets/*", "/assets", True),
        ("assets/*", "/other", False),
    ],
)
def test_route_match_scenarios(route_path, request_path, should_match):
    route = Route(path=route_path, render_fn=mock_render, components=[])
    match_result = route.match(request_path)
    assert (match_result is not None) == should_match


@pytest.mark.parametrize(
    "route_path,request_path,expected_params,expected_splat",
    [
        # Static routes
        ("/", "/", {}, []),
        ("about", "/about", {}, []),
        # Dynamic segments
        ("users/:id", "/users/123", {"id": "123"}, []),
        (
            "c/:catId/p/:prodId",
            "/c/electronics/p/456",
            {"catId": "electronics", "prodId": "456"},
            [],
        ),
        # Optional segments
        ("users/:id/edit?", "/users/123/edit", {"id": "123"}, []),
        ("users/:id/edit?", "/users/123", {"id": "123"}, []),
        (":lang?/categories", "/en/categories", {"lang": "en"}, []),
        (":lang?/categories", "/categories", {}, []),
        # Splat routes
        ("files/*", "/files/image.jpg", {}, ["image.jpg"]),
        ("files/*", "/files/docs/report.pdf", {}, ["docs", "report.pdf"]),
        # Combinations
        (
            "project/:pid/files/*",
            "/project/abc/files/src/main.py",
            {"pid": "abc"},
            ["src", "main.py"],
        ),
    ],
)
def test_route_match_with_params(
    route_path, request_path, expected_params, expected_splat
):
    route = Route(path=route_path, render_fn=mock_render, components=[])
    match_result = route.match(request_path)
    assert match_result is not None
    assert match_result.params == expected_params
    assert match_result.splat == expected_splat


def test_route_match_nested():
    parent_route = Route(path="/users/:id", render_fn=mock_render, components=[])
    child_route = Route(
        path="profile", render_fn=mock_render, components=[], parent=parent_route
    )

    parent_match = parent_route.match("/users/123")
    assert parent_match is not None
    assert parent_match.params == {"id": "123"}

    assert parent_route.match("/users/123/profile") is None

    child_match = child_route.match("/users/123/profile")
    assert child_match is not None
    assert child_match.params == {"id": "123"}

    assert child_route.match("/users/123") is None


def test_route_match_nested_deeply():
    grandparent = Route(path="/a", render_fn=mock_render, components=[])
    parent = Route(path=":b", render_fn=mock_render, components=[], parent=grandparent)
    child = Route(path="c", render_fn=mock_render, components=[], parent=parent)

    match_result = child.match("/a/123/c")
    assert match_result is not None
    assert match_result.params == {"b": "123"}


def test_route_match_index_route():
    parent = Route(path="/dashboard", render_fn=mock_render, components=[])
    index_route = Route(path="", render_fn=mock_render, components=[], parent=parent)

    assert parent.match("/dashboard") is not None
    assert index_route.match("/dashboard") is not None
    assert index_route.match("/dashboard/settings") is None


def test_route_match_root_index_route():
    index_route = Route(path="", render_fn=mock_render, components=[])
    assert index_route.match("/") is not None
    assert index_route.match("") is not None
    assert index_route.match("/about") is None


# --- Route Initialization Tests ---


def test_route_init_child_of_index_is_invalid():
    parent = Route(path="/", render_fn=mock_render, components=[])
    with pytest.raises(ValueError, match="Index routes cannot have children."):
        Route(path="child", render_fn=mock_render, components=[], parent=parent)
