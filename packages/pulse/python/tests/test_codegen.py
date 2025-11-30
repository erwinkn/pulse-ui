"""
Integration tests for the complete Pulse UI system.

This module tests the full pipeline from Python UI tree definition
through TypeScript code generation and React component integration.
"""

from pathlib import Path
from typing import Any, cast

import pulse as ps
import pytest
from pulse import div
from pulse.app import App
from pulse.codegen.codegen import Codegen, CodegenConfig
from pulse.codegen.templates.route import RouteTemplate
from pulse.components.react_router import Outlet
from pulse.javascript_v2.function import JsFunction
from pulse.react_component import COMPONENT_REGISTRY, ReactComponent
from pulse.routing import Route, RouteTree
from pulse.vdom import Component, component

SERVER_ADDRESS = "http://localhost:8000"


class TestCodegen:
	"""Test the Codegen class."""

	def setup_method(self):
		"""Clear the component registry before each test."""
		COMPONENT_REGISTRY.get().clear()

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

		assert 'import type { HeadersArgs } from "react-router";' in result
		assert (
			'import { PulseView, type ComponentRegistry } from "pulse-ui-client";'
			in result
		)
		assert "// No components needed for this route" in result
		assert "const externalComponents: ComponentRegistry = {};" in result
		assert 'const path = "/simple"' in result
		assert "export function headers" in result
		assert "export default function RouteComponent()" in result
		assert "externalComponents={externalComponents}" in result
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

		assert 'import { button } from "./Button";' in result
		assert 'import { card } from "./Card";' in result
		assert '"button": button,' in result
		assert '"card": card,' in result
		assert "No components needed for this route" not in result

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

		assert 'import DefaultComp from "./DefaultComp";' in result
		assert '"DefaultComp": DefaultComp,' in result

	def test_generate_route_page_with_property_components(self, tmp_path: Path):
		"""Test generating route with import_name components (nested component access)."""
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

		# Should import AppShell only once despite having two components
		assert 'import { AppShell } from "@mantine/core";' in result
		assert result.count("import { AppShell }") == 1  # Only one import

		# Should have components in registry
		assert '"AppShell.Header": AppShell.Header,' in result
		assert '"AppShell.Footer": AppShell.Footer,' in result
		assert "No components needed for this route" not in result

	def test_generate_route_page_with_duplicate_imports_different_aliases(
		self, tmp_path: Path
	):
		"""Test generating route with multiple components importing same value with different aliases."""
		# Duplicate imports of the same symbol should deduplicate import statements
		# and result in a single registry entry (last wins if duplicates are provided).
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

		# Should import button once
		assert 'import { button } from "./Button";' in result
		assert result.count("import { button }") == 1  # Only one import

		# Should have a single registry entry for the duplicate name
		assert result.count('"button": button,') == 1
		assert "No components needed for this route" not in result

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
		assert (
			'import { PulseView, type ComponentRegistry, RenderLazy } from "pulse-ui-client";'
			in result
		)

		# Should use RenderLazy dynamic import for the component and not import it statically
		assert (
			'RenderLazy(() => import("./LazyThing").then((m) => ({ default: m.LazyThing })))'
			in result
		)
		assert 'import { LazyThing } from "./LazyThing";' not in result
		assert 'import LazyThing from "./LazyThing";' not in result

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
		assert (
			'import { PulseView, type ComponentRegistry } from "pulse-ui-client";'
			in home_content
		)
		assert 'import { Header } from "./components/Header";' in home_content
		assert '"Header": Header,' in home_content
		assert 'const path = "/"' in home_content
		assert "externalComponents={externalComponents}" in home_content
		assert "path={path}" in home_content

		interactive_content = (routes_dir / "interactive.tsx").read_text()
		assert 'import { Button } from "./components/Button";' in interactive_content
		assert '"Header": Header,' not in interactive_content
		assert '"Button": Button,' in interactive_content
		assert 'const path = "/interactive"' in interactive_content
		assert "externalComponents={externalComponents}" in interactive_content
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


