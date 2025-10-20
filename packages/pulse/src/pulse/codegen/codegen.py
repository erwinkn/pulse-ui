import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pulse.codegen.templates.layout import LAYOUT_TEMPLATE
from pulse.codegen.templates.route import CssModuleImport, render_route
from pulse.codegen.templates.routes_ts import (
	ROUTES_CONFIG_TEMPLATE,
	ROUTES_RUNTIME_TEMPLATE,
)
from pulse.codegen.utils import NameRegistry
from pulse.css import CssImport, CssModule
from pulse.env import env
from pulse.routing import Layout, Route, RouteTree

logger = logging.getLogger(__file__)


@dataclass
class CodegenConfig:
	"""
	Configuration for code generation.

	Attributes:
	    web_dir (str): Root directory for the web output.
	    pulse_dir (str): Name of the Pulse app directory.
	    pulse_path (Path): Full path to the generated app directory.
	"""

	web_dir: Path | str = "web"
	"""Root directory for the web output."""

	pulse_dir: Path | str = "pulse"
	"""Name of the Pulse app directory."""

	base_dir: Path | None = None
	"""Directory containing the user's app file. If not provided, resolved from env."""

	@property
	def resolved_base_dir(self) -> Path:
		"""Resolve the base directory where relative paths should be anchored.

		Precedence:
		  1) Explicit `base_dir` if provided
		  2) Env var `PULSE_APP_FILE` (directory of the file)
		  3) Env var `PULSE_APP_DIR`
		  4) Current working directory
		"""
		if isinstance(self.base_dir, Path):
			return self.base_dir
		app_file = env.pulse_app_file
		if app_file:
			return Path(app_file).parent
		app_dir = env.pulse_app_dir
		if app_dir:
			return Path(app_dir)
		return Path.cwd()

	@property
	def web_root(self) -> Path:
		"""Absolute path to the web root directory (e.g. `<app_dir>/pulse-web`)."""
		wd = Path(self.web_dir)
		if wd.is_absolute():
			return wd
		return self.resolved_base_dir / wd

	@property
	def pulse_path(self) -> Path:
		"""Full path to the generated app directory."""
		return self.web_root / "app" / self.pulse_dir


def write_file_if_changed(path: Path, content: str) -> Path:
	"""Write content to file only if it has changed."""
	if path.exists():
		try:
			current_content = path.read_text()
			if current_content == content:
				return path  # Skip writing, content is the same
		except Exception:
			logging.warning(f"Can't read file {path.absolute()}")
			# If we can't read the file for any reason, just write it
			pass

	path.parent.mkdir(exist_ok=True, parents=True)
	path.write_text(content)
	return path


