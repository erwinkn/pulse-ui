"""Tests for Import path resolution and local file handling."""

from pathlib import Path

import pytest
from pulse.transpiler_v2.imports import (
	Import,
	clear_import_registry,
	is_absolute_path,
	is_local_path,
	is_relative_path,
	resolve_js_file,
	resolve_local_path,
)


class TestPathHelpers:
	"""Test the path classification helper functions."""

	def test_is_relative_path_with_dot_slash(self):
		"""Paths starting with ./ are relative."""
		assert is_relative_path("./utils")
		assert is_relative_path("./components/Button")
		assert is_relative_path("./styles.css")

	def test_is_relative_path_with_dot_dot_slash(self):
		"""Paths starting with ../ are relative."""
		assert is_relative_path("../utils")
		assert is_relative_path("../../shared/config")

	def test_is_relative_path_rejects_package_paths(self):
		"""Package paths are not relative."""
		assert not is_relative_path("react")
		assert not is_relative_path("@mantine/core")
		assert not is_relative_path("lodash/debounce")

	def test_is_relative_path_rejects_absolute(self):
		"""Absolute paths are not relative."""
		assert not is_relative_path("/absolute/path")
		assert not is_relative_path("/Users/test/file.ts")

	def test_is_absolute_path(self):
		"""Paths starting with / are absolute."""
		assert is_absolute_path("/absolute/path")
		assert is_absolute_path("/Users/test/project/src/utils.ts")
		assert is_absolute_path("/tmp/styles.css")

	def test_is_absolute_path_rejects_relative(self):
		"""Relative paths are not absolute."""
		assert not is_absolute_path("./utils")
		assert not is_absolute_path("../config")

	def test_is_absolute_path_rejects_package_paths(self):
		"""Package paths are not absolute."""
		assert not is_absolute_path("react")
		assert not is_absolute_path("@mantine/core")

	def test_is_local_path_includes_relative(self):
		"""Local paths include relative paths."""
		assert is_local_path("./utils")
		assert is_local_path("../shared")

	def test_is_local_path_includes_absolute(self):
		"""Local paths include absolute paths."""
		assert is_local_path("/absolute/path")
		assert is_local_path("/Users/test/file.ts")

	def test_is_local_path_excludes_packages(self):
		"""Package paths are not local."""
		assert not is_local_path("react")
		assert not is_local_path("@mantine/core")
		assert not is_local_path("lodash/debounce")


class TestResolveJsFile:
	"""Test JS file resolution following ESM conventions."""

	def test_resolve_existing_file_with_extension(self, tmp_path: Path):
		"""File with extension that exists is returned as-is."""
		file = tmp_path / "utils.ts"
		file.write_text("export const x = 1;")

		result = resolve_js_file(file)
		assert result == file

	def test_resolve_without_extension_finds_ts(self, tmp_path: Path):
		"""Path without extension resolves to .ts file."""
		ts_file = tmp_path / "utils.ts"
		ts_file.write_text("export const x = 1;")

		result = resolve_js_file(tmp_path / "utils")
		assert result == ts_file

	def test_resolve_without_extension_finds_tsx(self, tmp_path: Path):
		"""Path without extension resolves to .tsx file."""
		tsx_file = tmp_path / "Component.tsx"
		tsx_file.write_text("export const C = () => <div />;")

		result = resolve_js_file(tmp_path / "Component")
		assert result == tsx_file

	def test_resolve_without_extension_finds_js(self, tmp_path: Path):
		"""Path without extension resolves to .js file."""
		js_file = tmp_path / "legacy.js"
		js_file.write_text("module.exports = {};")

		result = resolve_js_file(tmp_path / "legacy")
		assert result == js_file

	def test_resolve_without_extension_finds_jsx(self, tmp_path: Path):
		"""Path without extension resolves to .jsx file."""
		jsx_file = tmp_path / "OldComponent.jsx"
		jsx_file.write_text("export const C = () => <div />;")

		result = resolve_js_file(tmp_path / "OldComponent")
		assert result == jsx_file

	def test_resolve_prefers_ts_over_js(self, tmp_path: Path):
		"""When both .ts and .js exist, prefers .ts (ESM convention order)."""
		ts_file = tmp_path / "utils.ts"
		js_file = tmp_path / "utils.js"
		ts_file.write_text("export const x = 1;")
		js_file.write_text("exports.x = 1;")

		result = resolve_js_file(tmp_path / "utils")
		assert result == ts_file

	def test_resolve_without_extension_finds_index_ts(self, tmp_path: Path):
		"""Directory path resolves to index.ts inside it."""
		subdir = tmp_path / "components"
		subdir.mkdir()
		index_file = subdir / "index.ts"
		index_file.write_text("export * from './Button';")

		result = resolve_js_file(subdir)
		assert result == index_file

	def test_resolve_without_extension_finds_index_tsx(self, tmp_path: Path):
		"""Directory path resolves to index.tsx inside it."""
		subdir = tmp_path / "ui"
		subdir.mkdir()
		index_file = subdir / "index.tsx"
		index_file.write_text("export const UI = () => <div />;")

		result = resolve_js_file(subdir)
		assert result == index_file

	def test_resolve_nonexistent_returns_none(self, tmp_path: Path):
		"""Non-existent path returns None."""
		result = resolve_js_file(tmp_path / "nonexistent")
		assert result is None

	def test_resolve_css_file_with_extension(self, tmp_path: Path):
		"""CSS file with extension is returned as-is when it exists."""
		css_file = tmp_path / "styles.css"
		css_file.write_text("body { margin: 0; }")

		result = resolve_js_file(css_file)
		assert result == css_file


