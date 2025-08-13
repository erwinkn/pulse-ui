"""
Tests for React component integration in pulse.html.

This module tests the system for defining and using React components
within the UI tree generation system.
"""

import pytest

from pulse.vdom import Node, VDOMNode, NodeTree
from pulse.components.registry import (
    COMPONENT_REGISTRY,
    ComponentRegistry,
    ReactComponent,
    Props,
    Prop,
)
from pulse.tests.test_utils import assert_node_equal


class TestReactComponent:
    """Test the ReactComponent class."""

    def test_component_creation(self):
        """Test creating ReactComponent instances."""
        component = ReactComponent(
            tag="TestComponent",
            import_path="./TestComponent",
            alias="test-component",
            is_default=False,
        )

        assert component.key == "test-component"
        assert component.import_path == "./TestComponent"
        assert component.tag == "TestComponent"
        assert not component.is_default

    def test_component_with_default_export(self):
        """Test ReactComponent with default export."""
        component = ReactComponent(
            tag="default-component",
            import_path="./DefaultComponent",
            is_default=True,
        )

        assert component.key == "default-component"
        assert component.import_path == "./DefaultComponent"
        # For default exports, the tag is the key, and the conceptual "export name" is "default"
        assert component.is_default


class TestDefineReactComponent:
    """Test the define_react_component function."""

    def setup_method(self):
        """Clear the component registry before each test."""
        # This is a bit of a hack to ensure a clean slate for tests,
        # as the global registry persists.
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_define_component_basic(self):
        """Test defining a basic React component."""
        TestComponent = ReactComponent(
            tag="TestComponent",
            import_path="./TestComponent",
            alias="test",
            is_default=False,
        )

        # Should return a callable
        assert callable(TestComponent)

        # Component should be registered
        components = COMPONENT_REGISTRY.get().items()
        assert "test" in components
        assert components["test"].tag == "TestComponent"
        assert components["test"].import_path == "./TestComponent"
        assert not components["test"].is_default

    def test_define_component_default_export(self):
        """Test defining a component with default export."""
        ReactComponent(
            tag="default-comp", import_path="./DefaultComponent", is_default=True
        )

        components = COMPONENT_REGISTRY.get().items()
        assert "default-comp" in components
        assert components["default-comp"].is_default

    def test_component_mount_point_creation(self):
        """Test that defined components create mount points."""
        TestComponent = ReactComponent(
            tag="TestComponent",
            import_path="./TestComponent",
            alias="test-component",
            is_default=False,
        )

        # Create a mount point
        mount_point = TestComponent(prop1="value1", prop2="value2")

        assert mount_point.tag == "$$test-component"
        assert mount_point.props == {"prop1": "value1", "prop2": "value2"}
        assert mount_point.children == []

    def test_component_with_children(self):
        """Test creating mount points with children."""
        Container = ReactComponent(
            tag="Container",
            import_path="./Container",
            alias="container",
            is_default=False,
        )

        # Create mount point with children
        mount_point = Container(
            "Text child", Node(tag="p")["Paragraph child"], className="container"
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
            tag="Card", import_path="./Card", alias="card", is_default=False
        )

        # Use indexing syntax
        mount_point = Card(title="Test Card")[
            Node(tag="p")["Card content"], "Additional text"
        ]

        assert mount_point.tag == "$$card"
        assert mount_point.props == {"title": "Test Card"}
        assert mount_point.children is not None
        assert len(mount_point.children) == 2
        p_child = mount_point.children[0]
        assert isinstance(p_child, Node) and p_child.tag == "p"
        assert mount_point.children[1] == "Additional text"

    def test_multiple_components(self):
        """Test defining multiple components."""
        ReactComponent("Button", "./Button", "button", False)
        ReactComponent("Input", "./Input", "input", False)
        ReactComponent("Modal", "./Modal", "modal", False)

        components = COMPONENT_REGISTRY.get().items()

        assert len(components) == 3
        assert "button" in components
        assert "input" in components
        assert "modal" in components

    def test_component_overwrite(self):
        """Test that defining a component with same key raises an error."""
        # Define first component
        ReactComponent("First", "./First", "test", False)

        # Define second component with same key
        with pytest.raises(ValueError):
            ReactComponent("Second", "./Second", "test", False)


class TestComponentRegistry:
    """Test the component registry functionality."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_empty_registry(self):
        """Test empty component registry."""
        components = COMPONENT_REGISTRY.get().items()
        assert components == {}

    def test_registry_isolation(self):
        """Test that get_registered_components returns a copy."""
        ReactComponent("Test", "./Test", "test", False)

        components1 = COMPONENT_REGISTRY.get().items()
        components2 = COMPONENT_REGISTRY.get().items()

        # Should be equal but not the same object
        assert components1 == components2
        assert components1 is not components2

        # Modifying one shouldn't affect the other
        components1["new"] = ReactComponent("New", "./New", "new", False)
        assert "new" not in components2


class TestMountPointGeneration:
    """Test mount point generation from React components."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_mount_point_tag_format(self):
        """Test that mount points have correct tag format."""
        TestComp = ReactComponent("Test", "./Test", "test-component", False)
        mount_point = TestComp()
        assert mount_point.tag == "$$test-component"

    def test_mount_point_serialization(self):
        """Test that mount points serialize correctly."""
        Counter = ReactComponent("Counter", "./Counter", "counter", False)

        mount_point = Counter(count=5, label="Test Counter")[
            Node(tag="p")["Counter description"], "Additional text"
        ]

        expected: VDOMNode = {
            "tag": "$$counter",
            "props": {"count": 5, "label": "Test Counter"},
            "children": [
                {
                    "tag": "p",
                    "props": {},
                    "children": ["Counter description"],
                },
                "Additional text",
            ],
        }

        assert_node_equal(mount_point, Node.from_vdom(expected))

    def test_nested_mount_points(self):
        """Test nesting mount points within each other."""
        Card = ReactComponent("Card", "./Card", "card", False)
        Button = ReactComponent("Button", "./Button", "button", False)

        nested_structure = Card(title="Nested Example")[
            Node(tag="p")["This card contains a button:"],
            Button(variant="primary")["Click me!"],
            "And some additional text.",
        ]

        expected: VDOMNode = {
            "tag": "$$card",
            "props": {"title": "Nested Example"},
            "children": [
                {"tag": "p", "props": {}, "children": ["This card contains a button:"]},
                {
                    "tag": "$$button",
                    "props": {"variant": "primary"},
                    "children": ["Click me!"],
                },
                "And some additional text.",
            ],
        }

        assert_node_equal(nested_structure, Node.from_vdom(expected))


