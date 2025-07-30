"""
Tests for TypeScript code generation in pulse.codegen.

This module tests the system for generating TypeScript files
from Python route definitions and React components.
"""

import os
import tempfile
from pathlib import Path

import pytest

from pulse.codegen import (
    generate_route_with_registry,
    generate_routes_config,
    write_generated_files,
)
from pulse.nodes import (
    COMPONENT_REGISTRY,
    ReactComponent,
    div,
    h1,
    p,
)
from pulse.route import Route, route


class TestGenerateRouteWithRegistry:
    """Test the generate_route_with_registry function."""

    def test_route_with_no_components(self):
        """Test generating route with no components."""

        def render_func():
            return div()["Simple route"]

        route = Route("/simple", render_func, [])
        initial_tree = {
            "id": "test",
            "tag": "div",
            "props": {},
            "children": ["Simple route"],
        }

        result = generate_route_with_registry(route, initial_tree)

        # Check basic structure
        assert (
            'import { ReactiveUIContainer } from "~/pulse-lib/ReactiveUIContainer";'
            in result
        )
        assert (
            'import { ComponentRegistryProvider } from "~/pulse-lib/component-registry";'
            in result
        )
        assert 'import type { ComponentType } from "react";' in result

        # Check empty component registry
        assert "// No components needed for this route" in result
        assert (
            "const componentRegistry: Record<string, ComponentType<any>> = {};"
            in result
        )

        # Check UI tree inclusion
        assert '"id": "test"' in result
        assert '"tag": "div"' in result
        assert '"Simple route"' in result

        # Check React component structure
        assert "export default function RouteComponent()" in result
        assert "<ComponentRegistryProvider registry={componentRegistry}>" in result
        assert "<ReactiveUIContainer" in result
        assert "initialTree={initialTree}" in result

    def test_route_with_components(self):
        """Test generating route with React components."""
        # Create mock components
        button_comp = ReactComponent("button", "./Button", "Button", False)
        card_comp = ReactComponent("card", "./Card", "Card", False)

        def render_func():
            return div()["Route with components"]

        route = Route("/with-components", render_func, [button_comp, card_comp])
        initial_tree = {
            "id": "test",
            "tag": "div",
            "props": {},
            "children": ["Route with components"],
        }

        result = generate_route_with_registry(route, initial_tree)

        # Check component imports
        assert 'import { Button } from "./Button";' in result
        assert 'import { Card } from "./Card";' in result

        # Check component registry
        assert '"button": Button,' in result
        assert '"card": Card,' in result

        # Check no empty registry comment
        assert "No components needed for this route" not in result

    def test_route_with_default_export_components(self):
        """Test generating route with default export components."""
        default_comp = ReactComponent("default-comp", "./DefaultComp", "default", True)

        def render_func():
            return div()["Route with default export"]

        route = Route("/default-export", render_func, [default_comp])
        initial_tree = {"id": "test", "tag": "div", "props": {}, "children": []}

        result = generate_route_with_registry(route, initial_tree)

        # Check default import syntax
        assert 'import default from "./DefaultComp";' in result
        assert '"default-comp": default,' in result

    def test_complex_ui_tree_serialization(self):
        """Test serialization of complex UI tree structures."""

        def render_func():
            return div()["Complex structure"]

        route = Route("/complex", render_func, [])

        # Complex nested structure
        initial_tree = {
            "id": "root",
            "tag": "div",
            "props": {"className": "container"},
            "children": [
                {
                    "id": "header",
                    "tag": "h1",
                    "props": {"className": "title"},
                    "children": ["Page Title"],
                },
                {
                    "id": "content",
                    "tag": "div",
                    "props": {"className": "content"},
                    "children": [
                        "Text content",
                        {
                            "id": "button",
                            "tag": "button",
                            "props": {"onClick": "handleClick()"},
                            "children": ["Click me"],
                        },
                    ],
                },
            ],
        }

        result = generate_route_with_registry(route, initial_tree)

        # Check that complex structure is properly JSON serialized
        assert '"className": "container"' in result
        assert '"className": "title"' in result
        assert '"className": "content"' in result
        assert '"onClick": "handleClick()"' in result
        assert '"Click me"' in result