class TestRouteTemplateConflicts:
	"""Unit tests for RouteTemplate name/alias conflict resolution."""

	def _by_src(self, import_sources: list[Any], src: str):
		for s in import_sources:
			if s.src == src:
				return s
		raise AssertionError(f"No import source for {src}")

	def test_alias_named_imports_on_reserved_conflict_and_component_ssr(self):
		rt = RouteTemplate(reserved_names=["Button", "AppShell"])

		comps = [
			ReactComponent(name="Button", src="./ui/button"),
			ReactComponent(name="AppShell", src="@mantine/core", prop="Header"),
		]
		rt.add_components(comps)
		ctx = rt.context()

		# Imports aliased due to reserved names
		import_sources = cast(list[Any], ctx["import_sources"])
		by_button = self._by_src(import_sources, "./ui/button")
		assert len(by_button.values) == 1
		assert by_button.values[0].name == "Button"
		assert by_button.values[0].alias == "Button2"

		by_mantine = self._by_src(import_sources, "@mantine/core")
		assert len(by_mantine.values) == 1
		assert by_mantine.values[0].name == "AppShell"
		assert by_mantine.values[0].alias == "AppShell2"

		components_ctx = cast(list[Any], ctx["components_ctx"])
		comps_ctx = {c["key"]: c for c in components_ctx}
		assert comps_ctx["Button2"]["expr"] == "Button2"
		assert comps_ctx["Button2"]["dynamic"] == "({ default: m.Button })"
		assert comps_ctx["AppShell2.Header"]["expr"] == "AppShell2.Header"
		assert (
			comps_ctx["AppShell2.Header"]["dynamic"]
			== "({ default: m.AppShell.Header })"
		)

	def test_alias_default_import_on_reserved_conflict(self):
		rt = RouteTemplate(reserved_names=["DefaultComp"])  # force aliasing

		comps = [ReactComponent(name="DefaultComp", src="./Default", is_default=True)]
		rt.add_components(comps)
		ctx = rt.context()

		import_sources = cast(list[Any], ctx["import_sources"])
		by_default = self._by_src(import_sources, "./Default")
		# Default import is a single identifier string
		assert by_default.default_import == "DefaultComp2"

		comp_ctx = cast(list[Any], ctx["components_ctx"])[0]
		assert comp_ctx["key"] == "DefaultComp2"
		assert comp_ctx["expr"] == "DefaultComp2"
		# Dynamic selector for default import uses m.default
		assert comp_ctx["dynamic"] == "({ default: m.default })"

	def test_deduplicate_repeated_imports_of_same_symbol(self):
		rt = RouteTemplate()
		# Same component twice -> one import value
		comps = [
			ReactComponent(name="Button", src="./Button"),
			ReactComponent(name="Button", src="./Button"),
		]
		rt.add_components(comps)
		ctx = rt.context()

		import_sources = cast(list[Any], ctx["import_sources"])
		by_src = self._by_src(import_sources, "./Button")
		assert len(by_src.values) == 1
		# Final components_ctx keeps one (last-wins on same key)
		components_ctx = cast(list[Any], ctx["components_ctx"])
		assert len(components_ctx) == 1
		assert components_ctx[0]["key"] == "Button"

	def test_alias_same_named_components_from_different_sources(self):
		COMPONENT_REGISTRY.get().clear()
		rt = RouteTemplate()
		comps = [
			ReactComponent(name="Select", src="@lib/a"),
			ReactComponent(name="Select", src="@lib/b"),
		]
		rt.add_components(comps)
		ctx = rt.context()

		import_sources = cast(list[Any], ctx["import_sources"])
		by_a = self._by_src(import_sources, "@lib/a")
		by_b = self._by_src(import_sources, "@lib/b")
		assert by_a.values[0].name == "Select"
		assert by_a.values[0].alias is None
		assert by_b.values[0].name == "Select"
		assert by_b.values[0].alias == "Select2"

		components_ctx = cast(list[Any], ctx["components_ctx"])
		comps_ctx = {c["key"]: c for c in components_ctx}
		assert comps_ctx["Select"]["expr"] == "Select"
		assert comps_ctx["Select"]["src"] == "@lib/a"
		assert comps_ctx["Select2"]["expr"] == "Select2"
		assert comps_ctx["Select2"]["src"] == "@lib/b"

		node_a = comps[0]()
		node_b = comps[1]()
		assert node_a.tag == "$$Select"
		assert node_b.tag == "$$Select2"

	def test_alias_same_named_import_from_two_sources_and_keep_both_components(self):
		rt = RouteTemplate()
		comps = [
			ReactComponent(name="Stack", src="@mantine/core"),
			# Different source and a prop so the component registry key differs
			ReactComponent(name="Stack", src="@other/lib", prop="Item"),
		]
		rt.add_components(comps)
		ctx = rt.context()

		import_sources = cast(list[Any], ctx["import_sources"])
		by_core = self._by_src(import_sources, "@mantine/core")
		by_other = self._by_src(import_sources, "@other/lib")
		assert by_core.values[0].name == "Stack" and by_core.values[0].alias is None
		assert (
			by_other.values[0].name == "Stack" and by_other.values[0].alias == "Stack2"
		)

		components_ctx = cast(list[Any], ctx["components_ctx"])
		comps_ctx = {c["key"]: c for c in components_ctx}
		assert comps_ctx["Stack"]["expr"] == "Stack"
		assert comps_ctx["Stack2.Item"]["expr"] == "Stack2.Item"

	def test_reserve_js_function_names_with_conflicts(self):
		# Define module-level functions for JsFunction (can't use lambdas)
		def path() -> None:
			pass

		def myFn() -> None:
			pass

		def RenderLazy() -> None:
			pass

		rt = RouteTemplate()
		# "path" and "RenderLazy" are in RESERVED_NAMES, should alias
		rt.reserve_js_function_names(
			[
				JsFunction(path),
				JsFunction(myFn),
				JsFunction(RenderLazy),
			]
		)
		ctx = rt.context()
		locals_map = cast(dict[str, Any], ctx["local_js_names"])
		assert locals_map["path"] == "path2"
		assert locals_map["myFn"] == "myFn"
		assert locals_map["RenderLazy"] == "RenderLazy2"


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
