import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pulse.cli.helpers import ensure_gitignore_has
from pulse.codegen.templates.layout import LAYOUT_TEMPLATE
from pulse.codegen.templates.route import generate_route
from pulse.codegen.templates.routes_ts import (
	ROUTES_CONFIG_TEMPLATE,
	ROUTES_RUNTIME_TEMPLATE,
)
from pulse.env import env
from pulse.javascript_v2.imports import registered_imports
from pulse.routing import Layout, Route, RouteTree

if TYPE_CHECKING:
	from pulse.app import ConnectionStatusConfig

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

	def __init__(self, routes: RouteTree, config: CodegenConfig) -> None:
		self.cfg = config
		self.routes = routes
		self._copied_css_files: set[Path] = set()
		# Maps source path -> destination path for CSS files
		self._css_dest_paths: dict[str, Path] = {}

	@property
	def output_folder(self):
		return self.cfg.pulse_path

	def generate_all(
		self,
		server_address: str,
		internal_server_address: str | None = None,
		api_prefix: str = "",
		connection_status: "ConnectionStatusConfig | None" = None,
	):
		# Ensure generated files are gitignored
		ensure_gitignore_has(self.cfg.web_root, f"app/{self.cfg.pulse_dir}/")

		self._copied_css_files: set[Path] = set()
		self._css_dest_paths: dict[str, Path] = {}

		# Copy all registered CSS files to the output css directory
		self._copy_css_files()

		# Keep track of all generated files
		generated_files = set(
			[
				self.generate_layout_tsx(
					server_address,
					internal_server_address,
					api_prefix,
					connection_status,
				),
				self.generate_routes_ts(),
				self.generate_routes_runtime_ts(),
				*(
					self.generate_route(route, server_address=server_address)
					for route in self.routes.flat_tree.values()
				),
			]
		)
		generated_files.update(self._copied_css_files)

		# Clean up any remaining files that are not part of the generated files
		for path in self.output_folder.rglob("*"):
			if path.is_file() and path not in generated_files:
				try:
					path.unlink()
					logger.debug(f"Removed stale file: {path}")
				except Exception as e:
					logger.warning(f"Could not remove stale file {path}: {e}")

	def _copy_css_files(self) -> None:
		"""Copy all registered local CSS files to the output css directory."""
		from pulse.javascript_v2.imports import CssImport

		css_dir = self.output_folder / "css"

		for imp in registered_imports():
			if not isinstance(imp, CssImport) or not imp.is_local:
				continue

			# Local CssImport has source_path and generated_filename set
			source_path = imp.source_path
			generated_filename = imp.generated_filename
			assert source_path is not None and generated_filename is not None

			if not source_path.exists():
				logger.warning(f"CSS file not found: {source_path}")
				continue

			dest_path = css_dir / generated_filename
			dest_path.parent.mkdir(parents=True, exist_ok=True)
			content = source_path.read_text()
			write_file_if_changed(dest_path, content)
			self._copied_css_files.add(dest_path)
			self._css_dest_paths[str(source_path)] = dest_path

	def generate_layout_tsx(
		self,
		server_address: str,
		internal_server_address: str | None = None,
		api_prefix: str = "",
		connection_status: "ConnectionStatusConfig | None" = None,
	):
		"""Generates the content of _layout.tsx"""
		from pulse.app import ConnectionStatusConfig

		connection_status = connection_status or ConnectionStatusConfig()
		content = str(
			LAYOUT_TEMPLATE.render_unicode(
				server_address=server_address,
				internal_server_address=internal_server_address or server_address,
				api_prefix=api_prefix,
				connection_status=connection_status,
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

		content = generate_route(
			path=route.unique_path(),
			components=list(route.components) if route.components else None,
			route_file_path=output_path,
			css_dir=self.output_folder / "css",
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