class TestGenerateRoutesConfig:
    """Test the generate_routes_config function."""

    def test_empty_routes_list(self):
        """Test generating config with empty routes list."""
        result = generate_routes_config([])

        # Should have empty array - check that there are no route entries between [ and ]
        import_line = (
            'import { type RouteConfig, index, route } from "@react-router/dev/routes";'
        )
        export_line = "export const routes = ["
        satisfies_line = "] satisfies RouteConfig;"

        expected = f"""{import_line}

{export_line}

{satisfies_line}"""

        assert result.strip() == expected.strip()

    def test_single_root_route(self):
        """Test generating config with single root route."""

        def render_func():
            return div()["Home"]

        home_route = Route("/", render_func, [])
        result = generate_routes_config([home_route])

        assert 'index("pulse/routes/index.tsx"),' in result

    def test_multiple_routes(self):
        """Test generating config with multiple routes."""

        def render_func():
            return div()["Test"]

        routes = [
            Route("/", render_func, []),
            Route("/about", render_func, []),
            Route("/contact", render_func, []),
            Route("/admin/users", render_func, []),
        ]

        result = generate_routes_config(routes)

        assert 'index("pulse/routes/index.tsx"),' in result
        assert 'route("/about", "pulse/routes/about.tsx"),' in result
        assert 'route("/contact", "pulse/routes/contact.tsx"),' in result
        assert 'route("/admin/users", "pulse/routes/admin_users.tsx"),' in result

    def test_route_path_to_filename_conversion(self):
        """Test conversion of route paths to safe filenames."""

        def render_func():
            return div()["Test"]

        routes = [
            Route("/api/v1/users", render_func, []),
            Route("/user-profile", render_func, []),
            Route("/admin/user-management", render_func, []),
        ]

        result = generate_routes_config(routes)

        assert 'route("/api/v1/users", "pulse/routes/api_v1_users.tsx"),' in result
        assert 'route("/user-profile", "pulse/routes/user_profile.tsx"),' in result
        assert (
            'route("/admin/user-management", "pulse/routes/admin_user_management.tsx"),'
            in result
        )


