"""
Tests for Import functionality: as dependency and as decorator.
"""

# pyright: reportPrivateUsage=false

from pathlib import Path
from typing import Any

import pytest
from pulse.transpiler import (
	TranspileError,
	clear_function_cache,
	clear_import_registry,
	emit,
	import_,
	javascript,
)
from pulse.transpiler.imports import (
	Import,
	get_registered_imports,
	is_absolute_path,
	is_local_path,
	is_relative_path,
	resolve_js_file,
	resolve_local_path,
)


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()  # Also clears import and asset registries
	yield
	clear_function_cache()


# =============================================================================
# Import as Dependency
# =============================================================================


class TestImportDependency:
	"""Test Import as a transpiler dependency (ToExpr, EmitsCall, EmitsGetattr)."""

	def test_import_as_value(self):
		"""Import used as a value resolves to Identifier with unique js_name."""
		useState = Import("useState", "react")  # ID 1

		@javascript
		def use_hook() -> Any:  # ID 2
			return useState

		fn = use_hook.transpile()
		code = emit(fn)
		assert code == "function use_hook_2() {\nreturn useState_1;\n}"

	def test_import_in_call(self):
		"""Import called as function (non-jsx) produces Call node."""
		useState = Import("useState", "react")  # ID 1

		@javascript
		def use_hook() -> Any:  # ID 2
			return useState(0)

		fn = use_hook.transpile()
		code = emit(fn)
		assert code == "function use_hook_2() {\nreturn useState_1(0);\n}"

	def test_import_jsx_call(self):
		"""Jsx wrapping an Import produced an Element."""
		from pulse.transpiler.nodes import Jsx

		Button = Jsx(Import("Button", "@mantine/core"))  # Import ID 1, Jsx ID 2

		@javascript
		def render() -> Any:  # ID 3
			return Button("Click me", disabled=True)

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_3() {\nreturn <Button_1 disabled={true}>{"Click me"}</Button_1>;\n}'
		)

	def test_import_jsx_call_with_key(self):
		"""Jsx wrapping an Import with key prop extracts key."""
		from pulse.transpiler.nodes import Jsx

		# Local path creates asset (ID 1), then Import (ID 2), then Jsx (ID 3)
		Item = Jsx(Import("Item", "./components"))

		@javascript
		def render() -> Any:  # ID 4
			return Item("text", key="item-1")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_4() {\nreturn <Item_2 key="item-1">{"text"}</Item_2>;\n}'
		)

	def test_import_jsx_call_no_children(self):
		"""Jsx wrapping an Import call with only props, no children."""
		from pulse.transpiler.nodes import Jsx

		# Local path creates asset (ID 1), then Import (ID 2), then Jsx (ID 3)
		Icon = Jsx(Import("Icon", "./icons"))

		@javascript
		def render() -> Any:  # ID 4
			return Icon(name="check")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_4() {\nreturn <Icon_2 name="check" />;\n}'

	def test_import_attribute_access(self):
		"""Import with attribute access produces Member."""
		React = Import("react")  # ID 1

		@javascript
		def get_version() -> Any:  # ID 2
			return React.version

		fn = get_version.transpile()
		code = emit(fn)
		assert code == "function get_version_2() {\nreturn react_1.version;\n}"

	def test_import_method_call(self):
		"""Import method call chains correctly."""
		router = Import("next/router")  # ID 1

		@javascript
		def navigate() -> Any:  # ID 2
			return router.push("/home")

		fn = navigate.transpile()
		code = emit(fn)
		assert code == 'function navigate_2() {\nreturn next_router_1.push("/home");\n}'

	def test_import_deduplication(self):
		"""Same import used twice gets same ID."""
		useState = Import("useState", "react")  # ID 1
		useEffect = Import("useEffect", "react")  # ID 2

		@javascript
		def both(x: Any) -> Any:  # ID 3
			return useState(x) + useEffect(x)  # pyright: ignore[reportOperatorIssue]

		fn = both.transpile()
		code = emit(fn)
		assert code == "function both_3(x) {\nreturn useState_1(x) + useEffect_2(x);\n}"

	def test_import_same_name_different_src(self):
		"""Same name from different sources get different IDs."""
		foo1 = Import("foo", "package-a")
		foo2 = Import("foo", "package-b")
		# They should have different IDs
		assert foo1.id != foo2.id

	def test_import_registry(self):
		"""get_registered_imports returns all created imports."""
		_ = Import("useState", "react")
		_ = Import("Button", "@mantine/core")
		_ = Import("MyType", "./types", is_type=True)

		imports = get_registered_imports()
		assert len(imports) == 3
		names = {imp.name for imp in imports}
		assert names == {"useState", "Button", "MyType"}

	def test_import_type_only_merged(self):
		"""Type-only import merged with regular becomes regular."""
		type_only = Import("Foo", "./types", is_type=True)
		assert type_only.is_type is True

		regular = Import("Foo", "./types")
		# Both now point to regular
		assert type_only.is_type is False
		assert regular.is_type is False

	def test_import_before_constraints_merged(self):
		"""Before constraints are merged across duplicate imports."""
		a = Import("A", "pkg", before=("x",))
		assert a.before == ("x",)

		b = Import("A", "pkg", before=("y", "z"))
		# Both have merged before
		assert set(a.before) == {"x", "y", "z"}
		assert set(b.before) == {"x", "y", "z"}

	def test_import_version(self):
		"""Import can specify a version requirement."""
		imp = Import("foo", "package-a", version="^1.0.0")
		assert imp.version == "^1.0.0"

	def test_import_version_merged(self):
		"""Version requirement is merged across duplicate imports."""
		a = Import("A", "pkg")
		assert a.version is None

		b = Import("A", "pkg", version="^1.0.0")
		assert a.version == "^1.0.0"
		assert b.version == "^1.0.0"

		_ = Import("A", "pkg", version="^1.1.0")
		# We now pick the more specific version
		assert a.version == "^1.1.0"


