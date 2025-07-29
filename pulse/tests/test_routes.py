"""
Tests for the route definition system in pulse.html.

This module tests the system for defining routes with associated
React components and render functions.
"""

import pytest
from pulse.html import (
    define_route,
    define_react_component,
    get_registered_components,
    Route,
    div, h1, p, span
)


class TestRoute:
    """Test the Route class."""
    
    def test_route_creation(self):
        """Test creating Route instances."""
        def render_func():
            return div()["Test content"]
            
        components = []
        route = Route("/test", render_func, components)
        
        assert route.path == "/test"
        assert route.render_func == render_func
        assert route.components == components
        
    def test_route_with_components(self):
        """Test Route with associated components."""
        def render_func():
            return div()["Test content"]
            
        # Create some mock components
        from pulse.html import ReactComponent
        comp1 = ReactComponent("comp1", "./Comp1", "Comp1", False)
        comp2 = ReactComponent("comp2", "./Comp2", "Comp2", False)
        components = [comp1, comp2]
        
        route = Route("/test", render_func, components)
        
        assert len(route.components) == 2
        assert route.components[0].component_key == "comp1"
        assert route.components[1].component_key == "comp2"


class TestDefineRoute:
    """Test the define_route decorator function."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_define_route_basic(self):
        """Test defining a basic route without components."""
        self.setUp()
        
        @define_route("/test")
        def test_route():
            return div()["Test route content"]
        
        assert isinstance(test_route, Route)
        assert test_route.path == "/test"
        assert callable(test_route.render_func)
        assert test_route.components == []
        
        # Test calling the render function
        result = test_route.render_func()
        assert result.tag == "div"
        assert result.children == ["Test route content"]
        
    def test_define_route_with_components(self):
        """Test defining a route with specified components."""
        self.setUp()
        
        # Define some components first
        Button = define_react_component("button", "./Button", "Button", False)
        Card = define_react_component("card", "./Card", "Card", False)
        
        @define_route("/with-components", components=["button", "card"])
        def route_with_components():
            return div()[
                Card(title="Test Card")[
                    p()["Card content"],
                    Button()["Click me"]
                ]
            ]
        
        assert isinstance(route_with_components, Route)
        assert route_with_components.path == "/with-components"
        assert len(route_with_components.components) == 2
        
        # Check component details
        component_keys = [comp.component_key for comp in route_with_components.components]
        assert "button" in component_keys
        assert "card" in component_keys
        
    def test_define_route_with_nonexistent_components(self):
        """Test that defining route with nonexistent components raises error."""
        self.setUp()
        
        with pytest.raises(ValueError, match="Component 'nonexistent' not found"):
            @define_route("/bad-route", components=["nonexistent"])
            def bad_route():
                return div()["Bad route"]
                
    def test_define_route_empty_components_list(self):
        """Test defining route with empty components list."""
        self.setUp()
        
        @define_route("/empty-components", components=[])
        def empty_components_route():
            return div()["Empty components route"]
        
        assert isinstance(empty_components_route, Route)
        assert empty_components_route.components == []
        
    def test_define_route_none_components(self):
        """Test defining route with None components."""
        self.setUp()
        
        @define_route("/none-components", components=None)
        def none_components_route():
            return div()["None components route"]
        
        assert isinstance(none_components_route, Route)
        assert none_components_route.components == []


class TestRouteRendering:
    """Test route rendering functionality."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_simple_route_rendering(self):
        """Test rendering a simple route."""
        self.setUp()
        
        @define_route("/simple")
        def simple_route():
            return div(className="page")[
                h1()["Simple Page"],
                p()["This is a simple page with no React components."]
            ]
        
        result = simple_route.render_func()
        result_dict = result.to_dict()
        
        assert result_dict["tag"] == "div"
        assert result_dict["props"] == {"className": "page"}
        assert len(result_dict["children"]) == 2
        assert result_dict["children"][0]["tag"] == "h1"
        assert result_dict["children"][1]["tag"] == "p"
        
    def test_route_with_react_components(self):
        """Test rendering a route with React components."""
        self.setUp()
        
        Counter = define_react_component("counter", "./Counter", "Counter", False)
        UserCard = define_react_component("user-card", "./UserCard", "UserCard", False)
        
        @define_route("/with-react", components=["counter", "user-card"])
        def react_route():
            return div()[
                h1()["React Component Demo"],
                Counter(count=5, label="Demo Counter")[
                    "This counter has children"
                ],
                UserCard(name="John Doe", email="john@example.com")
            ]
        
        result = react_route.render_func()
        result_dict = result.to_dict()
        
        assert result_dict["tag"] == "div"
        assert len(result_dict["children"]) == 3
        
        # Check React components
        counter_child = result_dict["children"][1]
        assert counter_child["tag"] == "$$counter"
        assert counter_child["props"] == {"count": 5, "label": "Demo Counter"}
        assert counter_child["children"] == ["This counter has children"]
        
        user_card_child = result_dict["children"][2]
        assert user_card_child["tag"] == "$$user-card"
        assert user_card_child["props"] == {"name": "John Doe", "email": "john@example.com"}
        
    def test_route_with_dynamic_content(self):
        """Test route that generates dynamic content."""
        self.setUp()
        
        ListItem = define_react_component("list-item", "./ListItem", "ListItem", False)
        
        @define_route("/dynamic", components=["list-item"])
        def dynamic_route():
            items = ["Apple", "Banana", "Cherry"]
            return div()[
                h1()["Dynamic List"],
                *[ListItem(key=item, text=item) for item in items]
            ]
        
        result = dynamic_route.render_func()
        result_dict = result.to_dict()
        
        assert result_dict["tag"] == "div"
        assert len(result_dict["children"]) == 4  # h1 + 3 list items
        
        # Check dynamic list items
        for i in range(3):
            item_child = result_dict["children"][i + 1]
            assert item_child["tag"] == "$$list-item"
            assert "key" in item_child["props"]
            assert "text" in item_child["props"]


