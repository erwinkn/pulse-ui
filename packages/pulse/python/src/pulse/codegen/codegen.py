import hashlib
import json
import logging
import shutil
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
from pulse.routing import Layout, Route, RouteTree
from pulse.transpiler import get_registered_imports

if TYPE_CHECKING:
	from pulse.app import ConnectionStatusConfig

logger = logging.getLogger(__file__)


def _compute_file_hash(content: str) -> str:
	"""Compute SHA256 hash of file content."""
	return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ChecksumsManager:
	"""Manages checksums for detecting changed files in managed mode."""

	checksums_path: Path
	checksums: dict[str, str]

	def __init__(self, checksums_path: Path):
		self.checksums_path = checksums_path
		self.checksums = {}
		self.load()

	def load(self) -> None:
		"""Load checksums from .checksums.json if it exists."""
		if self.checksums_path.exists():
			try:
				content = self.checksums_path.read_text()
				self.checksums = json.loads(content)
			except (json.JSONDecodeError, OSError):
				# If corrupted or unreadable, start fresh
				self.checksums = {}
		else:
			self.checksums = {}

	def save(self) -> None:
		"""Save checksums to .checksums.json."""
		self.checksums_path.parent.mkdir(parents=True, exist_ok=True)
		self.checksums_path.write_text(
			json.dumps(self.checksums, indent=2, sort_keys=True)
		)

	def should_write(self, file_path: str, content: str) -> bool:
		"""Check if file has changed since last generation."""
		new_hash = _compute_file_hash(content)
		old_hash = self.checksums.get(file_path)
		if old_hash != new_hash:
			self.checksums[file_path] = new_hash
			return True
		return False

	def check_user_edits(self, file_path: str, full_path: Path) -> bool:
		"""Check if a file was edited by the user (disk content differs from stored checksum).

		Returns True if user edits detected, False otherwise.
		"""
		if not full_path.exists():
			return False

		stored_hash = self.checksums.get(file_path)
		if stored_hash is None:
			# No previous hash stored, so no edits to detect
			return False

		try:
			disk_content = full_path.read_text()
			disk_hash = _compute_file_hash(disk_content)
			return disk_hash != stored_hash
		except Exception:
			# If we can't read the file, assume no edits detected
			return False

	def cleanup_old_files(self, current_files: set[str]) -> None:
		"""Remove checksums for files that no longer exist."""
		old_files = set(self.checksums.keys()) - current_files
		for file_path in old_files:
			del self.checksums[file_path]


@dataclass
class CodegenConfig:
	"""
	Configuration for code generation.

	Attributes:
	    web_dir (str): Root directory for the web output.
	    pulse_dir (str): Name of the Pulse app directory.
	    pulse_path (Path): Full path to the generated app directory.
	    mode (str): Code generation mode - 'managed' or 'exported'.
	"""

	web_dir: Path | str = "web"
	"""Root directory for the web output."""

	pulse_dir: Path | str = "pulse"
	"""Name of the Pulse app directory."""

	base_dir: Path | None = None
	"""Directory containing the user's app file. If not provided, resolved from env."""

	mode: str = "managed"
	"""Code generation mode: 'managed' (.pulse/web/, gitignored) or 'exported' (web/, committed)."""

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
		"""Absolute path to the web root directory (e.g. `<app_dir>/pulse-web`).

		In managed mode, returns .pulse/<web_dir>/
		In exported mode, returns <web_dir>/
		"""
		wd = Path(self.web_dir)
		if wd.is_absolute():
			return wd

		base = self.resolved_base_dir
		if self.mode == "managed":
			return base / ".pulse" / wd
		else:  # exported mode
			return base / wd

	@property
	def pulse_path(self) -> Path:
		"""Full path to the generated app directory."""
		return self.web_root / "app" / self.pulse_dir