# =============================================================================
# Import as Decorator
# =============================================================================


class TestImportAsDecorator:
	"""Test Import used as a decorator."""

	def test_import_decorator_returns_signature(self):
		"""@Import decorating a function returns a Signature wrapping the Import."""
		from pulse.transpiler.imports import Import
		from pulse.transpiler.nodes import Signature

		clsx_import = Import("clsx")

		@clsx_import.as_
		def clsx(*args: str) -> str: ...

		# clsx should be a Signature wrapping the Import
		assert isinstance(clsx, Signature)
		assert clsx.expr is clsx_import

	def test_import_decorator_call_still_works(self):
		"""Import decorated can still be called to build expressions."""
		from pulse.transpiler.imports import Import
		from pulse.transpiler.nodes import Call

		clsx_import = Import("clsx")

		@clsx_import.as_
		def clsx(*args: str) -> str: ...

		# Calling should produce a Call node
		result = clsx("a", "b")
		assert isinstance(result, Call)
		assert emit(result) == 'clsx_1("a", "b")'

	def test_import_jsx_decorator_produces_element(self):
		"""Jsx wrapping an Import used as decorator produces Element on call."""
		from pulse.transpiler.imports import Import
		from pulse.transpiler.nodes import Element, Jsx

		# Use Jsx(Import) as a decorator
		button_jsx = Jsx(Import("Button", "@ui/button"))

		@button_jsx.as_
		def Button(label: str) -> None: ...

		# Calling should produce an Element
		result = Button("Click")
		assert isinstance(result, Element)
		assert result.tag is button_jsx.expr
		assert result.children == ["Click"]


