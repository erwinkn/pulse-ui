"""
Integration tests for the complete Pulse UI system.

This module tests the full pipeline from Python UI tree definition
through TypeScript code generation and React component integration.
"""

from pathlib import Path

import pytest

from pulse.app import App
from pulse.codegen import Codegen, CodegenConfig
from pulse.components import Outlet
import pulse as ps
from pulse.react_component import COMPONENT_REGISTRY, ReactComponent
from pulse.routing import RouteTree, Route
from pulse import div


SERVER_ADDRESS = "http://localhost:8000"


class TestCodegen:
    """Test the Codegen class."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.get().clear()

    def test_generate_route_page_no_components(self, tmp_path):
        """Test generating a single route page with no components."""
        route = Route(
            "/simple", ps.component(lambda: div()["Simple route"]), components=[]
        )
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree([route]), codegen_config)
        codegen.generate_route(route, server_address=SERVER_ADDRESS)

        route_page_path = codegen.output_folder / "routes" / "simple.tsx"
        assert route_page_path.exists()
        result = route_page_path.read_text()

        assert (
            'import { PulseView, type VDOM, type ComponentRegistry, extractServerRouteInfo } from "pulse-ui-client";'
            in result
        )
        assert "// No components needed for this route" in result
        assert "const externalComponents: ComponentRegistry = {};" in result
        assert "export async function loader" in result
        assert 'const path = "simple"' in result
        assert (
            "export default function RouteComponent({ loaderData }: { loaderData: VDOM })"
            in result
        )
        assert "initialVDOM={loaderData}" in result

    def test_generate_route_page_with_components(self, tmp_path):
        """Test generating route with React components."""
        button_comp = ReactComponent("button", "./Button", "Button", False)
        card_comp = ReactComponent("card", "./Card", "Card", False)
        route = Route(
            "/with-components",
            lambda: div()["Route with components"],
            components=[button_comp, card_comp],
        )
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree([route]), codegen_config)
        codegen.generate_route(route, server_address=SERVER_ADDRESS)

        route_page_path = codegen.output_folder / "routes" / "with-components.tsx"
        assert route_page_path.exists()
        result = route_page_path.read_text()

        assert 'import { button as Button } from "./Button";' in result
        assert 'import { card as Card } from "./Card";' in result
        assert '"Button": Button,' in result
        assert '"Card": Card,' in result
        assert "No components needed for this route" not in result

    def test_generate_route_page_with_default_export_components(self, tmp_path):
        """Test generating route with default export components."""
        default_comp = ReactComponent("DefaultComp", "./DefaultComp", is_default=True)
        route = Route(
            "/default-export",
            lambda: div()["Route with default export"],
            components=[default_comp],
        )
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree([route]), codegen_config)
        codegen.generate_route(route, server_address=SERVER_ADDRESS)

        route_page_path = codegen.output_folder / "routes" / "default-export.tsx"
        assert route_page_path.exists()
        result = route_page_path.read_text()

        assert 'import DefaultComp from "./DefaultComp";' in result
        assert '"DefaultComp": DefaultComp,' in result

    def test_generate_routes_ts_empty(self, tmp_path):
        """Test generating config with empty routes list."""
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree([]), codegen_config)
        codegen.generate_routes_ts()

        routes_ts_path = Path(codegen_config.pulse_path) / "routes.ts"
        assert routes_ts_path.exists()
        result = routes_ts_path.read_text()

        assert "export const routes = [" in result
        assert "] satisfies RouteConfig;" in result
        assert 'layout("pulse/_layout.tsx"' in result

    def test_generate_routes_ts_single_root_route(self, tmp_path):
        """Test generating config with single root route."""
        home_route = Route("/", lambda: div(), components=[])
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree([home_route]), codegen_config)
        codegen.generate_routes_ts()

        routes_ts_path = Path(codegen_config.pulse_path) / "routes.ts"
        result = routes_ts_path.read_text()
        assert 'index("pulse/routes/index.tsx")' in result

    def test_generate_routes_ts_multiple_routes(self, tmp_path):
        """Test generating config with multiple routes."""
        routes = [
            Route("/", lambda: div(), components=[]),
            Route("/about", lambda: div(), components=[]),
        ]
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree(routes), codegen_config)
        codegen.generate_routes_ts()

        routes_ts_path = Path(codegen_config.pulse_path) / "routes.ts"
        result = routes_ts_path.read_text()
        assert 'index("pulse/routes/index.tsx")' in result
        assert 'route("about", "pulse/routes/about.tsx")' in result

    def test_full_app_generation(self, tmp_path):
        """Test generating all files for a simple app."""
        Header = ReactComponent("Header", "./components/Header")
        Footer = ReactComponent("Footer", "./components/Footer")
        Button = ReactComponent("Button", "./components/Button")

        home_route = ps.component(
            lambda: div()[Header(title="Home"), Footer(year=2024)]
        )
        users_page = ps.component(lambda: div()["Users Layout", Outlet()])
        user_details = ps.component(lambda: div()["User Details"])
        interactive_route = ps.component(lambda: div()[Button(variant="primary")])

        routes = [
            Route("/", home_route, components=[Header, Footer]),
            Route(
                "/users",
                users_page,
                components=[],
                children=[
                    Route(":id", user_details, components=[]),
                ],
            ),
            Route("/interactive", interactive_route, components=[Button]),
        ]

        app = App(routes=routes)

        codegen_config = CodegenConfig(
            web_dir=str(tmp_path),
            pulse_dir="test_pulse_app",
            lib_path="~/test-lib",
        )
        codegen = Codegen(app.routes, codegen_config)
        codegen.generate_all(server_address=SERVER_ADDRESS)

        pulse_app_dir = Path(codegen.output_folder)
        routes_dir = pulse_app_dir / "routes"

        assert (pulse_app_dir / "_layout.tsx").exists()
        assert (pulse_app_dir / "routes.ts").exists()
        assert (routes_dir / "index.tsx").exists()
        assert (routes_dir / "interactive.tsx").exists()
        assert (routes_dir / "users.tsx").exists()
        assert (routes_dir / "users" / ":id.tsx").exists()

        layout_content = (pulse_app_dir / "_layout.tsx").read_text()
        assert (
            'import { PulseProvider, type PulseConfig } from "~/test-lib";'
            in layout_content
        )
        assert 'serverAddress: "http://localhost:8000"' in layout_content

        routes_ts_content = (pulse_app_dir / "routes.ts").read_text()
        assert (
            'route("interactive", "test_pulse_app/routes/interactive.tsx")'
            in routes_ts_content
        )
        assert (
            'route("users", "test_pulse_app/routes/users.tsx", [' in routes_ts_content
        )
        assert (
            'route(":id", "test_pulse_app/routes/users/:id.tsx")' in routes_ts_content
        )

        home_content = (routes_dir / "index.tsx").read_text()
        assert (
            'import { PulseView, type VDOM, type ComponentRegistry, extractServerRouteInfo } from "~/test-lib";'
            in home_content
        )
        assert 'import { Header } from "./components/Header";' in home_content
        assert '"Header": Header,' in home_content
        assert 'const path = ""' in home_content
        assert "initialVDOM={loaderData}" in home_content

        interactive_content = (routes_dir / "interactive.tsx").read_text()
        assert 'import { Button } from "./components/Button";' in interactive_content
        assert '"Header": Header,' not in interactive_content
        assert '"Button": Button,' in interactive_content
        assert 'const path = "interactive"' in interactive_content
        assert "initialVDOM={loaderData}" in interactive_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
