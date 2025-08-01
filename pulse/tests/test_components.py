"""
Tests for React component integration in pulse.html.

This module tests the system for defining and using React components
within the UI tree generation system.
"""

import pytest

from pulse.vdom import (
    COMPONENT_REGISTRY,
    ReactComponent,
    Node,
    VDOMNode,
    react_component_registry,
    div,
    p,
    h1,
)
from pulse.tests.test_utils import assert_node_renders_to


class TestReactComponent:
    """Test the ReactComponent class."""

    def test_component_creation(self):
        """Test creating ReactComponent instances."""
        component = ReactComponent(
            component_key="test-component",
            import_path="./TestComponent",
            export_name="TestComponent",
            is_default_export=False,
        )

        assert component.component_key == "test-component"
        assert component.import_path == "./TestComponent"
        assert component.export_name == "TestComponent"
        assert not component.is_default_export

    def test_component_with_default_export(self):
        """Test ReactComponent with default export."""
        component = ReactComponent(
            component_key="default-component", import_path="./DefaultComponent"
        )

        assert component.component_key == "default-component"
        assert component.import_path == "./DefaultComponent"
        assert component.export_name == "default"
        assert component.is_default_export


class TestDefineReactComponent:
    """Test the define_react_component function."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.clear()

    def test_define_component_basic(self):
        """Test defining a basic React component."""
        TestComponent = ReactComponent(
            component_key="test",
            import_path="./TestComponent",
            export_name="TestComponent",
            is_default_export=False,
        )

        # Should return a callable
        assert callable(TestComponent)

        # Component should be registered
        components = react_component_registry()
        assert "test" in components
        assert components["test"].component_key == "test"
        assert components["test"].import_path == "./TestComponent"
        assert components["test"].export_name == "TestComponent"
        assert not components["test"].is_default_export

    def test_define_component_default_export(self):
        """Test defining a component with default export."""
        ReactComponent(component_key="default-comp", import_path="./DefaultComponent")

        components = react_component_registry()
        assert "default-comp" in components
        assert components["default-comp"].export_name == "default"
        assert components["default-comp"].is_default_export

    def test_component_mount_point_creation(self):
        """Test that defined components create mount points."""
        TestComponent = ReactComponent(
            component_key="test-component",
            import_path="./TestComponent",
            export_name="TestComponent",
            is_default_export=False,
        )

        # Create a mount point
        mount_point = TestComponent(prop1="value1", prop2="value2")

        assert mount_point.tag == "$$test-component"
        assert mount_point.props == {"prop1": "value1", "prop2": "value2"}
        assert mount_point.children == []

    def test_component_with_children(self):
        """Test creating mount points with children."""
        Container = ReactComponent(
            component_key="container",
            import_path="./Container",
            export_name="Container",
            is_default_export=False,
        )

        # Create mount point with children
        mount_point = Container(
            "Text child", p()["Paragraph child"], className="container"
        )

        assert mount_point.tag == "$$container"
        assert mount_point.props == {"className": "container"}
        assert mount_point.children is not None
        assert len(mount_point.children) == 2
        assert mount_point.children[0] == "Text child"
        p_child = mount_point.children[1]
        assert isinstance(p_child, Node) and p_child.tag == "p"

    def test_component_with_indexing_syntax(self):
        """Test using indexing syntax with React components."""
        Card = ReactComponent(
            component_key="card",
            import_path="./Card",
            export_name="Card",
            is_default_export=False,
        )

        # Use indexing syntax
        mount_point = Card(title="Test Card")[p()["Card content"], "Additional text"]

        assert mount_point.tag == "$$card"
        assert mount_point.props == {"title": "Test Card"}
        assert mount_point.children is not None
        assert len(mount_point.children) == 2
        p_child = mount_point.children[0]
        assert isinstance(p_child, Node) and p_child.tag == "p"
        assert mount_point.children[1] == "Additional text"

    def test_multiple_components(self):
        """Test defining multiple components."""
        ReactComponent("button", "./Button", "Button", False)
        ReactComponent("input", "./Input", "Input", False)
        ReactComponent("modal", "./Modal", "Modal", False)

        components = react_component_registry()

        assert len(components) == 3
        assert "button" in components
        assert "input" in components
        assert "modal" in components

    def test_component_overwrite(self):
        """Test that defining a component with same key raises an error."""
        # Define first component
        ReactComponent("test", "./First", "First", False)

        # Define second component with same key
        with pytest.raises(ValueError):
            ReactComponent("test", "./Second", "Second", False)


class TestComponentRegistry:
    """Test the component registry functionality."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.clear()

    def test_empty_registry(self):
        """Test empty component registry."""
        components = react_component_registry()
        assert components == {}

    def test_registry_isolation(self):
        """Test that get_registered_components returns a copy."""
        ReactComponent("test", "./Test", "Test", False)

        components1 = react_component_registry()
        components2 = react_component_registry()

        # Should be equal but not the same object
        assert components1 == components2
        assert components1 is not components2

        # Modifying one shouldn't affect the other
        components1["new"] = ReactComponent("new", "./New", "New", False)
        assert "new" not in components2


