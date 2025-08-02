"""
Integration tests for the complete Pulse UI system.

This module tests the full pipeline from Python UI tree definition
through TypeScript code generation and React component integration.
"""

import tempfile
from pathlib import Path

import pytest

from pulse.app import App, Route
from pulse.codegen import (
    CodegenConfig,
    generate_all_routes,
    generate_route_page,
    generate_routes_config,
)
from pulse.components.registry import ReactComponent, COMPONENT_REGISTRY
from pulse.vdom import (
    VDOMNode,
    div,
    h1,
    p,
)
from pulse.components import Outlet


class TestGenerateRoutePage:
    """Test the generate_route_page function."""

    def test_route_with_no_components(self):
        """Test generating route with no components."""

        def render_func():
            return div()["Simple route"]

        route = Route("/simple", render_func, [])
        initial_tree: VDOMNode = {
            "tag": "div",
            "props": {},
            "children": ["Simple route"],
        }

        result = generate_route_page(route, initial_tree, "~/pulse-lib")

        assert 'import { PulseView } from "~/pulse-lib/pulse";' in result
        assert (
            'import type { VDOM, ComponentRegistry } from "~/pulse-lib/vdom";' in result
        )
        assert "// No components needed for this route" in result
        assert "const externalComponents: ComponentRegistry = {};" in result
        assert '"tag": "div"' in result
        assert '"Simple route"' in result
        assert "export default function RouteComponent()" in result
        assert "<PulseView" in result

    def test_route_with_components(self):
        """Test generating route with React components."""
        button_comp = ReactComponent("button", "./Button", "Button", False)
        card_comp = ReactComponent("card", "./Card", "Card", False)

        def render_func():
            return div()["Route with components"]

        route = Route("/with-components", render_func, [button_comp, card_comp])
        initial_tree: VDOMNode = {
            "tag": "div",
            "props": {},
            "children": ["Route with components"],
        }

        result = generate_route_page(route, initial_tree, "~/pulse-lib")

        assert 'import { button as Button } from "./Button";' in result
        assert 'import { card as Card } from "./Card";' in result
        assert '"Button": Button,' in result
        assert '"Card": Card,' in result
        assert "No components needed for this route" not in result

    def test_route_with_default_export_components(self):
        """Test generating route with default export components."""
        default_comp = ReactComponent("DefaultComp", "./DefaultComp", is_default=True)

        def render_func():
            return div()["Route with default export"]

        route = Route("/default-export", render_func, [default_comp])
        initial_tree: VDOMNode = {"tag": "div", "props": {}, "children": []}

        result = generate_route_page(route, initial_tree, "~/pulse-lib")

        assert 'import DefaultComp from "./DefaultComp";' in result
        assert '"DefaultComp": DefaultComp,' in result


class TestGenerateRoutesConfig:
    """Test the generate_routes_config function."""

    def test_empty_routes_list(self):
        """Test generating config with empty routes list."""
        result = generate_routes_config([], "pulse")
        assert "export const routes = [" in result
        assert "] satisfies RouteConfig;" in result

    def test_single_root_route(self):
        """Test generating config with single root route."""
        home_route = Route("/", lambda: div(), [])
        result = generate_routes_config([home_route], "pulse")
        assert 'index("pulse/routes/index.tsx"),' in result

    def test_multiple_routes(self):
        """Test generating config with multiple routes."""
        routes = [
            Route("/", lambda: div(), []),
            Route("/about", lambda: div(), []),
        ]
        result = generate_routes_config(routes, "pulse")
        assert 'index("pulse/routes/index.tsx"),' in result
        assert 'route("about", "pulse/routes/about.tsx")' in result


class TestGenerateAllRoutes:
    """Test the generate_all_routes function."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.get().clear()

    def test_full_app_generation(self):
        """Test generating all files for a simple app."""
        Header = ReactComponent("Header", "./components/Header")
        Footer = ReactComponent("Footer", "./components/Footer")
        Button = ReactComponent("Button", "./components/Button")

        app = App()

        @app.route("/", components=[Header, Footer])
        def home_route():
            return div()[Header(title="Home"), Footer(year=2024)]

        @app.route("/users", components=[])
        def users_page():
            return div()["Users Layout", Outlet()]

        @app.route(":id", components=[], parent=users_page)
        def user_details():
            return div()["User Details"]

        @app.route("/interactive", components=[Button])
        def interactive_route():
            return div()[Button(variant="primary")]

        with tempfile.TemporaryDirectory() as temp_dir:
            codegen_config = CodegenConfig(
                web_dir=temp_dir,
                pulse_app_name="test_pulse_app",
                pulse_lib_path="~/test-lib",
            )
            app.codegen = codegen_config

            generate_all_routes(app, host="testhost", port=1234)

            pulse_app_dir = Path(codegen_config.pulse_app_dir)
            routes_dir = pulse_app_dir / "routes"

            assert (pulse_app_dir / "layout.tsx").exists()
            assert (pulse_app_dir / "routes.ts").exists()
            assert (routes_dir / "index.tsx").exists()
            assert (routes_dir / "interactive.tsx").exists()
            assert (routes_dir / "users.tsx").exists()
            assert (routes_dir / "users_param_id.tsx").exists()

            layout_content = (pulse_app_dir / "layout.tsx").read_text()
            assert (
                'import { PulseProvider, type PulseConfig } from "~/test-lib/pulse";'
                in layout_content
            )
            assert 'serverAddress: "testhost",' in layout_content
            assert "serverPort: 1234," in layout_content

            routes_ts_content = (pulse_app_dir / "routes.ts").read_text()
            assert (
                'route("interactive", "test_pulse_app/routes/interactive.tsx")'
                in routes_ts_content
            )
            assert (
                'route("users", "test_pulse_app/routes/users.tsx", ['
                in routes_ts_content
            )
            assert (
                'route(":id", "test_pulse_app/routes/users_param_id.tsx")'
                in routes_ts_content
            )

            home_content = (routes_dir / "index.tsx").read_text()
            assert 'import { PulseView } from "~/test-lib/pulse";' in home_content
            assert 'import { Header } from "./components/Header";' in home_content
            assert '"Header": Header,' in home_content
            assert '"tag": "$$Header"' in home_content

            interactive_content = (routes_dir / "interactive.tsx").read_text()
            assert (
                'import { Button } from "./components/Button";' in interactive_content
            )
            assert '"Header": Header,' not in interactive_content
            assert '"Button": Button,' in interactive_content
            assert '"tag": "$$Button"' in interactive_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