def write_file_if_changed(
	path: Path, content: str, checksums_manager: ChecksumsManager | None = None
) -> Path:
	"""Write content to file only if it has changed.

	If checksums_manager is provided (managed mode), uses hash comparison.
	Otherwise uses direct content comparison (exported mode).
	Detects and warns about user edits in managed mode.
	"""
	force_write = False

	if checksums_manager:
		# Managed mode: use checksums for change detection
		# Store relative path from checksums file location for deterministic keys
		file_key = str(path.relative_to(path.parent.parent.parent))

		# Check for user edits before writing
		if checksums_manager.check_user_edits(file_key, path):
			logger.warning(
				f"File {path.absolute()} was edited by user. Overwriting with generated content."
			)
			force_write = True

		# Only skip writing if content is unchanged AND no user edits detected
		if not force_write and not checksums_manager.should_write(file_key, content):
			return path  # Skip writing, content unchanged
		elif force_write:
			# Update checksum after forced overwrite
			new_hash = _compute_file_hash(content)
			checksums_manager.checksums[file_key] = new_hash

	else:
		# Exported mode: direct content comparison
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
		self._copied_files: set[Path] = set()
		self._checksums_manager: ChecksumsManager | None = None

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
		# Ensure generated files are gitignored based on mode
		if self.cfg.mode == "managed":
			# In managed mode, ignore .pulse directory at the base level
			ensure_gitignore_has(self.cfg.resolved_base_dir, ".pulse/")
			# Initialize checksums manager for change detection
			checksums_path = self.cfg.resolved_base_dir / ".pulse" / ".checksums.json"
			checksums_manager = ChecksumsManager(checksums_path)
		else:
			# In exported mode, ignore app folder within web_root
			ensure_gitignore_has(self.cfg.web_root, f"app/{self.cfg.pulse_dir}/")
			checksums_manager = None

		self._copied_files = set()
		self._checksums_manager = checksums_manager

		# Copy all registered local files to the assets directory
		asset_import_paths = self._copy_local_files()

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
					self.generate_route(
						route,
						server_address=server_address,
						asset_import_paths=asset_import_paths,
					)
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

		# Save checksums in managed mode
		if checksums_manager:
			# Clean up old checksums for deleted files
			generated_file_keys = {
				str(p.relative_to(p.parent.parent.parent)) for p in generated_files
			}
			checksums_manager.cleanup_old_files(generated_file_keys)
			checksums_manager.save()

	def _copy_local_files(self) -> dict[str, str]:
		"""Copy all registered local files to the assets directory.

		Collects all Import objects with is_local=True and copies their
		source files to the assets folder, returning an import path mapping.
		"""
		imports = get_registered_imports()
		local_imports = [imp for imp in imports if imp.is_local]

		if not local_imports:
			return {}

		self.assets_folder.mkdir(parents=True, exist_ok=True)
		asset_import_paths: dict[str, str] = {}

		for imp in local_imports:
			if imp.source_path is None:
				continue

			asset_filename = imp.asset_filename()
			dest_path = self.assets_folder / asset_filename

			# Copy file if source exists
			if imp.source_path.exists():
				shutil.copy2(imp.source_path, dest_path)
				self._copied_files.add(dest_path)
				logger.debug(f"Copied {imp.source_path} -> {dest_path}")

			# Store just the asset filename - the relative path is computed per-route
			asset_import_paths[imp.src] = asset_filename

		return asset_import_paths

	def _compute_asset_prefix(self, route_file_path: str) -> str:
		"""Compute the relative path prefix from a route file to the assets folder.

		Args:
			route_file_path: The route's file path (e.g., "users/_id_xxx.jsx")

		Returns:
			The relative path prefix (e.g., "../assets/" or "../../assets/")
		"""
		# Count directory depth: each "/" in the path adds one level
		depth = route_file_path.count("/")
		# Add 1 for the routes/ or layouts/ folder itself
		return "../" * (depth + 1) + "assets/"

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
		return write_file_if_changed(
			self.output_folder / "_layout.tsx",
			content,
			self._checksums_manager,
		)

	def generate_routes_ts(self):
		"""Generate TypeScript code for the routes configuration."""
		routes_str = self._render_routes_ts(self.routes.tree, 2)
		content = str(
			ROUTES_CONFIG_TEMPLATE.render_unicode(
				routes_str=routes_str,
				pulse_dir=self.cfg.pulse_dir,
			)
		)
		return write_file_if_changed(
			self.output_folder / "routes.ts",
			content,
			self._checksums_manager,
		)

	def generate_routes_runtime_ts(self):
		"""Generate a runtime React Router object tree for server-side matching."""
		routes_str = self._render_routes_runtime(self.routes.tree, indent_level=0)
		content = str(
			ROUTES_RUNTIME_TEMPLATE.render_unicode(
				routes_str=routes_str,
			)
		)
		return write_file_if_changed(
			self.output_folder / "routes.runtime.ts",
			content,
			self._checksums_manager,
		)

	def _render_routes_ts(
		self, routes: Sequence[Route | Layout], indent_level: int
	) -> str:
		"""Generate routes with dynamic imports for code splitting."""
		lines: list[str] = []
		indent_str = "  " * indent_level
		for route in routes:
			if isinstance(route, Layout):
				# Layouts don't have a path in the route tree
				lines.append(f"{indent_str}{{")
				lines.append(f'{indent_str}  path: "",')
				file_path = f"{self.cfg.pulse_dir}/layouts/{route.file_path()}"
				lines.append(
					f'{indent_str}  component: () => import("{file_path}").then(m => ({{ default: m.default }})),'
				)
				if route.children:
					children_str = self._render_routes_ts(
						route.children, indent_level + 1
					)
					lines.append(f"{indent_str}  children: [")
					lines.append(children_str)
					lines.append(f"{indent_str}  ],")
				lines.append(f"{indent_str}}},")
			else:
				# Routes have paths
				path = route.path if not route.is_index else ""
				lines.append(f"{indent_str}{{")
				lines.append(f'{indent_str}  path: "{path}",')
				file_path = f"{self.cfg.pulse_dir}/routes/{route.file_path()}"
				lines.append(
					f'{indent_str}  component: () => import("{file_path}").then(m => ({{ default: m.default }})),'
				)
				if route.children:
					children_str = self._render_routes_ts(
						route.children, indent_level + 1
					)
					lines.append(f"{indent_str}  children: [")
					lines.append(children_str)
					lines.append(f"{indent_str}  ],")
				lines.append(f"{indent_str}}},")
		return "\n".join(lines)

	def generate_route(
		self,
		route: Route | Layout,
		server_address: str,
		asset_import_paths: dict[str, str],
	):
		route_file_path = route.file_path()
		if isinstance(route, Layout):
			output_path = self.output_folder / "layouts" / route_file_path
		else:
			output_path = self.output_folder / "routes" / route_file_path

		# Compute asset prefix based on route depth
		asset_prefix = self._compute_asset_prefix(route_file_path)

		content = generate_route(
			path=route.unique_path(),
			asset_filenames=asset_import_paths,
			asset_prefix=asset_prefix,
		)
		return write_file_if_changed(
			output_path,
			content,
			self._checksums_manager,
		)

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