class TestResolveLocalPath:
	"""Test local path resolution for both relative and absolute paths."""

	def test_resolve_relative_path_with_extension(self, tmp_path: Path):
		"""Relative path with extension resolves correctly."""
		css_file = tmp_path / "styles.css"
		css_file.write_text("body { margin: 0; }")
		caller = tmp_path / "index.py"

		result = resolve_local_path("./styles.css", caller)
		assert result == css_file

	def test_resolve_relative_path_without_extension(self, tmp_path: Path):
		"""Relative path without extension uses JS resolution."""
		ts_file = tmp_path / "utils.ts"
		ts_file.write_text("export const x = 1;")
		caller = tmp_path / "index.py"

		result = resolve_local_path("./utils", caller)
		assert result == ts_file

	def test_resolve_relative_path_parent_dir(self, tmp_path: Path):
		"""Relative path with ../ resolves correctly."""
		utils_file = tmp_path / "shared" / "utils.ts"
		utils_file.parent.mkdir(parents=True)
		utils_file.write_text("export const x = 1;")
		caller = tmp_path / "src" / "app.py"

		result = resolve_local_path("../shared/utils", caller)
		assert result == utils_file

	def test_resolve_absolute_path_with_extension(self, tmp_path: Path):
		"""Absolute path with extension resolves directly."""
		css_file = tmp_path / "absolute.css"
		css_file.write_text("body { margin: 0; }")

		result = resolve_local_path(str(css_file), caller=None)
		assert result == css_file

	def test_resolve_absolute_path_without_extension(self, tmp_path: Path):
		"""Absolute path without extension uses JS resolution."""
		ts_file = tmp_path / "config.ts"
		ts_file.write_text("export default {};")

		# Pass the path without extension
		result = resolve_local_path(str(tmp_path / "config"), caller=None)
		assert result == ts_file

	def test_resolve_relative_without_caller_returns_none(self):
		"""Relative path without caller returns None."""
		result = resolve_local_path("./utils", caller=None)
		assert result is None

	def test_resolve_package_path_returns_none(self, tmp_path: Path):
		"""Package paths return None."""
		caller = tmp_path / "index.py"
		result = resolve_local_path("react", caller)
		assert result is None

	def test_resolve_nonexistent_file_returns_path_anyway(self, tmp_path: Path):
		"""Non-existent file still returns the resolved path (for generated/future files)."""
		caller = tmp_path / "index.py"
		result = resolve_local_path("./nonexistent.css", caller)
		assert result == tmp_path / "nonexistent.css"

	def test_resolve_nonexistent_without_extension_returns_base_path(
		self, tmp_path: Path
	):
		"""Non-existent path without extension returns the base path as fallback."""
		caller = tmp_path / "index.py"
		result = resolve_local_path("./nonexistent", caller)
		assert result == tmp_path / "nonexistent"

	def test_resolve_absolute_nonexistent_returns_path(self, tmp_path: Path):
		"""Absolute path to non-existent file still returns the path."""
		result = resolve_local_path(str(tmp_path / "nonexistent.css"), caller=None)
		assert result == tmp_path / "nonexistent.css"


