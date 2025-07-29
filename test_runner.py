#!/usr/bin/env python3
"""
Simple test runner for Pulse UI without external dependencies.

This runner executes basic tests to verify the system works correctly.
"""

from pulse.html import (
    div,
    p,
    h1,
    span,
    img,
    br,
    define_react_component,
    define_route,
    get_registered_components,
)
from pulse.codegen import generate_route_with_registry, generate_routes_config


def test_basic_ui_tree_creation():
    """Test basic UI tree node creation."""
    node = div(className="container", id="main")
    assert node.tag == "div"
    assert node.props == {"className": "container", "id": "main"}
    assert node.children == []
    assert node.id.startswith("py_")


def test_ui_tree_with_children():
    """Test UI tree with children."""
    structure = div(className="page")[
        h1()["Page Title"],
        p()["First paragraph"],
        p()["Second paragraph with ", span()["nested span"], " content"],
    ]

    result = structure.to_dict()
    assert result["tag"] == "div"
    assert result["props"] == {"className": "page"}
    assert len(result["children"]) == 3
    assert result["children"][0]["tag"] == "h1"
    assert result["children"][0]["children"] == ["Page Title"]


def test_self_closing_tags():
    """Test self-closing tags."""
    node = br()
    assert node.tag == "br"
    assert node.children == []

    img_node = img(src="/test.jpg", alt="Test")
    assert img_node.tag == "img"
    assert img_node.props == {"src": "/test.jpg", "alt": "Test"}
    assert img_node.children == []


def test_react_component_definition():
    """Test React component definition."""
    # Clear registry
    if hasattr(define_react_component, "_components"):
        define_react_component._components.clear()

    Button = define_react_component("button", "./Button", "Button", False)

    # Component should be registered
    components = get_registered_components()
    assert "button" in components
    assert components["button"].component_key == "button"
    assert components["button"].import_path == "./Button"

    # Should create mount points
    mount_point = Button(variant="primary")["Click me"]
    assert mount_point.tag == "$$button"
    assert mount_point.props == {"variant": "primary"}
    assert mount_point.children == ["Click me"]


def test_route_definition():
    """Test route definition."""
    # Clear registry
    if hasattr(define_react_component, "_components"):
        define_react_component._components.clear()

    Counter = define_react_component("counter", "./Counter", "Counter", False)

    @define_route("/test", components=["counter"])
    def test_route():
        return div()[h1()["Test Route"], Counter(count=5)["Test counter"]]

    assert test_route.path == "/test"
    assert len(test_route.components) == 1
    assert test_route.components[0].component_key == "counter"

    # Test rendering
    result = test_route.render_func()
    result_dict = result.to_dict()
    assert result_dict["tag"] == "div"
    assert len(result_dict["children"]) == 2
    assert result_dict["children"][1]["tag"] == "$$counter"


def test_typescript_generation():
    """Test TypeScript code generation."""
    # Clear registry
    if hasattr(define_react_component, "_components"):
        define_react_component._components.clear()

    Button = define_react_component("button", "./Button", "Button", False)

    def render_func():
        return div()["Test content"]

    from pulse.html import Route, ReactComponent

    button_comp = ReactComponent("button", "./Button", "Button", False)
    route = Route("/test", render_func, [button_comp])

    initial_tree = {
        "id": "test",
        "tag": "div",
        "props": {},
        "children": ["Test content"],
    }

    result = generate_route_with_registry(route, initial_tree)

    # Check generated TypeScript
    assert 'import { Button } from "./Button";' in result
    assert '"button": Button,' in result
    assert "export default function RouteComponent()" in result
    assert "<ComponentRegistryProvider registry={componentRegistry}>" in result


def test_routes_config_generation():
    """Test routes configuration generation."""

    def render_func():
        return div()["Test"]

    from pulse.html import Route

    routes = [
        Route("/", render_func, []),
        Route("/about", render_func, []),
        Route("/contact", render_func, []),
    ]

    result = generate_routes_config(routes)

    assert 'index("routes/index.tsx"),' in result
    assert 'route("/about", "routes/about.tsx"),' in result
    assert 'route("/contact", "routes/contact.tsx"),' in result
    assert "satisfies RouteConfig;" in result


def test_complex_nested_structure():
    """Test complex nested structures with React components."""
    # Clear registry
    if hasattr(define_react_component, "_components"):
        define_react_component._components.clear()

    Card = define_react_component("card", "./Card", "Card", False)
    Button = define_react_component("button", "./Button", "Button", False)

    structure = div(className="app")[
        h1()["Complex Demo"],
        Card(title="Test Card", variant="primary")[
            p()["This is card content"],
            Button(variant="secondary")["Card Button"],
            div()["More content", Button()["Another Button"]],
        ],
    ]

    result = structure.to_dict()

    # Verify structure
    assert result["tag"] == "div"
    assert result["props"] == {"className": "app"}
    assert len(result["children"]) == 2

    # Find mount points
    mount_points = []

    def find_mount_points(node):
        if isinstance(node, dict) and node.get("tag", "").startswith("$$"):
            mount_points.append(node["tag"])
        if isinstance(node, dict) and "children" in node:
            for child in node["children"]:
                find_mount_points(child)

    find_mount_points(result)
    assert "$$card" in mount_points
    assert "$$button" in mount_points
    assert mount_points.count("$$button") == 2  # Two buttons