class TestImportSingleArg:
	"""Test Import single-argument default form."""

	def test_import_single_arg_default_package(self):
		"""Import("react") creates a default import."""
		imp = Import("react")
		assert imp.kind == "default"
		assert imp.name == "react"
		assert imp.src == "react"
		assert imp.is_default is True
		assert imp.is_side_effect is False
		assert imp.asset is None

	def test_import_single_arg_default_local(self, tmp_path: Path):
		"""Import("./styles.css") resolves local assets and defaults."""
		css_file = tmp_path / "styles.css"
		css_file.write_text("body { margin: 0; }")

		caller = tmp_path / "test_caller.py"
		caller.write_text("")

		import pulse.transpiler.imports as imports_module

		original_caller_file = imports_module.caller_file
		imports_module.caller_file = lambda depth: caller

		try:
			imp = Import("./styles.css")
			assert imp.kind == "default"
			assert imp.name == "./styles.css"
			assert imp.is_local
			assert imp.asset is not None
			assert imp.asset.source_path == css_file
			assert str(css_file) in imp.src
		finally:
			imports_module.caller_file = original_caller_file

	def test_import_namespace_star(self):
		"""Import("*", "react") creates a namespace import."""
		imp = Import("*", "react")
		assert imp.kind == "namespace"
		assert imp.name == "react"
		assert imp.src == "react"
		assert imp.is_namespace is True

	def test_import_side_effect_flag(self):
		"""side_effect=True creates a side-effect import."""
		imp = Import("react", side_effect=True)
		assert imp.kind == "side_effect"
		assert imp.name == ""
		assert imp.src == "react"
		assert imp.is_side_effect is True

	def test_import_star_requires_source(self):
		"""Import("*") requires a source path."""
		with pytest.raises(TypeError, match="requires a source"):
			Import("*")

	def test_import_side_effect_rejects_name(self):
		"""side_effect cannot be combined with an explicit name."""
		with pytest.raises(
			TypeError, match="side_effect imports cannot specify a name"
		):
			Import("Foo", "pkg", side_effect=True)


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

	def test_import_relative_css_sets_asset(self, tmp_path: Path):
		"""Import with relative CSS path sets asset."""
		css_file = tmp_path / "styles.css"
		css_file.write_text("body { margin: 0; }")

		# Create a caller file in the same directory
		caller = tmp_path / "test_caller.py"
		caller.write_text("")

		# Create import with explicit caller depth simulation
		# We need to bypass the automatic caller detection
		import pulse.transpiler.imports as imports_module

		original_caller_file = imports_module.caller_file
		imports_module.caller_file = lambda depth: caller

		try:
			imp = Import("./styles.css", side_effect=True)
			assert imp.is_local
			assert imp.asset is not None
			assert imp.asset.source_path == css_file
			assert str(css_file) in imp.src
		finally:
			imports_module.caller_file = original_caller_file

	def test_import_absolute_path_sets_asset(self, tmp_path: Path):
		"""Import with absolute path sets asset."""
		css_file = tmp_path / "absolute.css"
		css_file.write_text("body { margin: 0; }")

		imp = Import(str(css_file), side_effect=True)
		assert imp.is_local
		assert imp.asset is not None
		assert imp.asset.source_path == css_file

	def test_import_absolute_js_without_extension_resolves(self, tmp_path: Path):
		"""Import with absolute JS path without extension resolves correctly."""
		ts_file = tmp_path / "utils.ts"
		ts_file.write_text("export const x = 1;")

		# Import without extension
		imp = Import("*", str(tmp_path / "utils"))
		assert imp.is_local
		assert imp.asset is not None
		assert imp.asset.source_path == ts_file
		assert imp.asset.source_path.suffix == ".ts"

	def test_import_package_not_local(self):
		"""Import from package is not local."""
		imp = Import("useState", "react")
		assert not imp.is_local
		assert imp.asset is None

	def test_import_scoped_package_not_local(self):
		"""Import from scoped package is not local."""
		imp = Import("Button", "@mantine/core")
		assert not imp.is_local
		assert imp.asset is None

	def test_asset_filename_uses_id(self, tmp_path: Path):
		"""asset.asset_filename uses asset ID for uniqueness."""
		css_file = tmp_path / "styles.css"
		css_file.write_text("body { margin: 0; }")

		imp = Import(str(css_file), side_effect=True)
		assert imp.asset is not None

		filename = imp.asset.asset_filename
		assert filename.startswith("styles_")
		assert filename.endswith(".css")
		assert imp.asset.id in filename

	def test_asset_filename_preserves_extension(self, tmp_path: Path):
		"""asset.asset_filename preserves the original extension."""
		ts_file = tmp_path / "Component.tsx"
		ts_file.write_text("export const C = () => <div />;")

		imp = Import(str(ts_file))
		assert imp.asset is not None

		filename = imp.asset.asset_filename
		assert filename.endswith(".tsx")

	@pytest.mark.parametrize(
		"ext",
		[
			".css",
			".scss",
			".sass",
			".less",
			".styl",
			".stylus",
		],
	)
	def test_asset_filename_preserves_css_module_suffix(self, tmp_path: Path, ext: str):
		"""CSS module assets keep .module.<ext> suffix intact."""
		css_file = tmp_path / f"foo.bar.module{ext}"
		css_file.write_text(".x { color: red; }")

		imp = Import(str(css_file))
		assert imp.asset is not None

		filename = imp.asset.asset_filename
		assert filename == f"foo.bar_{imp.asset.id}.module{ext}"

	def test_no_asset_for_package_import(self):
		"""Package imports have no asset."""
		imp = Import("useState", "react")
		assert imp.asset is None

	def test_multiple_local_imports_get_unique_filenames(self, tmp_path: Path):
		"""Multiple local imports get unique asset filenames."""
		file1 = tmp_path / "dir1" / "utils.ts"
		file2 = tmp_path / "dir2" / "utils.ts"
		file1.parent.mkdir(parents=True)
		file2.parent.mkdir(parents=True)
		file1.write_text("export const x = 1;")
		file2.write_text("export const y = 2;")

		imp1 = Import("*", str(file1))
		imp2 = Import("*", str(file2))

		assert imp1.asset is not None
		assert imp2.asset is not None
		assert imp1.asset.asset_filename != imp2.asset.asset_filename


