"""
Tests for Import functionality: as dependency and as decorator.
"""

# pyright: reportPrivateUsage=false

from typing import Any

import pytest
from pulse.transpiler_v2 import (
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
)
from pulse.transpiler_v2.imports import (
	Import,
	get_registered_imports,
)


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()
	clear_import_registry()
	yield
	clear_function_cache()
	clear_import_registry()


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
		from pulse.transpiler_v2.nodes import Jsx

		Button = Jsx(Import("Button", "@mantine/core"))  # ID 1

		@javascript
		def render() -> Any:  # ID 2
			return Button("Click me", disabled=True)

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_2() {\nreturn <Button_1 disabled={true}>{"Click me"}</Button_1>;\n}'
		)

	def test_import_jsx_call_with_key(self):
		"""Jsx wrapping an Import with key prop extracts key."""
		from pulse.transpiler_v2.nodes import Jsx

		Item = Jsx(Import("Item", "./components"))  # ID 1

		@javascript
		def render() -> Any:  # ID 2
			return Item("text", key="item-1")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_2() {\nreturn <Item_1 key="item-1">{"text"}</Item_1>;\n}'
		)

	def test_import_jsx_call_no_children(self):
		"""Jsx wrapping an Import call with only props, no children."""
		from pulse.transpiler_v2.nodes import Jsx

		Icon = Jsx(Import("Icon", "./icons"))  # ID 1

		@javascript
		def render() -> Any:  # ID 2
			return Icon(name="check")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_2() {\nreturn <Icon_1 name="check" />;\n}'

	def test_import_attribute_access(self):
		"""Import with attribute access produces Member."""
		React = Import("React", "react", kind="default")  # ID 1

		@javascript
		def get_version() -> Any:  # ID 2
			return React.version

		fn = get_version.transpile()
		code = emit(fn)
		assert code == "function get_version_2() {\nreturn React_1.version;\n}"

	def test_import_method_call(self):
		"""Import method call chains correctly."""
		router = Import("router", "next/router", kind="default")  # ID 1

		@javascript
		def navigate() -> Any:  # ID 2
			return router.push("/home")

		fn = navigate.transpile()
		code = emit(fn)
		assert code == 'function navigate_2() {\nreturn router_1.push("/home");\n}'

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

	def test_import_decorator_returns_import(self):
		"""@Import decorating a function returns the Import itself."""
		from pulse.transpiler_v2.imports import Import

		clsx_import = Import("clsx", "clsx", kind="default")

		@clsx_import.as_
		def clsx(*args: str) -> str: ...

		# clsx should be the Import, not the function
		assert clsx is clsx_import

	def test_import_decorator_call_still_works(self):
		"""Import decorated can still be called to build expressions."""
		from pulse.transpiler_v2.imports import Import
		from pulse.transpiler_v2.nodes import Call

		clsx_import = Import("clsx", "clsx", kind="default")

		@clsx_import.as_
		def clsx(*args: str) -> str: ...

		# Calling should produce a Call node
		result = clsx("a", "b")
		assert isinstance(result, Call)
		assert emit(result) == 'clsx_1("a", "b")'

	def test_import_jsx_decorator_produces_element(self):
		"""Jsx wrapping an Import used as decorator produces Element on call."""
		from pulse.transpiler_v2.imports import Import
		from pulse.transpiler_v2.nodes import Element, Jsx

		# Use Jsx(Import) as a decorator
		button_jsx = Jsx(Import("Button", "@ui/button"))

		@button_jsx.as_
		def Button(label: str) -> None: ...

		# Calling should produce an Element
		result = Button("Click")
		assert isinstance(result, Element)
		assert result.tag is button_jsx.expr
		assert result.children == ["Click"]