class TestWriteGeneratedFiles:
    """Test the write_generated_files function."""

    def setUp(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.clear()

    def test_write_files_to_temp_directory(self):
        """Test writing generated files to a temporary directory."""
        self.setUp()

        # Define components and routes
        Button = ReactComponent("button", "./Button", "Button", False)

        @route("/test", components=[Button])
        def test_route():
            return div()[h1()["Test Route"], Button()["Click me"]]

        routes = [test_route]

        # Use temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app", "pulse")
            write_generated_files(routes, app_dir)

            # Check that files were created
            routes_dir = Path(app_dir) / "routes"
            assert routes_dir.exists()
            assert (routes_dir / "test.tsx").exists()
            assert (Path(app_dir) / "routes.ts").exists()

            # Check route file content
            route_content = (routes_dir / "test.tsx").read_text()
            assert 'import { Button } from "./Button";' in route_content
            assert '"button": Button,' in route_content
            assert '"tag": "h1"' in route_content
            assert '"tag": "$$button"' in route_content

            # Check routes config
            config_content = (Path(app_dir) / "routes.ts").read_text()
            assert 'route("/test", "pulse/routes/test.tsx"),' in config_content

    def test_multiple_routes_file_generation(self):
        """Test generating files for multiple routes."""
        self.setUp()

        # Define routes
        @route("/")
        def home_route():
            return div()["Home Page"]

        @route("/about")
        def about_route():
            return div()["About Page"]

        routes = [home_route, about_route]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            routes_dir = Path(app_dir) / "routes"

            # Check both files exist
            assert (routes_dir / "index.tsx").exists()
            assert (routes_dir / "about.tsx").exists()

            # Check routes config has both
            config_content = (Path(app_dir) / "routes.ts").read_text()
            assert 'index("pulse/routes/index.tsx"),' in config_content
            assert 'route("/about", "pulse/routes/about.tsx"),' in config_content

    def test_route_with_complex_ui_tree(self):
        """Test generating files for route with complex UI structure."""
        self.setUp()

        Counter = ReactComponent("counter", "./Counter", "Counter", False)
        Card = ReactComponent("card", "./Card", "Card", False)

        @route("/complex", components=[Counter, Card])
        def complex_route():
            return div(className="app")[
                h1()["Complex Demo"],
                Card(title="Counter Card")[
                    p()["This card contains a counter:"],
                    Counter(count=42, label="Demo Counter")["Counter with children"],
                ],
            ]

        routes = [complex_route]

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            write_generated_files(routes, app_dir)

            route_content = (Path(app_dir) / "routes" / "complex.tsx").read_text()

            # Check component imports
            assert 'import { Counter } from "./Counter";' in route_content
            assert 'import { Card } from "./Card";' in route_content

            # Check component registry
            assert '"counter": Counter,' in route_content
            assert '"card": Card,' in route_content

            # Check UI tree structure
            assert '"className": "app"' in route_content
            assert '"tag": "$$card"' in route_content
            assert '"tag": "$$counter"' in route_content
            assert '"title": "Counter Card"' in route_content
            assert '"count": 42' in route_content
            assert '"label": "Demo Counter"' in route_content


class TestCodegenEdgeCases:
    """Test edge cases in code generation."""

    def test_component_with_special_characters_in_path(self):
        """Test component with special characters in import path."""
        special_comp = ReactComponent(
            "special", "./components/Special@Component", "SpecialComponent", False
        )

        def render_func():
            return div()["Special component route"]

        route = Route("/special", render_func, [special_comp])
        initial_tree = {"id": "test", "tag": "div", "props": {}, "children": []}

        result = generate_route_with_registry(route, initial_tree)

        # Should handle special characters in import path
        assert (
            'import { SpecialComponent } from "./components/Special@Component";'
            in result
        )
        assert '"special": SpecialComponent,' in result

    def test_empty_props_and_children(self):
        """Test handling of empty props and children in UI tree."""

        def render_func():
            return div()

        route = Route("/empty", render_func, [])
        initial_tree = {"id": "empty", "tag": "div", "props": {}, "children": []}

        result = generate_route_with_registry(route, initial_tree)

        # Should handle empty objects/arrays correctly
        assert '"props": {}' in result
        assert '"children": []' in result

    def test_json_serialization_safety(self):
        """Test that JSON serialization handles various data types safely."""

        def render_func():
            return div()["Test"]

        route = Route("/json-test", render_func, [])

        # UI tree with various data types
        initial_tree = {
            "id": "test",
            "tag": "div",
            "props": {
                "stringProp": "text",
                "numberProp": 42,
                "booleanProp": True,
                "nullProp": None,
                "arrayProp": [1, 2, 3],
                "objectProp": {"nested": "value"},
            },
            "children": ["text", 123, True, None],
        }

        result = generate_route_with_registry(route, initial_tree)

        # Check JSON serialization
        assert '"stringProp": "text"' in result
        assert '"numberProp": 42' in result
        assert '"booleanProp": true' in result  # JSON boolean
        assert '"nullProp": null' in result  # JSON null
        assert (
            '"arrayProp"' in result
            and "1" in result
            and "2" in result
            and "3" in result
        )
        assert '"objectProp"' in result and '"nested": "value"' in result

        # Children array should handle mixed types
        assert (
            "text" in result
            and "123" in result
            and "true" in result
            and "null" in result
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