class TestMountPointGeneration:
    """Test mount point generation from React components."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.clear()

    def test_mount_point_tag_format(self):
        """Test that mount points have correct tag format."""
        TestComp = ReactComponent("test-component", "./Test", "Test", False)
        mount_point = TestComp()
        assert mount_point.tag == "$$test-component"

    def test_mount_point_serialization(self):
        """Test that mount points serialize correctly."""
        Counter = ReactComponent("counter", "./Counter", "Counter", False)

        mount_point = Counter(count=5, label="Test Counter")[
            p()["Counter description"], "Additional text"
        ]

        expected: VDOMNode = {
            "tag": "$$counter",
            "props": {"count": 5, "label": "Test Counter"},
            "children": [
                {
                    "tag": "p",
                    "children": ["Counter description"],
                },
                "Additional text",
            ],
        }

        assert_node_renders_to(mount_point, expected)

    def test_nested_mount_points(self):
        """Test nesting mount points within each other."""
        Card = ReactComponent("card", "./Card", "Card", False)
        Button = ReactComponent("button", "./Button", "Button", False)

        nested_structure = Card(title="Nested Example")[
            p()["This card contains a button:"],
            Button(variant="primary")["Click me!"],
            "And some additional text.",
        ]

        expected: VDOMNode = {
            "tag": "$$card",
            "props": {"title": "Nested Example"},
            "children": [
                {"tag": "p", "children": ["This card contains a button:"]},
                {
                    "tag": "$$button",
                    "props": {"variant": "primary"},
                    "children": ["Click me!"],
                },
                "And some additional text.",
            ],
        }

        assert_node_renders_to(nested_structure, expected)


class TestComponentIntegrationWithHTML:
    """Test integration of React components with regular HTML elements."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.clear()

    def test_mixed_html_and_components(self):
        """Test mixing HTML elements and React components."""
        UserCard = ReactComponent("user-card", "./UserCard", "UserCard", False)
        Counter = ReactComponent("counter", "./Counter", "Counter", False)

        mixed_structure = div(className="app")[
            h1()["My App"],
            UserCard(name="John Doe", email="john@example.com"),
            p()["Some regular HTML content"],
            Counter(count=42)["This counter has children"],
            div()["More HTML content"],
        ]

        expected: VDOMNode = {
            "tag": "div",
            "props": {"className": "app"},
            "children": [
                {"tag": "h1", "children": ["My App"]},
                {
                    "tag": "$$user-card",
                    "props": {"name": "John Doe", "email": "john@example.com"},
                },
                {"tag": "p", "children": ["Some regular HTML content"]},
                {
                    "tag": "$$counter",
                    "props": {"count": 42},
                    "children": ["This counter has children"],
                },
                {"tag": "div", "children": ["More HTML content"]},
            ],
        }

        assert_node_renders_to(mixed_structure, expected)

    def test_component_props_types(self):
        """Test that component props handle various data types."""
        DataComponent = ReactComponent("data", "./Data", "Data", False)

        mount_point = DataComponent(
            stringProp="text",
            numberProp=42,
            booleanProp=True,
            listProp=[1, 2, 3],
            dictProp={"key": "value"},
        )

        expected_props = {
            "stringProp": "text",
            "numberProp": 42,
            "booleanProp": True,
            "listProp": [1, 2, 3],
            "dictProp": {"key": "value"},
        }

        assert mount_point.props == expected_props


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