class Codegen:
	cfg: CodegenConfig
	routes: RouteTree
	_css_name_registry: NameRegistry

	def __init__(self, routes: RouteTree, config: CodegenConfig) -> None:
		self.cfg = config
		self.routes = routes
		self._css_module_dest: dict[str, Path] = {}
		self._copied_css_modules: set[Path] = set()
		self._css_name_registry = NameRegistry()
		self._css_import_dest: dict[str, Path | str] = {}

	@property
	def output_folder(self):
		return self.cfg.pulse_path

	def generate_all(
		self, server_address: str, internal_server_address: str | None = None
	):
		self._copied_css_modules = set()
		self._css_module_dest = {}
		self._css_name_registry = NameRegistry()
		self._css_import_dest = {}
		# Keep track of all generated files
		generated_files = set(
			[
				self.generate_layout_tsx(server_address, internal_server_address),
				self.generate_routes_ts(),
				self.generate_routes_runtime_ts(),
				*(
					self.generate_route(route, server_address=server_address)
					for route in self.routes.flat_tree.values()
				),
			]
		)
		generated_files.update(self._copied_css_modules)

		# Clean up any remaining files that are not part of the generated files
		for path in self.output_folder.rglob("*"):
			if path.is_file() and path not in generated_files:
				try:
					path.unlink()
					logger.debug(f"Removed stale file: {path}")
				except Exception as e:
					logger.warning(f"Could not remove stale file {path}: {e}")

	def generate_layout_tsx(
		self, server_address: str, internal_server_address: str | None = None
	):
		"""Generates the content of _layout.tsx"""
		content = str(
			LAYOUT_TEMPLATE.render_unicode(
				server_address=server_address,
				internal_server_address=internal_server_address or server_address,
			)
		)
		# The underscore avoids an eventual naming conflict with a generated
		# /layout route.
		return write_file_if_changed(self.output_folder / "_layout.tsx", content)

	def generate_routes_ts(self):
		"""Generate TypeScript code for the routes configuration."""
		routes_str = self._render_routes_ts(self.routes.tree, 2)
		content = str(
			ROUTES_CONFIG_TEMPLATE.render_unicode(
				routes_str=routes_str,
				pulse_dir=self.cfg.pulse_dir,
			)
		)
		return write_file_if_changed(self.output_folder / "routes.ts", content)

	def generate_routes_runtime_ts(self):
		"""Generate a runtime React Router object tree for server-side matching."""
		routes_str = self._render_routes_runtime(self.routes.tree, indent_level=0)
		content = str(
			ROUTES_RUNTIME_TEMPLATE.render_unicode(
				routes_str=routes_str,
			)
		)
		return write_file_if_changed(self.output_folder / "routes.runtime.ts", content)

	def _render_routes_ts(
		self, routes: Sequence[Route | Layout], indent_level: int
	) -> str:
		lines: list[str] = []
		indent_str = "  " * indent_level
		for route in routes:
			if isinstance(route, Layout):
				children_str = ""
				if route.children:
					children_str = f"\n{self._render_routes_ts(route.children, indent_level + 1)}\n{indent_str}"
				lines.append(
					f'{indent_str}layout("{self.cfg.pulse_dir}/layouts/{route.file_path()}", [{children_str}]),'
				)
			else:
				if route.children:
					children_str = f"\n{self._render_routes_ts(route.children, indent_level + 1)}\n{indent_str}"
					lines.append(
						f'{indent_str}route("{route.path}", "{self.cfg.pulse_dir}/routes/{route.file_path()}", [{children_str}]),'
					)
				elif route.is_index:
					lines.append(
						f'{indent_str}index("{self.cfg.pulse_dir}/routes/{route.file_path()}"),'
					)
				else:
					lines.append(
						f'{indent_str}route("{route.path}", "{self.cfg.pulse_dir}/routes/{route.file_path()}"),'
					)
		return "\n".join(lines)

	def generate_route(self, route: Route | Layout, server_address: str):
		if isinstance(route, Layout):
			output_path = self.output_folder / "layouts" / route.file_path()
		else:
			output_path = self.output_folder / "routes" / route.file_path()

		components = route.components or []
		css_modules = route.css_modules or []
		css_side_effects = route.css_imports or []

		target_dir = output_path.parent
		css_imports: list[CssModuleImport] = []
		for module in css_modules:
			import_path = self._prepare_css_module(module, target_dir)
			css_imports.append({"id": module.id, "import_path": import_path})

		css_side_effect_specs: list[str] = []
		for css_import in css_side_effects:
			spec = self._prepare_css_import(css_import, target_dir)
			css_side_effect_specs.append(spec)

		content = render_route(
			route=route,
			components=components,
			css_modules=css_imports,
			css_imports=css_side_effect_specs,
			js_functions=[],
			external_js=[],
			reserved_names=None,
		)
		return write_file_if_changed(output_path, content)

	def _render_routes_runtime(
		self, routes: list[Route | Layout], indent_level: int
	) -> str:
		"""
		Render an array of RRRouteObject literals suitable for matchRoutes.
		"""

		def render_node(node: Route | Layout, indent: int) -> str:
			ind = "  " * indent
			lines: list[str] = [f"{ind}{{"]
			# Common: id and uniquePath
			lines.append(f'{ind}  id: "{node.unique_path()}",')
			lines.append(f'{ind}  uniquePath: "{node.unique_path()}",')
			if isinstance(node, Layout):
				# Pathless layout
				lines.append(
					f'{ind}  file: "{self.cfg.pulse_dir}/layouts/{node.file_path()}",'
				)
			else:
				# Route: index vs path
				if node.is_index:
					lines.append(f"{ind}  index: true,")
				else:
					lines.append(f'{ind}  path: "{node.path}",')
				lines.append(
					f'{ind}  file: "{self.cfg.pulse_dir}/routes/{node.file_path()}",'
				)
			if node.children:
				lines.append(f"{ind}  children: [")
				for c in node.children:
					lines.append(render_node(c, indent + 2))
					lines.append(f"{ind}  ,")
				if lines[-1] == f"{ind}  ,":
					lines.pop()
				lines.append(f"{ind}  ],")
			lines.append(f"{ind}}}")
			return "\n".join(lines)

		ind = "  " * indent_level
		out: list[str] = [f"{ind}["]
		for index, r in enumerate(routes):
			out.append(render_node(r, indent_level + 1))
			if index != len(routes) - 1:
				out.append(f"{ind}  ,")
		out.append(f"{ind}]")
		return "\n".join(out)

	def _copy_css_source(self, source_path: Path) -> Path:
		name = source_path.name
		if name.endswith(".module.css"):
			suffix = ".module.css"
			base_name = name[: -len(suffix)] or "style"
		else:
			suffix = source_path.suffix or ".css"
			base_name = source_path.stem or "style"

		unique_name = self._css_name_registry.register(base_name)
		dest_filename = f"{unique_name}{suffix}"
		dest_path = self.output_folder / "css" / dest_filename
		dest_path.parent.mkdir(parents=True, exist_ok=True)
		content = source_path.read_text()
		write_file_if_changed(dest_path, content)
		self._copied_css_modules.add(dest_path)
		return dest_path

	def _copy_css_module(self, module: CssModule) -> Path:
		return self._copy_css_source(module.source_path)

	def _prepare_css_import(self, css_import: CssImport, target_dir: Path) -> str:
		existing = self._css_import_dest.get(css_import.id)
		if existing is None:
			if css_import.source_path is not None:
				dest_path = self._copy_css_source(css_import.source_path)
				existing = dest_path
			else:
				existing = css_import.specifier or ""
			self._css_import_dest[css_import.id] = existing

		value = self._css_import_dest[css_import.id]
		if isinstance(value, Path):
			rel_path = os.path.relpath(value, target_dir)
			rel_posix = Path(rel_path).as_posix()
			if not rel_posix.startswith("."):
				rel_posix = f"./{rel_posix}"
			return rel_posix
		return value

	def _prepare_css_module(self, module: CssModule, target_dir: Path) -> str:
		dest = self._css_module_dest.get(module.id)
		if dest is None:
			dest = self._copy_css_module(module)
			self._css_module_dest[module.id] = dest
		rel_path = os.path.relpath(dest, target_dir)
		rel_posix = Path(rel_path).as_posix()
		if not rel_posix.startswith("."):
			rel_posix = f"./{rel_posix}"
		return rel_posix