class TestRoutePathHandling:
    """Test route path handling and validation."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_root_path(self):
        """Test defining route with root path."""
        self.setUp()
        
        @define_route("/")
        def home_route():
            return div()["Home page"]
        
        assert home_route.path == "/"
        
    def test_nested_path(self):
        """Test defining route with nested path."""
        self.setUp()
        
        @define_route("/admin/users")
        def admin_users_route():
            return div()["Admin users page"]
        
        assert admin_users_route.path == "/admin/users"
        
    def test_path_with_params(self):
        """Test defining route with parameters (as string)."""
        self.setUp()
        
        @define_route("/users/:id")
        def user_detail_route():
            return div()["User detail page"]
        
        assert user_detail_route.path == "/users/:id"
        
    def test_path_with_special_characters(self):
        """Test paths with special characters."""
        self.setUp()
        
        @define_route("/api/v1/users")
        def api_route():
            return div()["API route"]
        
        assert api_route.path == "/api/v1/users"


class TestRouteComponentIntegration:
    """Test integration between routes and components."""
    
    def setUp(self):
        """Clear the component registry before each test."""
        if hasattr(define_react_component, '_components'):
            define_react_component._components.clear()
    
    def test_route_component_dependency_tracking(self):
        """Test that routes correctly track their component dependencies."""
        self.setUp()
        
        # Define components
        Header = define_react_component("header", "./Header", "Header", False)
        Footer = define_react_component("footer", "./Footer", "Footer", False)
        Sidebar = define_react_component("sidebar", "./Sidebar", "Sidebar", False)
        
        @define_route("/layout", components=["header", "footer", "sidebar"])
        def layout_route():
            return div()[
                Header(title="My App"),
                div(className="main")[
                    Sidebar(),
                    div(className="content")["Main content"]
                ],
                Footer()
            ]
        
        # Check that all components are tracked
        assert len(layout_route.components) == 3
        component_keys = [comp.component_key for comp in layout_route.components]
        assert set(component_keys) == {"header", "footer", "sidebar"}
        
    def test_unused_component_in_route(self):
        """Test route that lists components not actually used in rendering."""
        self.setUp()
        
        Button = define_react_component("button", "./Button", "Button", False)
        Modal = define_react_component("modal", "./Modal", "Modal", False)
        
        @define_route("/partial-use", components=["button", "modal"])
        def partial_use_route():
            # Only use button, not modal
            return div()[
                h1()["Partial Use"],
                Button()["Click me"],
                p()["Modal component not used here"]
            ]
        
        # Route should still track both components
        assert len(partial_use_route.components) == 2
        
        # But rendering should only create button mount point
        result = partial_use_route.render_func()
        result_dict = result.to_dict()
        
        # Find mount points in result
        mount_points = []
        def find_mount_points(node):
            if isinstance(node, dict) and node.get("tag", "").startswith("$$"):
                mount_points.append(node["tag"])
            if isinstance(node, dict) and "children" in node:
                for child in node["children"]:
                    find_mount_points(child)
        
        find_mount_points(result_dict)
        assert mount_points == ["$$button"]  # Only button used
        
    def test_component_order_preservation(self):
        """Test that component order is preserved in route definition."""
        self.setUp()
        
        A = define_react_component("a", "./A", "A", False)
        B = define_react_component("b", "./B", "B", False)
        C = define_react_component("c", "./C", "C", False)
        
        @define_route("/ordered", components=["c", "a", "b"])
        def ordered_route():
            return div()[A(), B(), C()]
        
        component_keys = [comp.component_key for comp in ordered_route.components]
        assert component_keys == ["c", "a", "b"]  # Order preserved


if __name__ == "__main__":
    pytest.main([__file__, "-v"])