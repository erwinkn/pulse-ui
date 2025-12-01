"""
Integration tests for the complete Pulse UI system.

This module tests the full pipeline from Python UI tree definition
through TypeScript code generation and React component integration.
"""

from pathlib import Path

import pulse as ps
import pytest
from pulse import div
from pulse.app import App
from pulse.codegen.codegen import Codegen, CodegenConfig
from pulse.codegen.templates.route import generate_route
from pulse.components.react_router import Outlet
from pulse.javascript_v2.imports import clear_import_registry
from pulse.react_component import COMPONENT_REGISTRY, ReactComponent
from pulse.routing import Route, RouteTree
from pulse.vdom import Component, component

SERVER_ADDRESS = "http://localhost:8000"


class TestCodegen:
	"""Test the Codegen class."""

	def setup_method(self):
		"""Clear the component registry and import registry before each test."""
		COMPONENT_REGISTRY.get().clear()
		clear_import_registry()

	def test_generate_route_page_no_components(self, tmp_path: Path):
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

		assert "import type { HeadersArgs" in result
		assert '"react-router"' in result
		assert "import { PulseView" in result
		assert '"pulse-ui-client"' in result
		# Unified registry only
		assert "const __registry: Record<string, unknown>" in result
		assert 'const path = "/simple"' in result
		assert "export function headers" in result
		assert "export default function RouteComponent()" in result
		assert "registry={__registry}" in result
		assert "path={path}" in result

	def test_generate_route_page_with_components(self, tmp_path: Path):
		"""Test generating route with React components."""
		button_comp = ReactComponent("button", "./Button", is_default=False)
		card_comp = ReactComponent("card", "./Card", is_default=False)
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

		# New system uses unique IDs like button_1, card_2
		assert "import { button as button_" in result
		assert '"./Button"' in result
		assert "import { card as card_" in result
		assert '"./Card"' in result
		# Components are in the unified registry
		assert "const __registry: Record<string, unknown>" in result

	def test_generate_route_page_with_default_export_components(self, tmp_path: Path):
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

		# Default imports use the name directly with unique ID
		assert "import DefaultComp_" in result
		assert '"./DefaultComp"' in result

	def test_generate_route_page_with_property_components(self, tmp_path: Path):
		"""Test generating route with prop-accessed components (nested component access)."""
		app_shell_header = ReactComponent("AppShell", "@mantine/core", prop="Header")
		app_shell_footer = ReactComponent("AppShell", "@mantine/core", prop="Footer")
		route = Route(
			"/app-shell",
			Component(lambda: div()["AppShell route"]),
			components=[app_shell_header, app_shell_footer],
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(route, server_address=SERVER_ADDRESS)

		route_page_path = codegen.output_folder / "routes" / "app-shell.tsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		# Should import AppShell with unique ID
		assert "import { AppShell as AppShell_" in result
		assert '"@mantine/core"' in result
		# Should have one import (deduplication by same name/src)
		assert result.count("import { AppShell as") == 1

	def test_generate_route_page_with_duplicate_imports(self, tmp_path: Path):
		"""Test generating route with duplicate components."""
		# Duplicate imports of the same symbol should deduplicate
		button1 = ReactComponent("button", "./Button")
		button2 = ReactComponent("button", "./Button")
		route = Route(
			"/duplicate-imports",
			Component(lambda: div()["Duplicate imports route"]),
			components=[button1, button2],
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(route, server_address=SERVER_ADDRESS)

		route_page_path = codegen.output_folder / "routes" / "duplicate-imports.tsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		# Should have only one import statement for button
		assert result.count('from "./Button"') == 1

	def test_generate_route_page_with_lazy_component_imports_renderlazy(
		self, tmp_path: Path
	):
		"""Lazy components should trigger importing RenderLazy and avoid SSR imports."""
		lazy_comp = ReactComponent("LazyThing", "./LazyThing", lazy=True)
		route = Route(
			"/lazy",
			Component(lambda: div()["Lazy route"]),
			components=[lazy_comp],
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(route, server_address=SERVER_ADDRESS)

		route_page_path = codegen.output_folder / "routes" / "lazy.tsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		# Should import RenderLazy from pulse-ui-client when any component is lazy
		assert "RenderLazy" in result
		assert '"pulse-ui-client"' in result

		# Should use RenderLazy dynamic import in the unified registry (now with ID suffix)
		assert "RenderLazy_" in result
		assert 'import("./LazyThing")' in result
		# Lazy component should be in the unified registry
		assert "const __registry: Record<string, unknown>" in result
		# Should NOT import it statically
		assert "import LazyThing_" not in result
		assert "import { LazyThing" not in result

	def test_generate_routes_ts_empty(self, tmp_path: Path):
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

	def test_generate_routes_ts_single_root_route(self, tmp_path: Path):
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

	def test_generate_routes_ts_multiple_routes(self, tmp_path: Path):
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

	def test_full_app_generation(self, tmp_path: Path):
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
		assert (routes_dir / "users" / "_id_4742d9b5.tsx").exists()

		layout_content = (pulse_app_dir / "_layout.tsx").read_text()
		assert (
			'import { deserialize, extractServerRouteInfo, PulseProvider, type PulseConfig, type PulsePrerender } from "pulse-ui-client";'
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
		assert 'file: "test_pulse_app/routes/users/_id_4742d9b5.tsx"' in runtime_content

		home_content = (routes_dir / "index.tsx").read_text()
		assert "import { PulseView" in home_content
		assert '"pulse-ui-client"' in home_content
		assert "import { Header as Header_" in home_content
		assert 'const path = "/"' in home_content
		assert "registry={__registry}" in home_content
		assert "path={path}" in home_content

		interactive_content = (routes_dir / "interactive.tsx").read_text()
		assert "import { Button as Button_" in interactive_content
		assert 'const path = "/interactive"' in interactive_content
		assert "registry={__registry}" in interactive_content
		assert "path={path}" in interactive_content

	def test_sibling_layouts_get_distinct_files(self, tmp_path: Path):
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


class TestGenerateRoute:
	"""Unit tests for the new generate_route function."""

	def setup_method(self):
		"""Clear the import registry before each test."""
		clear_import_registry()
		COMPONENT_REGISTRY.get().clear()

	def test_generate_route_basic(self):
		"""Test basic route generation."""
		result = generate_route(path="/test")

		assert "import { PulseView" in result
		assert "import type { HeadersArgs" in result
		assert 'const path = "/test"' in result
		assert "export default function RouteComponent()" in result
		assert "export function headers" in result
		assert "const __registry: Record<string, unknown>" in result

	def test_generate_route_with_component(self):
		"""Test route generation with a component."""
		Button = ReactComponent("Button", "@mantine/core")

		result = generate_route(
			path="/dashboard",
			components=[Button],
		)

		assert "import { Button as Button_" in result
		assert '"@mantine/core"' in result
		# Uses unified registry
		assert "const __registry: Record<string, unknown>" in result

	def test_generate_route_with_lazy_component(self):
		"""Test route generation with a lazy component."""
		LazyComp = ReactComponent("HeavyChart", "@mantine/charts", lazy=True)

		result = generate_route(
			path="/charts",
			components=[LazyComp],
		)

		assert "RenderLazy_" in result
		assert 'import("@mantine/charts")' in result
		# Lazy components should NOT be imported statically
		assert "import HeavyChart_" not in result
		assert "import { HeavyChart" not in result

	def test_generate_route_with_css_import(self):
		"""Test route generation with CSS side-effect import."""
		from pulse.javascript_v2.imports import CssImport

		Button = ReactComponent(
			"Button",
			"@mantine/core",
			extra_imports=[CssImport("@mantine/core/styles.css")],
		)

		result = generate_route(
			path="/styled",
			components=[Button],
		)

		assert 'import "@mantine/core/styles.css"' in result

	def test_generate_route_deduplicates_imports(self):
		"""Test that duplicate imports are deduplicated."""
		# Create two components with the same import
		Button1 = ReactComponent("Button", "@mantine/core")
		Button2 = ReactComponent("Button", "@mantine/core")

		result = generate_route(
			path="/test",
			components=[Button1, Button2],
		)

		# Should only have one import statement
		assert result.count('from "@mantine/core"') == 1


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
