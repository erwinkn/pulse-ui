"""Unified asset registry for local files that need copying.

Used by both Import (static imports) and DynamicImport (inline dynamic imports)
to track local files that should be copied to the assets folder during codegen.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path

from pulse.transpiler.emit_context import EmitContext
from pulse.transpiler.id import next_id

_CSS_MODULE_EXTS = (
	".css",
	".scss",
	".sass",
	".less",
	".styl",
	".stylus",
)


@dataclass(slots=True)
class LocalAsset:
	"""A local file registered for copying to assets."""

	source_path: Path
	id: str

	@property
	def asset_filename(self) -> str:
		"""Filename in assets folder: stem_id.ext (preserve .module.*)."""
		name = self.source_path.name
		for ext in _CSS_MODULE_EXTS:
			module_suffix = f".module{ext}"
			if name.endswith(module_suffix):
				base = name[: -len(module_suffix)]
				return f"{base}_{self.id}{module_suffix}"
		return f"{self.source_path.stem}_{self.id}{self.source_path.suffix}"

	def import_path(self) -> str:
		"""Get import path for this asset.

		If EmitContext is set, returns path relative to route file.
		Otherwise returns the absolute source path (useful for tests/debugging).
		"""
		ctx = EmitContext.get()
		if ctx is None:
			return str(self.source_path)
		# Compute relative path from route file directory to asset
		# route_file_path is like "routes/users/index.tsx"
		# asset is in "assets/{asset_filename}"
		route_dir = posixpath.dirname(ctx.route_file_path)
		asset_path = f"assets/{self.asset_filename}"
		return posixpath.relpath(asset_path, route_dir)


# Registry keyed by resolved source_path (dedupes same file)
_ASSET_REGISTRY: dict[Path, LocalAsset] = {}


def register_local_asset(source_path: Path) -> LocalAsset:
	"""Register a local file for copying. Returns existing if already registered."""
	if source_path in _ASSET_REGISTRY:
		return _ASSET_REGISTRY[source_path]
	asset = LocalAsset(source_path, next_id())
	_ASSET_REGISTRY[source_path] = asset
	return asset


def get_registered_assets() -> list[LocalAsset]:
	"""Get all registered local assets."""
	return list(_ASSET_REGISTRY.values())


def clear_asset_registry() -> None:
	"""Clear asset registry (for tests)."""
	_ASSET_REGISTRY.clear()
