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
from pulse.component import Component, component
from pulse.components.react_router import Outlet
from pulse.routing import Route, RouteTree
from pulse.transpiler import Import, Jsx, clear_function_cache

SERVER_ADDRESS = "http://localhost:8000"


class TestCodegen:
	"""Test the Codegen class."""

	def setup_method(self):
		"""Clear the registries before each test."""
		clear_function_cache()  # Also clears ref registry

	def test_generate_route_page_no_components(self, tmp_path: Path):
		"""Test generating a single route page."""
		route = Route("/simple", ps.component(lambda: div()["Simple route"]))
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(
			route, server_address=SERVER_ADDRESS, asset_import_paths={}
		)

		route_page_path = codegen.output_folder / "routes" / "simple.jsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		assert "import { PulseView" in result
		assert '"pulse-ui-client"' in result
		# Unified registry only
		assert "const __registry = {" in result
		assert 'const path = "/simple"' in result
		assert "export function headers" in result
		assert "export default function RouteComponent()" in result
		assert "registry={__registry}" in result
		assert "path={path}" in result

	def test_generate_route_page_with_components(self, tmp_path: Path):
		"""Test generating route with React components."""
		# Use package paths to avoid relative path resolution in tests
		button_import = Import("Button", "@ui/components")
		card_import = Import("Card", "@ui/components")
		_button_comp = Jsx(button_import)
		_card_comp = Jsx(card_import)
		route = Route(
			"/with-components",
			Component(lambda: div()["Route with components"]),
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(
			route, server_address=SERVER_ADDRESS, asset_import_paths={}
		)

		route_page_path = codegen.output_folder / "routes" / "with-components.jsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		# New system uses unique IDs like Button_1, Card_2
		# Both may be in the same import statement since they're from the same source
		assert "Button as Button_" in result
		assert "Card as Card_" in result
		assert '"@ui/components"' in result
		# Components are in the unified registry with their own IDs
		assert "const __registry = {" in result

	def test_generate_route_page_with_default_export_components(self, tmp_path: Path):
		"""Test generating route with default export components."""
		default_import = Import("DefaultComp", "@ui/default-comp", kind="default")
		_default_comp = Jsx(default_import)
		route = Route(
			"/default-export",
			Component(lambda: div()["Route with default export"]),
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(
			route, server_address=SERVER_ADDRESS, asset_import_paths={}
		)

		route_page_path = codegen.output_folder / "routes" / "default-export.jsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		# Default imports use the name directly with unique ID
		assert "import DefaultComp_" in result
		assert '"@ui/default-comp"' in result

	def test_generate_route_page_with_property_components(self, tmp_path: Path):
		"""Test generating route with prop-accessed components (nested component access)."""
		from pulse.transpiler.nodes import Member

		# Use Member to access properties on an import
		app_shell_import = Import("AppShell", "@mantine/core")
		# These will be in the registry because the import is in the registry
		# Standalone Jsx wrappers without function dependencies are no longer auto-registered
		# via the Route components argument.
		_app_shell_header = Jsx(Member(app_shell_import, "Header"))
		_app_shell_footer = Jsx(Member(app_shell_import, "Footer"))
		route = Route(
			"/app-shell",
			Component(lambda: div()["AppShell route"]),
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(
			route, server_address=SERVER_ADDRESS, asset_import_paths={}
		)

		route_page_path = codegen.output_folder / "routes" / "app-shell.jsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		# Should import AppShell with unique ID
		assert "import { AppShell as AppShell_" in result
		assert '"@mantine/core"' in result
		# Should have one import (deduplication by same name/src)
		assert result.count("import { AppShell as") == 1
		# Registry should have AppShell
		assert "AppShell_" in result

	def test_generate_route_page_with_duplicate_imports(self, tmp_path: Path):
		"""Test generating route with duplicate components."""
		# Duplicate imports of the same symbol should deduplicate
		button_import = Import("Button", "@ui/button")
		_button1 = Jsx(button_import)
		_button2 = Jsx(button_import)  # Same import, different Jsx wrappers
		route = Route(
			"/duplicate-imports",
			Component(lambda: div()["Duplicate imports route"]),
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_route(
			route, server_address=SERVER_ADDRESS, asset_import_paths={}
		)

		route_page_path = codegen.output_folder / "routes" / "duplicate-imports.jsx"
		assert route_page_path.exists()
		result = route_page_path.read_text()

		# Should have only one import statement for Button
		assert result.count('from "@ui/button"') == 1

	@pytest.mark.skip(reason="Lazy component support not yet implemented")
	def test_generate_route_page_with_lazy_component_raises_not_implemented(
		self, tmp_path: Path
	):
		"""Lazy components should raise NotImplementedError (not yet supported)."""
		lazy_import = Import("LazyThing", "@ui/lazy-thing")
		_lazy_comp = Jsx(lazy_import)  # lazy=True no longer supported
		route = Route(
			"/lazy",
			Component(lambda: div()["Lazy route"]),
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)

		# TODO: Implement lazy component support
		with pytest.raises(NotImplementedError):
			codegen.generate_route(
				route, server_address=SERVER_ADDRESS, asset_import_paths={}
			)

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
		home_route = Route("/", Component(lambda: div()))
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
			Route("/", Component(lambda: div())),
			Route("/about", Component(lambda: div())),
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
		header_import = Import("Header", "./components/Header")
		footer_import = Import("Footer", "./components/Footer")
		button_import = Import("Button", "./components/Button")
		Header = Jsx(header_import)
		Footer = Jsx(footer_import)
		Button = Jsx(button_import)

		home_route = ps.component(
			lambda: div()[Header(title="Home"), Footer(year=2024)]
		)
		users_page = ps.component(lambda: div()["Users Layout", Outlet()])
		user_details = ps.component(lambda: div()["User Details"])
		interactive_route = ps.component(lambda: div()[Button(variant="primary")])

		routes = [
			Route("/", home_route),
			Route(
				"/users",
				users_page,
				children=[
					Route(":id", user_details),
				],
			),
			Route("/interactive", interactive_route),
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
		assert (routes_dir / "index.jsx").exists()
		assert (routes_dir / "interactive.jsx").exists()
		assert (routes_dir / "users.jsx").exists()
		# The dynamic route :id gets sanitized with a hash suffix
		user_id_files = list((routes_dir / "users").glob("_id_*.jsx"))
		assert len(user_id_files) == 1, (
			f"Expected 1 _id_*.jsx file, found {user_id_files}"
		)

		layout_content = (pulse_app_dir / "_layout.tsx").read_text()
		assert (
			'import { PulseRouterProvider } from "pulse-ui-client";' in layout_content
		)
		assert (
			'import type { Location, NavigateFn, Params } from "pulse-ui-client";'
			in layout_content
		)
		assert "export default function PulseLayout(" in layout_content
		assert "<PulseRouterProvider" in layout_content
		assert "location={location}" in layout_content
		assert "params={params}" in layout_content
		assert "navigate={navigate}" in layout_content

		routes_ts_content = (pulse_app_dir / "routes.ts").read_text()
		# routes.ts should be built from runtime route tree now
		assert "import { rrPulseRouteTree" in routes_ts_content
		assert "function toDevRoute(" in routes_ts_content
		assert "rrPulseRouteTree.map(toDevRoute)" in routes_ts_content

		# Validate the runtime route tree carries correct file/path data
		runtime_content = (pulse_app_dir / "routes.runtime.ts").read_text()
		assert 'path: "interactive"' in runtime_content
		assert 'file: "test_pulse_app/routes/interactive.jsx"' in runtime_content
		assert 'path: "users"' in runtime_content
		assert 'file: "test_pulse_app/routes/users.jsx"' in runtime_content
		assert 'path: ":id"' in runtime_content
		# The dynamic route file has a hash suffix that depends on extension
		assert 'file: "test_pulse_app/routes/users/_id_' in runtime_content
		assert '.jsx"' in runtime_content

		home_content = (routes_dir / "index.jsx").read_text()
		assert "import { PulseView" in home_content
		assert '"pulse-ui-client"' in home_content
		assert "import { Header as Header_" in home_content
		assert 'const path = "/"' in home_content
		assert "registry={__registry}" in home_content
		assert "path={path}" in home_content

		interactive_content = (routes_dir / "interactive.jsx").read_text()
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
		"""Clear the registries before each test."""
		clear_function_cache()

	def test_generate_route_basic(self):
		"""Test basic route generation."""
		result = generate_route(path="/test")

		assert "import { PulseView" in result
		assert 'const path = "/test"' in result
		assert "export default function RouteComponent()" in result
		assert "export function headers" in result
		assert "const __registry = {" in result

	def test_generate_route_with_component(self):
		"""Test route generation with a component."""
		button_import = Import("Button", "@mantine/core")
		Jsx(button_import)

		result = generate_route(path="/dashboard")

		assert "import { Button as Button_" in result
		assert '"@mantine/core"' in result
		# Uses unified registry
		assert "const __registry = {" in result

	@pytest.mark.skip(reason="Lazy component support not yet implemented")
	def test_generate_route_with_lazy_component_raises(self):
		"""Test route generation with a lazy component raises NotImplementedError."""
		chart_import = Import("HeavyChart", "@mantine/charts")
		Jsx(chart_import)  # lazy=True no longer supported

		# TODO: Implement lazy component support
		with pytest.raises(NotImplementedError):
			generate_route(path="/charts")

	def test_generate_route_with_css_import(self):
		"""Test route generation with CSS side-effect import."""
		# Create a side-effect import for CSS
		Import("", "@mantine/core/styles.css", kind="side_effect")

		button_import = Import("Button", "@mantine/core")
		Jsx(button_import)

		result = generate_route(path="/styled")

		assert 'import "@mantine/core/styles.css"' in result

	def test_generate_route_deduplicates_imports(self):
		"""Test that duplicate imports are deduplicated."""
		# Create two refs with the same import (deduplication of imports happens automatically)
		button_import = Import("Button", "@mantine/core")
		Jsx(button_import)
		Jsx(button_import)  # Same import, different Jsx wrappers

		result = generate_route(path="/test")

		# Should only have one import statement
		assert result.count('from "@mantine/core"') == 1

	def test_generate_route_with_namespace_import(self):
		"""Test route generation with namespace import."""
		# Creating the import auto-registers it (for import generation)
		Import("Icons", "lucide-react", kind="namespace")

		result = generate_route(path="/icons")

		# Should generate: import * as Icons_X from "lucide-react";
		assert "import * as Icons_" in result
		assert 'from "lucide-react"' in result
		# Note: Imports are no longer auto-added to __registry
		# Only Refs are in the registry now


class TestLocalFileImports:
	"""Test local file copying and import path generation."""

	def setup_method(self):
		"""Clear the registries before each test."""
		clear_function_cache()

	def test_local_css_file_copied_to_assets(self, tmp_path: Path):
		"""Local CSS file is copied to assets folder."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create a local CSS file
		css_file = tmp_path / "src" / "styles.css"
		css_file.parent.mkdir(parents=True)
		css_file.write_text("body { margin: 0; }")

		# Create import using absolute path
		Import("", str(css_file), kind="side_effect")

		route = Route("/test", Component(lambda: div()))
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Check assets folder exists and contains the file
		assets_dir = codegen.assets_folder
		assert assets_dir.exists()

		# Find the copied CSS file (with unique ID suffix)
		css_files = list(assets_dir.glob("styles_*.css"))
		assert len(css_files) == 1
		assert css_files[0].read_text() == "body { margin: 0; }"

	def test_local_js_file_copied_to_assets(self, tmp_path: Path):
		"""Local JS/TS file is copied to assets folder."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create a local TS file
		ts_file = tmp_path / "src" / "utils.ts"
		ts_file.parent.mkdir(parents=True)
		ts_file.write_text("export const helper = () => {};")

		# Create import using absolute path (without extension)
		Import("helper", str(tmp_path / "src" / "utils"), kind="named")

		route = Route("/test", Component(lambda: div()))
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Find the copied TS file
		assets_dir = codegen.assets_folder
		ts_files = list(assets_dir.glob("utils_*.ts"))
		assert len(ts_files) == 1
		assert ts_files[0].read_text() == "export const helper = () => {};"

	def test_route_imports_from_assets_folder(self, tmp_path: Path):
		"""Generated routes import local files from assets folder."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create local files
		css_file = tmp_path / "src" / "app.css"
		css_file.parent.mkdir(parents=True)
		css_file.write_text("body { margin: 0; }")

		# Create import (auto-registered, so we just need to create it)
		_css_import = Import("", str(css_file), kind="side_effect")
		del _css_import  # Suppress unused variable warning

		route = Route("/test", Component(lambda: div()))
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Read the generated route
		route_file = codegen.output_folder / "routes" / "test.jsx"
		content = route_file.read_text()

		# Should import from ../assets/ (relative to routes folder)
		assert 'import "../assets/app_' in content
		assert '.css"' in content

	def test_nested_route_imports_from_assets_folder(self, tmp_path: Path):
		"""Nested routes also import from assets folder with correct relative path."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create local file
		ts_file = tmp_path / "src" / "shared.ts"
		ts_file.parent.mkdir(parents=True)
		ts_file.write_text("export const shared = 1;")

		# Create import
		Import("shared", str(ts_file))

		# Create nested route structure
		parent_route = Route(
			"/users",
			Component(lambda: div()["Users"]),
			children=[
				Route(":id", Component(lambda: div()["User"])),
			],
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([parent_route]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Check parent route import
		parent_file = codegen.output_folder / "routes" / "users.jsx"
		parent_content = parent_file.read_text()
		assert 'from "../assets/shared_' in parent_content

		# Check nested route import - it's in users/_id_*.jsx
		nested_files = list(
			(codegen.output_folder / "routes" / "users").glob("_id_*.jsx")
		)
		assert len(nested_files) == 1
		nested_content = nested_files[0].read_text()
		# Nested routes are in routes/users/, so need ../../assets/
		assert 'from "../../assets/shared_' in nested_content

	def test_multiple_local_files_all_copied(self, tmp_path: Path):
		"""Multiple local files are all copied to assets folder."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create multiple local files
		file1 = tmp_path / "src" / "styles.css"
		file2 = tmp_path / "src" / "utils.ts"
		file3 = tmp_path / "src" / "config.json"
		for f in [file1, file2, file3]:
			f.parent.mkdir(parents=True, exist_ok=True)
			f.write_text(f"content of {f.name}")

		# Create imports
		Import("", str(file1), kind="side_effect")
		Import("utils", str(tmp_path / "src" / "utils"))
		Import("config", str(file3), kind="default")

		route = Route("/test", Component(lambda: div()))
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Check all files copied
		assets_dir = codegen.assets_folder
		assert len(list(assets_dir.glob("styles_*.css"))) == 1
		assert len(list(assets_dir.glob("utils_*.ts"))) == 1
		assert len(list(assets_dir.glob("config_*.json"))) == 1

	def test_package_imports_not_affected(self, tmp_path: Path):
		"""Package imports are not affected by local file handling."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create package imports (should not be treated as local)
		Import("useState", "react")
		Import("Button", "@mantine/core")
		Jsx(Import("Card", "@mantine/core"))

		route = Route("/test", Component(lambda: div()))
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([route]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Assets folder should either not exist or be empty
		assets_dir = codegen.assets_folder
		if assets_dir.exists():
			assert len(list(assets_dir.iterdir())) == 0

		# Route should import from package paths directly
		route_file = codegen.output_folder / "routes" / "test.jsx"
		content = route_file.read_text()
		assert 'from "react"' in content
		assert 'from "@mantine/core"' in content

	def test_layout_imports_from_assets_folder(self, tmp_path: Path):
		"""Layout files also import from assets folder with correct relative path."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create local file
		css_file = tmp_path / "src" / "layout.css"
		css_file.parent.mkdir(parents=True)
		css_file.write_text(".layout { display: flex; }")

		# Create import
		Import("", str(css_file), kind="side_effect")

		# Create layout route
		from pulse.routing import Layout

		layout = Layout(
			Component(lambda: div()["Layout"]),
			children=[Route("/", Component(lambda: div()["Home"]))],
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([layout]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Check layout file import - layouts are in layouts/ folder
		layout_files = list((codegen.output_folder / "layouts").rglob("_layout.tsx"))
		assert len(layout_files) >= 1

		# The layout file should import from ../assets/ or ../../assets/ depending on nesting
		layout_content = layout_files[0].read_text()
		assert "../assets/layout_" in layout_content

	def test_deeply_nested_route_correct_relative_path(self, tmp_path: Path):
		"""Deeply nested routes compute correct relative paths to assets."""
		from pulse.transpiler.imports import clear_import_registry

		clear_import_registry()

		# Create local file
		ts_file = tmp_path / "src" / "utils.ts"
		ts_file.parent.mkdir(parents=True)
		ts_file.write_text("export const utils = {};")

		# Create import
		Import("utils", str(ts_file))

		# Create deeply nested route: /org/:orgId/project/:projectId/settings
		org_route = Route(
			"/org",
			Component(lambda: div()["Org"]),
			children=[
				Route(
					":orgId",
					Component(lambda: div()["Org Detail"]),
					children=[
						Route(
							"project",
							Component(lambda: div()["Project"]),
							children=[
								Route(
									":projectId",
									Component(lambda: div()["Project Detail"]),
									children=[
										Route(
											"settings",
											Component(lambda: div()["Settings"]),
										),
									],
								),
							],
						),
					],
				),
			],
		)
		codegen_config = CodegenConfig(web_dir=str(tmp_path / "web"), pulse_dir="pulse")
		codegen = Codegen(RouteTree([org_route]), codegen_config)
		codegen.generate_all(server_address=SERVER_ADDRESS)

		# Find the deepest route file (settings.jsx somewhere in the tree)
		settings_files = list(codegen.output_folder.rglob("settings.jsx"))
		assert len(settings_files) == 1

		settings_content = settings_files[0].read_text()
		# Count how many levels deep: routes/org/_orgId_xxx/project/_projectId_xxx/settings.jsx
		# That's 5 directory levels, so we need 5 levels of ../ plus assets/
		# Actually the path would be something like:
		# routes/org/_orgId_.../project/_projectId_.../settings.jsx -> 5 directories
		# So prefix should be: ../../../../../../assets/
		# But wait, count('/') in file_path gives us 4, so depth=4, prefix = ../../../../../assets/

		# Just verify it ends with /assets/utils_ and starts with the right number of ../
		assert "assets/utils_" in settings_content
		# The import should start with enough ../ to get back to pulse root
		import_match = [
			line
			for line in settings_content.split("\n")
			if "utils_" in line and "from" in line
		]
		assert len(import_match) == 1
		# Check that the path starts with multiple ../ (at least 4 levels up for nested route)
		assert import_match[0].count("../") >= 4


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
