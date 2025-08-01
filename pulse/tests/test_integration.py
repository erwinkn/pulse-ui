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
    generate_config_file,
    generate_route_page,
    generate_routes_config,
)
from pulse.vdom import (
    COMPONENT_REGISTRY,
    ReactComponent,
    VDOMNode,
    div,
    h1,
    p,
)


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

        assert 'import { Pulse, type PulseInit, type ComponentRegistry } from "~/pulse-lib/pulse";' in result
        assert 'import { SocketIOTransport } from "~/pulse-lib/transport";' in result
        assert 'import { config } from "../config";' in result
        assert "// No components needed for this route" in result
        assert "const externalComponents: ComponentRegistry = {};" in result
        assert '"tag": "div"' in result
        assert '"Simple route"' in result
        assert "export default function RouteComponent()" in result
        assert "<Pulse {...pulseInit} config={config} />" in result

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

        assert 'import { Button } from "./Button";' in result
        assert 'import { Card } from "./Card";' in result
        assert '"button": Button,' in result
        assert '"card": Card,' in result
        assert "No components needed for this route" not in result

    def test_route_with_default_export_components(self):
        """Test generating route with default export components."""
        default_comp = ReactComponent("default-comp", "./DefaultComp", "default", True)

        def render_func():
            return div()["Route with default export"]

        route = Route("/default-export", render_func, [default_comp])
        initial_tree: VDOMNode = {"tag": "div", "props": {}, "children": []}

        result = generate_route_page(route, initial_tree, "~/pulse-lib")

        assert 'import default from "./DefaultComp";' in result
        assert '"default-comp": default,' in result


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
        assert 'route("/about", "pulse/routes/about.tsx"),' in result


class TestGenerateConfigFile:
    """Test the generate_config_file function."""

    def test_generate_config(self):
        """Test generating the config file."""
        result = generate_config_file(
            host="127.0.0.1", port=8080, pulse_lib_path="~/lib"
        )
        assert 'serverAddress: "127.0.0.1",' in result
        assert "serverPort: 8080," in result
        assert 'import type { PulseConfig } from "~/lib/pulse";' in result


class TestGenerateAllRoutes:
    """Test the generate_all_routes function."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.clear()

    def test_full_app_generation(self):
        """Test generating all files for a simple app."""
        Header = ReactComponent("header", "./components/Header", "Header", False)
        Footer = ReactComponent("footer", "./components/Footer", "Footer", False)
        Button = ReactComponent("button", "./components/Button", "Button", False)

        app = App()

        @app.route("/", components=[Header, Footer])
        def home_route():
            return div()[Header(title="Home"), Footer(year=2024)]

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

            assert (pulse_app_dir / "config.ts").exists()
            assert (pulse_app_dir / "routes.ts").exists()
            assert (routes_dir / "index.tsx").exists()
            assert (routes_dir / "interactive.tsx").exists()

            config_content = (pulse_app_dir / "config.ts").read_text()
            assert (
                'import type { PulseConfig } from "~/test-lib/pulse";' in config_content
            )
            assert 'serverAddress: "testhost",' in config_content
            assert "serverPort: 1234," in config_content

            routes_ts_content = (pulse_app_dir / "routes.ts").read_text()
            assert 'index("test_pulse_app/routes/index.tsx"),' in routes_ts_content
            assert (
                'route("/interactive", "test_pulse_app/routes/interactive.tsx"),'
                in routes_ts_content
            )

            home_content = (routes_dir / "index.tsx").read_text()
            assert (
                'import { Pulse, type PulseInit, type ComponentRegistry } from "~/test-lib/pulse";'
                in home_content
            )
            assert 'import { Header } from "./components/Header";' in home_content
            assert '"header": Header,' in home_content
            assert '"tag": "$$header"' in home_content

            interactive_content = (routes_dir / "interactive.tsx").read_text()
            assert (
                'import { Button } from "./components/Button";' in interactive_content
            )
            assert '"button": Button,' in interactive_content
            assert '"tag": "$$button"' in interactive_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
