"""Unified asset registry for local files that need copying.

Used by both Import (static imports) and DynamicImport (inline dynamic imports)
to track local files that should be copied to the assets folder during codegen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pulse.transpiler.id import next_id


@dataclass(slots=True)
class LocalAsset:
	"""A local file registered for copying to assets."""

	source_path: Path
	id: str

	@property
	def asset_filename(self) -> str:
		"""Filename in assets folder: stem_id.ext"""
		return f"{self.source_path.stem}_{self.id}{self.source_path.suffix}"


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
