"""
Tests for React component integration in pulse.html.

This module tests the system for defining and using React components
within the UI tree generation system.
"""

import pytest
from pulse.html import (
    define_react_component,
    get_registered_components,
    ReactComponent,
    div, p, span, h1
)


class TestReactComponent:
    """Test the ReactComponent class."""
    
    def test_component_creation(self):
        """Test creating ReactComponent instances."""
        component = ReactComponent(
            component_key="test-component",
            import_path="./TestComponent", 
            export_name="TestComponent",
            is_default_export=False
        )
        
        assert component.component_key == "test-component"
        assert component.import_path == "./TestComponent"
        assert component.export_name == "TestComponent"
        assert component.is_default_export == False
        
    def test_component_with_default_export(self):
        """Test ReactComponent with default export."""
        component = ReactComponent(
            component_key="default-component",
            import_path="./DefaultComponent"
        )
        
        assert component.component_key == "default-component"
        assert component.import_path == "./DefaultComponent"
        assert component.export_name == "default"
        assert component.is_default_export == True


class TestDefineReactComponent:
    """Test the define_react_component function."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_define_component_basic(self):
        """Test defining a basic React component."""
        self.setUp()
        
        TestComponent = define_react_component(
            component_key="test",
            import_path="./TestComponent",
            export_name="TestComponent",
            is_default_export=False
        )
        
        # Should return a callable
        assert callable(TestComponent)
        
        # Component should be registered
        components = get_registered_components()
        assert "test" in components
        assert components["test"].component_key == "test"
        assert components["test"].import_path == "./TestComponent"
        assert components["test"].export_name == "TestComponent"
        assert components["test"].is_default_export == False
        
    def test_define_component_default_export(self):
        """Test defining a component with default export."""
        self.setUp()
        
        DefaultComponent = define_react_component(
            component_key="default-comp",
            import_path="./DefaultComponent"
        )
        
        components = get_registered_components()
        assert "default-comp" in components
        assert components["default-comp"].export_name == "default"
        assert components["default-comp"].is_default_export == True
        
    def test_component_mount_point_creation(self):
        """Test that defined components create mount points."""
        self.setUp()
        
        TestComponent = define_react_component(
            component_key="test-component",
            import_path="./TestComponent",
            export_name="TestComponent",
            is_default_export=False
        )
        
        # Create a mount point
        mount_point = TestComponent(prop1="value1", prop2="value2")
        
        assert mount_point.tag == "$$test-component"
        assert mount_point.props == {"prop1": "value1", "prop2": "value2"}
        assert mount_point.children == []
        
    def test_component_with_children(self):
        """Test creating mount points with children."""
        self.setUp()
        
        Container = define_react_component(
            component_key="container",
            import_path="./Container",
            export_name="Container",
            is_default_export=False
        )
        
        # Create mount point with children
        mount_point = Container(
            "Text child",
            p()["Paragraph child"],
            className="container"
        )
        
        assert mount_point.tag == "$$container"
        assert mount_point.props == {"className": "container"}
        assert len(mount_point.children) == 2
        assert mount_point.children[0] == "Text child"
        assert mount_point.children[1].tag == "p"
        
    def test_component_with_indexing_syntax(self):
        """Test using indexing syntax with React components."""
        self.setUp()
        
        Card = define_react_component(
            component_key="card",
            import_path="./Card",
            export_name="Card",
            is_default_export=False
        )
        
        # Use indexing syntax
        mount_point = Card(title="Test Card")[
            p()["Card content"],
            "Additional text"
        ]
        
        assert mount_point.tag == "$$card"
        assert mount_point.props == {"title": "Test Card"}
        assert len(mount_point.children) == 2
        assert mount_point.children[0].tag == "p"
        assert mount_point.children[1] == "Additional text"
        
    def test_multiple_components(self):
        """Test defining multiple components."""
        self.setUp()
        
        Button = define_react_component("button", "./Button", "Button", False)
        Input = define_react_component("input", "./Input", "Input", False)  
        Modal = define_react_component("modal", "./Modal", "Modal", False)
        
        components = get_registered_components()
        
        assert len(components) == 3
        assert "button" in components
        assert "input" in components
        assert "modal" in components
        
    def test_component_overwrite(self):
        """Test that defining a component with same key overwrites."""
        self.setUp()
        
        # Define first component
        define_react_component("test", "./First", "First", False)
        
        # Define second component with same key
        define_react_component("test", "./Second", "Second", False)
        
        components = get_registered_components()
        assert len(components) == 1
        assert components["test"].import_path == "./Second"
        assert components["test"].export_name == "Second"


class TestComponentRegistry:
    """Test the component registry functionality."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_empty_registry(self):
        """Test empty component registry."""
        self.setUp()
        
        components = get_registered_components()
        assert components == {}
        
    def test_registry_isolation(self):
        """Test that get_registered_components returns a copy."""
        self.setUp()
        
        define_react_component("test", "./Test", "Test", False)
        
        components1 = get_registered_components()
        components2 = get_registered_components()
        
        # Should be equal but not the same object
        assert components1 == components2
        assert components1 is not components2
        
        # Modifying one shouldn't affect the other
        components1["new"] = ReactComponent("new", "./New", "New", False)
        assert "new" not in components2