class TestImportLocalFiles:
	"""Test Import class with local file paths."""

	def setup_method(self):
		"""Clear the import registry before each test."""
		clear_import_registry()

	def test_import_relative_css_sets_source_path(self, tmp_path: Path):
		"""Import with relative CSS path sets source_path."""
		css_file = tmp_path / "styles.css"
		css_file.write_text("body { margin: 0; }")

		# Create a caller file in the same directory
		caller = tmp_path / "test_caller.py"
		caller.write_text("")

		# Create import with explicit caller depth simulation
		# We need to bypass the automatic caller detection
		import pulse.transpiler_v2.imports as imports_module

		original_caller_file = imports_module.caller_file
		imports_module.caller_file = lambda depth: caller

		try:
			imp = Import("", "./styles.css", kind="side_effect")
			assert imp.is_local
			assert imp.source_path == css_file
			assert str(css_file) in imp.src
		finally:
			imports_module.caller_file = original_caller_file

	def test_import_absolute_path_sets_source_path(self, tmp_path: Path):
		"""Import with absolute path sets source_path."""
		css_file = tmp_path / "absolute.css"
		css_file.write_text("body { margin: 0; }")

		imp = Import("", str(css_file), kind="side_effect")
		assert imp.is_local
		assert imp.source_path == css_file

	def test_import_absolute_js_without_extension_resolves(self, tmp_path: Path):
		"""Import with absolute JS path without extension resolves correctly."""
		ts_file = tmp_path / "utils.ts"
		ts_file.write_text("export const x = 1;")

		# Import without extension
		imp = Import("utils", str(tmp_path / "utils"), kind="namespace")
		assert imp.is_local
		assert imp.source_path == ts_file
		assert imp.source_path is not None
		assert imp.source_path.suffix == ".ts"

	def test_import_package_not_local(self):
		"""Import from package is not local."""
		imp = Import("useState", "react")
		assert not imp.is_local
		assert imp.source_path is None

	def test_import_scoped_package_not_local(self):
		"""Import from scoped package is not local."""
		imp = Import("Button", "@mantine/core")
		assert not imp.is_local
		assert imp.source_path is None

	def test_asset_filename_uses_id(self, tmp_path: Path):
		"""asset_filename() uses import ID for uniqueness."""
		css_file = tmp_path / "styles.css"
		css_file.write_text("body { margin: 0; }")

		imp = Import("", str(css_file), kind="side_effect")

		filename = imp.asset_filename()
		assert filename.startswith("styles_")
		assert filename.endswith(".css")
		assert imp.id in filename

	def test_asset_filename_preserves_extension(self, tmp_path: Path):
		"""asset_filename() preserves the original extension."""
		ts_file = tmp_path / "Component.tsx"
		ts_file.write_text("export const C = () => <div />;")

		imp = Import("Component", str(ts_file), kind="default")

		filename = imp.asset_filename()
		assert filename.endswith(".tsx")

	def test_asset_filename_raises_for_package_import(self):
		"""asset_filename() raises for non-local imports."""
		imp = Import("useState", "react")

		with pytest.raises(ValueError, match="non-local import"):
			imp.asset_filename()

	def test_multiple_local_imports_get_unique_filenames(self, tmp_path: Path):
		"""Multiple local imports get unique asset filenames."""
		file1 = tmp_path / "dir1" / "utils.ts"
		file2 = tmp_path / "dir2" / "utils.ts"
		file1.parent.mkdir(parents=True)
		file2.parent.mkdir(parents=True)
		file1.write_text("export const x = 1;")
		file2.write_text("export const y = 2;")

		imp1 = Import("utils1", str(file1), kind="namespace")
		imp2 = Import("utils2", str(file2), kind="namespace")

		assert imp1.asset_filename() != imp2.asset_filename()