class TestLazyImports:
	"""Test Import with lazy=True flag."""

	def setup_method(self):
		"""Clear registries before each test."""
		clear_function_cache()

	def test_import_lazy_flag_stored(self):
		"""Import stores the lazy flag correctly."""
		lazy_imp = Import("./Chart", lazy=True)
		eager_imp = Import("Button", "@mantine/core")

		assert lazy_imp.lazy is True
		assert lazy_imp.is_lazy is True
		assert eager_imp.lazy is False
		assert eager_imp.is_lazy is False

	def test_lazy_and_type_raises(self):
		"""Import with both lazy=True and is_type=True raises TranspileError."""
		with pytest.raises(TranspileError, match="lazy and type-only"):
			Import("Props", "./types", is_type=True, lazy=True)

	def test_lazy_import_separate_from_eager(self):
		"""Lazy and eager imports of same symbol are tracked separately."""
		eager = Import("./Chart")
		lazy = Import("./Chart", lazy=True)

		# They should have different IDs (separate registry entries)
		assert eager.id != lazy.id

	def test_lazy_import_dedupes_with_lazy(self):
		"""Multiple lazy imports of same symbol dedupe."""
		lazy1 = Import("./Chart", lazy=True)
		lazy2 = Import("./Chart", lazy=True)

		# Same ID means deduped
		assert lazy1.id == lazy2.id

	def test_lazy_import_js_name(self):
		"""Lazy import has correct js_name."""
		imp = Import("./Chart", lazy=True)
		assert imp.js_name.endswith(f"_{imp.id}")
		assert imp.id in imp.js_name


class TestDynamicImport:
	"""Test dynamic import_() primitive."""

	def setup_method(self):
		"""Clear registries before each test."""
		clear_function_cache()

	def test_dynamic_import_package(self):
		"""import_() with package path emits correct JS."""

		# import_ captured via closure (package path, not local)
		@javascript
		def load():
			return import_("my-module").then(lambda m: m.default)

		fn = load.transpile()
		js = emit(fn)
		assert (
			js
			== 'function load_1() {\nreturn import("my-module").then(m => m.default);\n}'
		)

	def test_dynamic_import_then_chain(self):
		"""import_() supports .then() chaining."""
		from pulse.transpiler import import_

		@javascript
		def load():
			return import_("lodash").then(lambda m: m.default).then(lambda d: d.x)

		fn = load.transpile()
		js = emit(fn)
		assert (
			js
			== 'function load_1() {\nreturn import("lodash").then(m => m.default).then(d => d.x);\n}'
		)

	def test_dynamic_import_local_with_emit_context(self, tmp_path: Path):
		"""Local import_() uses asset path from emit context."""
		from pulse.transpiler import DynamicImport, EmitContext
		from pulse.transpiler.assets import register_local_asset

		# Create a temp JS file to import
		chart_file = tmp_path / "Chart.tsx"
		chart_file.write_text("export default function Chart() {}")

		# Register asset and create DynamicImport directly (bypasses transpiler)
		asset = register_local_asset(chart_file)
		dynamic_import = DynamicImport(src=str(chart_file), asset=asset)

		# Without emit context - returns absolute source path
		js_no_ctx = emit(dynamic_import)
		assert js_no_ctx == f'import("{chart_file}")'

		# With emit context - has correct relative path
		with EmitContext(route_file_path="routes/users/index.tsx"):
			js_with_ctx = emit(dynamic_import)

		assert js_with_ctx == f'import("../../assets/Chart_{asset.id}.tsx")'