class TestMountPointGeneration:
    """Test mount point generation from React components."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_mount_point_tag_format(self):
        """Test that mount points have correct tag format."""
        self.setUp()
        
        TestComp = define_react_component("test-component", "./Test", "Test", False)
        
        mount_point = TestComp()
        assert mount_point.tag == "$$test-component"
        
    def test_mount_point_serialization(self):
        """Test that mount points serialize correctly."""
        self.setUp()
        
        Counter = define_react_component("counter", "./Counter", "Counter", False)
        
        mount_point = Counter(count=5, label="Test Counter")[
            p()["Counter description"],
            "Additional text"
        ]
        
        result = mount_point.to_dict()
        
        expected = {
            "id": mount_point.id,
            "tag": "$$counter",
            "props": {"count": 5, "label": "Test Counter"},
            "children": [
                {
                    "id": mount_point.children[0].id,
                    "tag": "p",
                    "props": {},
                    "children": ["Counter description"]
                },
                "Additional text"
            ]
        }
        
        assert result == expected
        
    def test_nested_mount_points(self):
        """Test nesting mount points within each other."""
        self.setUp()
        
        Card = define_react_component("card", "./Card", "Card", False)
        Button = define_react_component("button", "./Button", "Button", False)
        
        nested_structure = Card(title="Nested Example")[
            p()["This card contains a button:"],
            Button(variant="primary")["Click me!"],
            "And some additional text."
        ]
        
        result = nested_structure.to_dict()
        
        assert result["tag"] == "$$card"
        assert result["props"] == {"title": "Nested Example"}
        assert len(result["children"]) == 3
        
        # Check nested button
        button_child = result["children"][1]
        assert button_child["tag"] == "$$button"
        assert button_child["props"] == {"variant": "primary"}
        assert button_child["children"] == ["Click me!"]


class TestComponentIntegrationWithHTML:
    """Test integration of React components with regular HTML elements."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_mixed_html_and_components(self):
        """Test mixing HTML elements and React components."""
        self.setUp()
        
        UserCard = define_react_component("user-card", "./UserCard", "UserCard", False)
        Counter = define_react_component("counter", "./Counter", "Counter", False)
        
        mixed_structure = div(className="app")[
            h1()["My App"],
            UserCard(name="John Doe", email="john@example.com"),
            p()["Some regular HTML content"],
            Counter(count=42)[
                "This counter has children"
            ],
            div()[
                "More HTML content"
            ]
        ]
        
        result = mixed_structure.to_dict()
        
        assert result["tag"] == "div"
        assert result["props"] == {"className": "app"}
        assert len(result["children"]) == 5
        
        # Check structure
        assert result["children"][0]["tag"] == "h1"  # HTML
        assert result["children"][1]["tag"] == "$$user-card"  # React component
        assert result["children"][2]["tag"] == "p"  # HTML
        assert result["children"][3]["tag"] == "$$counter"  # React component
        assert result["children"][4]["tag"] == "div"  # HTML
        
    def test_component_props_types(self):
        """Test that component props handle various data types."""
        self.setUp()
        
        DataComponent = define_react_component("data", "./Data", "Data", False)
        
        mount_point = DataComponent(
            stringProp="text",
            numberProp=42,
            booleanProp=True,
            listProp=[1, 2, 3],
            dictProp={"key": "value"}
        )
        
        expected_props = {
            "stringProp": "text",
            "numberProp": 42,
            "booleanProp": True,
            "listProp": [1, 2, 3],
            "dictProp": {"key": "value"}
        }
        
        assert mount_point.props == expected_props


if __name__ == "__main__":
    pytest.main([__file__, "-v"])