class TestPropsSpecValidation:
    def setup_method(self):
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_unknown_prop_raises(self):
        Comp = ReactComponent(
            tag="X",
            import_path="./X",
            alias="x",
            props=Props({"a": int}),
        )
        with pytest.raises(ValueError):
            Comp(b=1)

    def test_missing_required_raises(self):
        Comp = ReactComponent(
            tag="X",
            import_path="./X",
            alias="x",
            props=Props({"a": int}, total=True),
        )
        with pytest.raises(ValueError):
            Comp()

    def test_type_mismatch_raises(self):
        Comp = ReactComponent(
            tag="X",
            import_path="./X",
            alias="x",
            props=Props({"a": int}),
        )
        with pytest.raises(TypeError):
            Comp(a="not-int")

    def test_default_and_factory_and_serializer(self):
        Comp = ReactComponent(
            tag="X",
            import_path="./X",
            alias="x",
            props=Props(
                {
                    "a": Prop(int, default=5),
                    "b": Prop(dict, default_factory=dict),
                    "c": Prop(str, serialize=lambda s: s.upper()),
                }
            ),
        )
        node = Comp(c="hi")
        assert node.props == {"a": 5, "b": {}, "c": "HI"}

    def test_key_extracted(self):
        Comp = ReactComponent(
            tag="X",
            import_path="./X",
            alias="x",
            props=Props({}),
        )
        node = Comp(key="k1")
        assert node.key == "k1"
        assert node.props == {}


class TestHintValidation:
    def setup_method(self):
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_valid_hint_with_children(self):
        def hint(*children: NodeTree, key: None | str = None, **props) -> NodeTree:
            return None

        ReactComponent(
            tag="H",
            import_path="./H",
            alias="h",
            hint=hint,
        )

    def test_valid_hint_no_children(self):
        def hint(key: None | str = None, **props) -> NodeTree:
            return None

        ReactComponent(
            tag="H",
            import_path="./H",
            alias="h",
            hint=hint,
        )

    def test_hint_missing_key_raises(self):
        def hint(*children: NodeTree, **props) -> NodeTree:
            return None

        with pytest.raises(ValueError):
            ReactComponent(
                tag="H",
                import_path="./H",
                alias="h",
                hint=hint,
            )

    def test_hint_key_default_not_none_raises(self):
        def hint(*children: NodeTree, key: str = "x", **props) -> NodeTree:
            return None

        with pytest.raises(ValueError):
            ReactComponent(
                tag="H",
                import_path="./H",
                alias="h",
                hint=hint,
            )

    def test_hint_children_wrong_annotation_raises(self):
        def hint(*children: int, key: None | str = None, **props) -> NodeTree:
            return None

        with pytest.raises(TypeError):
            ReactComponent(
                tag="H",
                import_path="./H",
                alias="h",
                hint=hint,
            )

    def test_hint_fixed_positional_raises(self):
        def hint(x, key: None | str = None, **props) -> NodeTree:
            return None

        with pytest.raises(ValueError):
            ReactComponent(
                tag="H",
                import_path="./H",
                alias="h",
                hint=hint,
            )


class TestComponentIntegrationWithHTML:
    """Test integration of React components with regular HTML elements."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_mixed_html_and_components(self):
        """Test mixing HTML elements and React components."""
        UserCard = ReactComponent("UserCard", "./UserCard", "user-card", False)
        Counter = ReactComponent("Counter", "./Counter", "counter", False)

        mixed_structure = Node(tag="div", props={"className": "app"})[
            Node(tag="h1")["My App"],
            UserCard(name="John Doe", email="john@example.com"),
            Node(tag="p")["Some regular HTML content"],
            Counter(count=42)["This counter has children"],
            Node(tag="div")["More HTML content"],
        ]

        expected: VDOMNode = {
            "tag": "div",
            "props": {"className": "app"},
            "children": [
                {"tag": "h1", "props": {}, "children": ["My App"]},
                {
                    "tag": "$$user-card",
                    "props": {"name": "John Doe", "email": "john@example.com"},
                    "children": None,
                },
                {"tag": "p", "props": {}, "children": ["Some regular HTML content"]},
                {
                    "tag": "$$counter",
                    "props": {"count": 42},
                    "children": ["This counter has children"],
                },
                {"tag": "div", "props": {}, "children": ["More HTML content"]},
            ],
        }

        assert_node_equal(mixed_structure, Node.from_vdom(expected))

    def test_component_props_types(self):
        """Test that component props handle various data types."""
        DataComponent = ReactComponent("Data", "./Data", "data", False)

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
