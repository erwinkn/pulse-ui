"""
Integration tests for the complete Pulse UI system.

This module tests the full pipeline from Python UI tree definition
through TypeScript code generation and React component integration.
"""

from pathlib import Path

from pulse.vdom import Component, component
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

        assert 'import { type HeadersArgs } from "react-router";' in result
        assert (
            'import { PulseView, type VDOM, type ComponentRegistry } from "pulse-ui-client";'
            in result
        )
        assert "// No components needed for this route" in result
        assert "const externalComponents: ComponentRegistry = {};" in result
        assert 'const path = "simple"' in result
        assert "export function headers" in result
        assert "export default function RouteComponent()" in result
        assert "externalComponents={externalComponents}" in result
        assert "path={path}" in result

    def test_generate_route_page_with_components(self, tmp_path):
        """Test generating route with React components."""
        button_comp = ReactComponent("button", "./Button", "Button", False)
        card_comp = ReactComponent("card", "./Card", "Card", False)
        route = Route(
            "/with-components",
            Component(lambda: div()["Route with components"]),
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
            Component(lambda: div()["Route with default export"]),
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
        home_route = Route("/", Component(lambda: div()), components=[])
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree([home_route]), codegen_config)
        codegen.generate_routes_ts()

        routes_ts_path = Path(codegen_config.pulse_path) / "routes.ts"
        result = routes_ts_path.read_text()
        # New format derives dev routes from runtime route tree
        assert "import { rrPulseRouteTree" in result
        assert "function toDevRoute(" in result
        assert 'layout("pulse/_layout.tsx", rrPulseRouteTree.map(toDevRoute))' in result

    def test_generate_routes_ts_multiple_routes(self, tmp_path):
        """Test generating config with multiple routes."""
        routes = [
            Route("/", Component(lambda: div()), components=[]),
            Route("/about", Component(lambda: div()), components=[]),
        ]
        codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(RouteTree(routes), codegen_config)
        codegen.generate_routes_ts()

        routes_ts_path = Path(codegen_config.pulse_path) / "routes.ts"
        result = routes_ts_path.read_text()
        # New format uses mapping from runtime tree, not static route literals
        assert "import { rrPulseRouteTree" in result
        assert "function toDevRoute(" in result
        assert "rrPulseRouteTree.map(toDevRoute)" in result

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
            'import { extractServerRouteInfo, PulseProvider, type PulseConfig, type PulsePrerender } from "~/test-lib";'
            in layout_content
        )
        assert 'serverAddress: "http://localhost:8000"' in layout_content

        routes_ts_content = (pulse_app_dir / "routes.ts").read_text()
        # routes.ts should be built from runtime route tree now
        assert "import { rrPulseRouteTree" in routes_ts_content
        assert "function toDevRoute(" in routes_ts_content
        assert "rrPulseRouteTree.map(toDevRoute)" in routes_ts_content

        # Validate the runtime route tree carries correct file/path data
        runtime_content = (pulse_app_dir / "routes.runtime.ts").read_text()
        assert 'path: "interactive"' in runtime_content
        assert 'file: "test_pulse_app/routes/interactive.tsx"' in runtime_content
        assert 'path: "users"' in runtime_content
        assert 'file: "test_pulse_app/routes/users.tsx"' in runtime_content
        assert 'path: ":id"' in runtime_content
        assert 'file: "test_pulse_app/routes/users/:id.tsx"' in runtime_content

        home_content = (routes_dir / "index.tsx").read_text()
        assert (
            'import { PulseView, type VDOM, type ComponentRegistry } from "~/test-lib";'
            in home_content
        )
        assert 'import { Header } from "./components/Header";' in home_content
        assert '"Header": Header,' in home_content
        assert 'const path = ""' in home_content
        assert "externalComponents={externalComponents}" in home_content
        assert "path={path}" in home_content

        interactive_content = (routes_dir / "interactive.tsx").read_text()
        assert 'import { Button } from "./components/Button";' in interactive_content
        assert '"Header": Header,' not in interactive_content
        assert '"Button": Button,' in interactive_content
        assert 'const path = "interactive"' in interactive_content
        assert "externalComponents={externalComponents}" in interactive_content
        assert "path={path}" in interactive_content

    def test_sibling_layouts_get_distinct_files(self, tmp_path):
        """Ensure sibling layouts generate distinct file paths and avoid collisions."""

        @component
        def render():
            return div()

        app = App(
            routes=[
                ps.Layout(render, [ps.Route("/a", render)]),
                ps.Layout(render, [ps.Route("/b", render)]),
            ]
        )

        cfg = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
        codegen = Codegen(app.routes, cfg)
        codegen.generate_all(server_address=SERVER_ADDRESS)

        # Expect two sibling layout directories: layout/ and layout2/
        layout1 = codegen.output_folder / "layouts" / "layout" / "_layout.tsx"
        layout2 = codegen.output_folder / "layouts" / "layout2" / "_layout.tsx"
        assert layout1.exists(), f"missing {layout1}"
        assert layout2.exists(), f"missing {layout2}"
        assert layout1 != layout2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
