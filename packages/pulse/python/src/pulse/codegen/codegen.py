import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pulse.cli.helpers import ensure_gitignore_has
from pulse.codegen.templates.layout import LAYOUT_TEMPLATE
from pulse.codegen.templates.route import generate_route
from pulse.codegen.templates.routes_ts import ROUTES_MANIFEST_TEMPLATE
from pulse.env import env
from pulse.routing import Layout, Route, RouteTree
from pulse.transpiler.assets import get_registered_assets

if TYPE_CHECKING:
	from pulse.app import ConnectionStatusConfig

logger = logging.getLogger(__file__)


@dataclass
class CodegenConfig:
	"""Configuration for code generation output paths.

	Controls where generated web files are written. All paths
	can be relative (resolved against base_dir) or absolute.

	Args:
		web_dir: Root directory for web output. Defaults to "web".
		pulse_dir: Subdirectory for generated Pulse files. Defaults to "pulse".
		base_dir: Base directory for resolving relative paths. If not provided,
			resolved from PULSE_APP_FILE, PULSE_APP_DIR, or cwd.

	Attributes:
		web_dir: Root directory for web output.
		pulse_dir: Subdirectory name for generated files.
		base_dir: Explicit base directory, if provided.

	Example:
		```python
		app = ps.App(
		    codegen=ps.CodegenConfig(
		        web_dir="frontend",
		        pulse_dir="generated",
		    ),
		)
		# Generated files will be at: frontend/app/generated/
		```
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

		Returns:
			Resolved base directory path.

		Resolution precedence:
			1. Explicit `base_dir` if provided
			2. Directory of PULSE_APP_FILE env var
			3. PULSE_APP_DIR env var
			4. Current working directory
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
		"""Absolute path to the web root directory.

		Returns:
			Absolute path to web_dir (e.g., `<base_dir>/web`).
		"""
		wd = Path(self.web_dir)
		if wd.is_absolute():
			return wd
		return self.resolved_base_dir / wd

	@property
	def pulse_path(self) -> Path:
		"""Full path to the generated Pulse app directory.

		Returns:
			Absolute path where generated files are written
			(e.g., `<web_root>/app/<pulse_dir>`).
		"""
		return self.web_root / "app" / self.pulse_dir


def write_file_if_changed(path: Path, content: str | bytes) -> Path:
	"""Write content to file only if it has changed."""
	if path.exists():
		try:
			if isinstance(content, bytes):
				current_content = path.read_bytes()
			else:
				current_content = path.read_text()
			if current_content == content:
				return path  # Skip writing, content is the same
		except Exception as exc:
			logging.warning("Can't read file %s: %s", path.absolute(), exc)
			# If we can't read the file for any reason, just write it
			pass

	path.parent.mkdir(exist_ok=True, parents=True)
	if isinstance(content, bytes):
		path.write_bytes(content)
	else:
		path.write_text(content)
	return path


class Codegen:
	cfg: CodegenConfig
	routes: RouteTree

	def __init__(self, routes: RouteTree, config: CodegenConfig) -> None:
		self.cfg = config
		self.routes = routes
		self._copied_files: set[Path] = set()

	@property
	def output_folder(self):
		return self.cfg.pulse_path

	@property
	def assets_folder(self):
		return self.output_folder / "assets"

	def generate_all(
		self,
		server_address: str,
		internal_server_address: str | None = None,
		api_prefix: str = "",
		connection_status: "ConnectionStatusConfig | None" = None,
	):
		# Ensure generated files are gitignored
		ensure_gitignore_has(self.cfg.web_root, f"app/{self.cfg.pulse_dir}/")

		self._copied_files = set()

		# Copy all registered local files to the assets directory
		self._copy_local_files()

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
				*(
					self.generate_route(route, server_address=server_address)
					for route in self.routes.flat_tree.values()
				),
			]
		)
		generated_files.update(self._copied_files)

		# Clean up any remaining files that are not part of the generated files
		for path in self.output_folder.rglob("*"):
			if path.is_file() and path not in generated_files:
				try:
					path.unlink()
					logger.debug(f"Removed stale file: {path}")
				except Exception as e:
					logger.warning(f"Could not remove stale file {path}: {e}")

	def _copy_local_files(self) -> None:
		"""Copy all registered local assets to the assets directory.

		Uses the unified asset registry which tracks local files from both
		Import objects and DynamicImport expressions.
		"""
		assets = get_registered_assets()

		if not assets:
			return

		self.assets_folder.mkdir(parents=True, exist_ok=True)

		for asset in assets:
			dest_path = self.assets_folder / asset.asset_filename

			# Copy file if source exists
			if asset.source_path.exists():
				self._copied_files.add(dest_path)
				try:
					content = asset.source_path.read_bytes()
				except OSError as exc:
					logger.warning(
						"Can't read asset %s: %s",
						asset.source_path,
						exc,
					)
					continue
				write_file_if_changed(dest_path, content)

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
		"""Generate TypeScript code for the route manifest."""
		routes_str = self._render_routes_ts(self.routes.tree, indent_level=0)
		loaders_str = self._render_route_loaders()
		content = str(
			ROUTES_MANIFEST_TEMPLATE.render_unicode(
				routes_str=routes_str,
				loaders_str=loaders_str,
			)
		)
		return write_file_if_changed(self.output_folder / "routes.ts", content)

	def _render_routes_ts(
		self, routes: Sequence[Route | Layout], indent_level: int
	) -> str:
		def render_node(node: Route | Layout, indent: int) -> str:
			ind = "  " * indent
			lines: list[str] = [f"{ind}{{"]
			lines.append(f'{ind}  id: "{node.unique_path()}",')
			if isinstance(node, Layout):
				lines.append(
					f'{ind}  file: "{self.cfg.pulse_dir}/layouts/{node.file_path()}",'
				)
			else:
				if node.is_index:
					lines.append(f"{ind}  index: true,")
				else:
					lines.append(f'{ind}  path: "{node.path}",')
				lines.append(
					f'{ind}  file: "{self.cfg.pulse_dir}/routes/{node.file_path()}",'
				)
			if node.children:
				lines.append(f"{ind}  children: [")
				for idx, child in enumerate(node.children):
					lines.append(render_node(child, indent + 2))
					if idx != len(node.children) - 1:
						lines.append(f"{ind}  ,")
				lines.append(f"{ind}  ],")
			lines.append(f"{ind}}}")
			return "\n".join(lines)

		ind = "  " * indent_level
		out: list[str] = [f"{ind}["]
		for index, route in enumerate(routes):
			out.append(render_node(route, indent_level + 1))
			if index != len(routes) - 1:
				out.append(f"{ind}  ,")
		out.append(f"{ind}]")
		return "\n".join(out)

	def generate_route(
		self,
		route: Route | Layout,
		server_address: str,
	):
		route_file_path = route.file_path()
		if isinstance(route, Layout):
			output_path = self.output_folder / "layouts" / route_file_path
			full_route_path = f"layouts/{route_file_path}"
		else:
			output_path = self.output_folder / "routes" / route_file_path
			full_route_path = f"routes/{route_file_path}"

		content = generate_route(
			path=route.unique_path(),
			route_file_path=full_route_path,
		)
		return write_file_if_changed(output_path, content)

	def _render_route_loaders(self) -> str:
		lines: list[str] = ["{"]
		for key, node in self.routes.flat_tree.items():
			if isinstance(node, Layout):
				import_path = f"./layouts/{node.file_path()}"
			else:
				import_path = f"./routes/{node.file_path()}"
			lines.append(f'  "{key}": () => import("{import_path}"),')
		lines.append("}")
		return "\n".join(lines)
