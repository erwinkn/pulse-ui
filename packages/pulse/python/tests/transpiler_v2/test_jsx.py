"""
Tests for JSX support: tags, JsxFunction, ReactComponent, and related functionality.
"""

# pyright: reportPrivateUsage=false

import ast
from typing import Any
from unittest.mock import MagicMock

import pytest
from pulse.transpiler_v2 import (
	JsFunction,
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
)
from pulse.transpiler_v2.imports import Import
from pulse.transpiler_v2.nodes import (
	Call,
	Element,
	Jsx,
	Literal,
	Member,
	Ref,
	Subscript,
	registered_refs,
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
# JSX Support - Tags
# =============================================================================


class TestTagsModule:
	"""Test pulse.dom.tags transpilation via PyTags."""

	def test_div_simple(self):
		"""div() produces Element."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		div = TagExpr("div")

		@javascript
		def render() -> Any:
			return div("Hello")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_1() {\nreturn <div>{"Hello"}</div>;\n}'

	def test_div_with_props(self):
		"""div(className=...) produces Element with props."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		div = TagExpr("div")

		@javascript
		def render() -> Any:
			return div("Hello", className="container")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_1() {\nreturn <div className="container">{"Hello"}</div>;\n}'
		)

	def test_nested_tags(self):
		"""Nested tag calls produce nested JSX."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		div = TagExpr("div")
		span = TagExpr("span")

		@javascript
		def render() -> Any:
			return div(span("inner"))

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_1() {\nreturn <div><span>{"inner"}</span></div>;\n}'
		)

	def test_self_closing_tag(self):
		"""Tag with no children produces self-closing JSX."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		img = TagExpr("img")

		@javascript
		def render() -> Any:
			return img(src="photo.jpg")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_1() {\nreturn <img src="photo.jpg" />;\n}'

	def test_fragment(self):
		"""Fragment produces <>...</> JSX."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		fragment = TagExpr("$$fragment")

		@javascript
		def render() -> Any:
			return fragment("one", "two")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_1() {\nreturn <>{"one"}{"two"}</>;\n}'

	def test_tag_with_key(self):
		"""Tag with key=... extracts key prop."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		li = TagExpr("li")

		@javascript
		def render() -> Any:
			return li("item", key="item-1")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code == 'function render_1() {\nreturn <li key="item-1">{"item"}</li>;\n}'
		)

	def test_tag_expr_cannot_emit_directly(self):
		"""TagExpr raises when emitted directly (not called)."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		div = TagExpr("div")
		out: list[str] = []
		with pytest.raises(TypeError, match="must be called"):
			div.emit(out)

	def test_pytags_module_registration(self):
		"""PyTags registers all standard tags."""
		from pulse.transpiler_v2.modules.pulse.tags import PulseTags, TagExpr

		# Check a few standard tags exist
		assert isinstance(PulseTags._transpiler.get("div"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("span"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("a"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("button"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("img"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("fragment"), TagExpr)

	def test_pytags_svg_tags(self):
		"""PyTags includes SVG tags."""
		from pulse.transpiler_v2.modules.pulse.tags import PulseTags, TagExpr

		assert isinstance(PulseTags._transpiler.get("svg"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("path"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("circle"), TagExpr)


class TestTagsIntegration:
	"""Test pulse.dom.tags integration with the full system."""

	def test_tags_registered_in_expr_registry(self):
		"""pulse.dom.tags values are registered in EXPR_REGISTRY."""
		import pulse.transpiler_v2.modules  # noqa: F401 - triggers registration
		from pulse.dom import tags
		from pulse.transpiler_v2.nodes import EXPR_REGISTRY

		# div should be registered
		assert id(tags.div) in EXPR_REGISTRY

	def test_tags_via_pymodule(self):
		"""Can access tags via PyModule.transpile_getattr."""
		import pulse.transpiler_v2.modules  # noqa: F401 - triggers registration
		from pulse.dom import tags
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr
		from pulse.transpiler_v2.nodes import EXPR_REGISTRY

		tags_module = EXPR_REGISTRY[id(tags)]
		# Access div through the module
		div_expr = tags_module.transpile_getattr("div", None)  # pyright: ignore[reportArgumentType]
		assert isinstance(div_expr, TagExpr)
		assert div_expr.tag == "div"


# =============================================================================
# JSX Support - Jsx(JsFunction)
# =============================================================================


class TestJsxFunction:
	"""Test @javascript(jsx=True) returns JsxFunction wrapper."""

	def test_jsx_function_basic(self):
		"""@javascript(jsx=True) creates JsxFunction wrapper."""
		from pulse.transpiler_v2.function import JsxFunction

		@javascript(jsx=True)
		def MyComponent(name: str) -> str:
			return name

		assert isinstance(MyComponent, JsxFunction)
		assert isinstance(MyComponent.js_fn, JsFunction)

	def test_jsx_function_call_produces_element(self):
		"""JsxFunction called produces Element."""

		@javascript(jsx=True)
		def Button(label: str) -> str:
			return label

		@javascript
		def render() -> Any:
			return Button("Click")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code == 'function render_2() {\nreturn <Button_1>{"Click"}</Button_1>;\n}'
		)

	def test_jsx_function_with_props(self):
		"""JsxFunction call with kwargs produces props."""

		@javascript(jsx=True)
		def Card(title: str) -> str:
			return title

		@javascript
		def render() -> Any:
			return Card("content", title="Hello")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_2() {\nreturn <Card_1 title="Hello">{"content"}</Card_1>;\n}'
		)

	def test_jsx_function_with_key(self):
		"""JsxFunction call with key= extracts key."""

		@javascript(jsx=True)
		def Item(text: str) -> str:
			return text

		@javascript
		def render() -> Any:
			return Item("hello", key="item-1")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code
			== 'function render_2() {\nreturn <Item_1 key="item-1">{"hello"}</Item_1>;\n}'
		)

	def test_jsx_function_transpile(self):
		"""JsxFunction.transpile() delegates to underlying JsFunction."""
		from pulse.transpiler_v2.modules.pulse.tags import TagExpr

		div = TagExpr("div")

		@javascript(jsx=True)
		def Greeting(name: str) -> Any:
			return div(name)

		fn = Greeting.transpile()
		code = emit(fn)
		assert code == "function Greeting_1(name) {\nreturn <div>{name}</div>;\n}"

	def test_jsx_function_caching(self):
		"""Underlying JsFunction is cached in FUNCTION_CACHE."""
		from pulse.transpiler_v2.function import FUNCTION_CACHE

		def MyComp() -> str:
			return "hi"

		comp1 = javascript(jsx=True)(MyComp)
		comp2 = javascript(jsx=True)(MyComp)
		assert comp1 is not comp2  # wrapper not cached
		assert comp1.js_fn is comp2.js_fn  # underlying JsFunction is cached
		assert MyComp in FUNCTION_CACHE

	def test_jsx_function_as_dependency(self):
		"""JsxFunction can be used as dependency in another function."""
		from pulse.transpiler_v2.function import JsxFunction

		@javascript(jsx=True)
		def Inner() -> str:
			return "inner"

		@javascript
		def outer() -> Any:
			return Inner()

		assert "Inner" in outer.deps
		assert isinstance(outer.deps["Inner"], JsxFunction)

	def test_jsx_function_imports(self):
		"""JsxFunction.imports() returns Import deps."""
		from pulse.transpiler_v2.function import JsxFunction

		Button = Import("Button", "@ui/core")

		@javascript(jsx=True)
		def Card() -> Any:
			from pulse.transpiler_v2.nodes import Jsx

			return Jsx(Button)("click")

		assert isinstance(Card, JsxFunction)
		imports = Card.imports()
		assert "Button" in imports

	def test_jsx_function_no_children(self):
		"""JsxFunction call with only props, no children."""

		@javascript(jsx=True)
		def Icon(name: str) -> str:
			return name

		@javascript
		def render() -> Any:
			return Icon(name="check")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_2() {\nreturn <Icon_1 name="check" />;\n}'

	def test_regular_vs_jsx_decorator(self):
		"""@javascript vs @javascript(jsx=True) produce different types."""
		from pulse.transpiler_v2.function import JsFunction, JsxFunction

		@javascript
		def regular() -> int:
			return 1

		@javascript(jsx=True)
		def jsx_fn() -> int:
			return 1

		assert isinstance(regular, JsFunction)
		assert isinstance(jsx_fn, JsxFunction)
		assert isinstance(jsx_fn.js_fn, JsFunction)

	def test_jsx_function_js_name(self):
		"""Underlying JsFunction.js_name is unique."""

		@javascript(jsx=True)
		def Widget() -> str:
			return "w"

		assert Widget.js_name.startswith("Widget_")
		assert Widget.js_name == f"Widget_{Widget.id}"


# =============================================================================
# ReactComponent Tests
# =============================================================================


class TestReactComponent:
	"""Test Ref(Jsx(expr)) pattern for React components."""

	def test_ref_jsx_with_import(self):
		"""Ref(Jsx(Import)) creates a registry entry with correct key."""

		button_import = Import("Button", "@mantine/core")
		Button = Ref(Jsx(button_import))

		# Check key is a small unique ID
		assert Button.key == "1"
		# Check emit outputs the import's js_name
		assert emit(Button) == button_import.js_name

	def test_ref_jsx_with_member(self):
		"""Ref(Jsx(Member)) for AppShell.Header patterns."""

		app_shell = Import("AppShell", "@mantine/core")
		header_expr = Member(app_shell, "Header")
		Header = Ref(Jsx(header_expr))

		# Check key is unique ID
		assert Header.key == "1"
		# Check emit includes member access
		assert ".Header" in emit(Header)
		assert "AppShell_" in emit(Header)

	def test_ref_jsx_call_produces_mount_point_element(self):
		"""Calling Ref(Jsx(expr)) produces Element with expr as tag."""

		button_import = Import("Button", "@mantine/core")
		Button = Ref(Jsx(button_import))

		elem = Button("Click me", variant="primary")
		# tag is now the underlying expr (e.g. Import)
		assert elem.tag is button_import
		assert elem.children == ["Click me"]
		assert elem.props is not None
		assert elem.props["variant"] == "primary"

	def test_ref_jsx_transpile_call(self):
		"""Ref(Jsx(expr)).transpile_call produces Element with expr as tag."""

		card_import = Import("Card", "@mantine/core")
		Card = Ref(Jsx(card_import))

		@javascript(jsx=True)
		def render() -> Any:
			return Card("Content", shadow="sm")

		fn = render.transpile()
		code = emit(fn)
		# Should produce Element with the import's js_name as tag
		assert f"<{card_import.js_name}" in code
		assert 'shadow="sm"' in code
		assert "Content" in code

	def test_ref_jsx_member_transpile_call(self):
		"""Member-based Ref(Jsx) produces correct JSX in transpilation."""

		app_shell = Import("AppShell", "@mantine/core")
		Header = Ref(Jsx(Member(app_shell, "Header")))

		@javascript(jsx=True)
		def render() -> Any:
			return Header(height=60)

		fn = render.transpile()
		code = emit(fn)
		assert f"<{app_shell.js_name}.Header height={{60}} />" in code

	def test_ref_registry(self):
		"""Refs are registered in the ref registry."""

		button = Import("Button", "@ui/button")
		card = Import("Card", "@ui/card")

		Button = Ref(Jsx(button))
		Card = Ref(Jsx(card))

		refs = registered_refs()
		assert Button in refs
		assert Card in refs
		# Note: JsFunction also creates refs, so >= 2
		assert len([r for r in refs if r in [Button, Card]]) == 2

	def test_react_component_decorator(self):
		"""The @react_component decorator returns a Ref(Jsx(expr))."""
		from pulse.transpiler_v2.react_component import react_component

		@react_component("Button", "@mantine/core")
		def Button(children: str, variant: str = "default") -> Element: ...

		# Should be a Ref wrapping a Jsx
		assert isinstance(Button, Ref)
		assert isinstance(Button.expr, Jsx)


# =============================================================================
# Jsx Standalone Behavior
# =============================================================================


class TestJsxStandalone:
	"""Test Jsx wrapper without Ref."""

	def test_jsx_transpile_getattr(self):
		"""Jsx.transpile_getattr is not overridden (returns Member)."""

		app_shell = Import("AppShell", "@mantine/core")
		jsx_shell = Jsx(app_shell)

		# Access .Header via transpile_getattr
		header = jsx_shell.transpile_getattr("Header", None)  # pyright: ignore[reportArgumentType]
		# Should be a Member wrapping the Jsx, since Jsx doesn't override it
		assert isinstance(header, Member)
		assert header.obj is jsx_shell
		assert header.prop == "Header"

	def test_jsx_runtime_call_produces_element(self):
		"""Jsx.__call__ produces Element at runtime."""

		button = Import("Button", "@mantine/core")
		jsx_button = Jsx(button)

		# Direct runtime call
		result = jsx_button("Click", variant="primary")
		assert isinstance(result, Element)
		assert result.tag is button
		assert result.children == ["Click"]
		assert result.props is not None
		assert result.props["variant"] == "primary"

	def test_jsx_emit_defers_to_wrapped_expr(self):
		"""Jsx.emit() defers to wrapped expr's emit."""

		button = Import("Button", "@ui/button")
		jsx_button = Jsx(button)

		# emit should delegate to the import
		assert emit(jsx_button) == button.js_name


# =============================================================================
# Ref Delegation Methods
# =============================================================================


class TestRefDelegation:
	"""Test Ref delegation to wrapped expression."""

	def test_ref_transpile_getattr_delegates(self):
		"""Ref.transpile_getattr delegates to wrapped expr."""

		app_shell = Import("AppShell", "@mantine/core")
		ref = Ref(app_shell)

		# Access .Header through Ref
		result = ref.transpile_getattr("Header", None)  # pyright: ignore[reportArgumentType]
		assert isinstance(result, Member)
		# Member uses .prop field, not .attr
		assert result.prop == "Header"

	def test_ref_transpile_subscript_delegates(self):
		"""Ref.transpile_subscript delegates to wrapped expr."""

		# Use Import which creates Subscript correctly
		obj = Import("obj", "./obj", kind="default")
		ref = Ref(obj)

		# Access [0] through Ref - need to pass an ast.expr node
		key_node = ast.Constant(value=0)
		# Create a mock context with emit_expr
		mock_ctx = MagicMock()
		mock_ctx.emit_expr.return_value = Literal(0)

		result = ref.transpile_subscript(key_node, mock_ctx)
		assert isinstance(result, Subscript)
		mock_ctx.emit_expr.assert_called_once_with(key_node)

	def test_ref_wrapping_non_jsx_call_delegates(self):
		"""Ref wrapping non-Jsx expr delegates call to wrapped expr."""

		fn_import = Import("helper", "./utils")
		ref = Ref(fn_import)

		# Calling should delegate to import's __call__ (produces Call)
		result = ref("arg1", "arg2")
		assert isinstance(result, Call)

	def test_ref_emit_delegates(self):
		"""Ref.emit() defers to wrapped expr."""

		button = Import("Button", "@mantine/core")
		ref = Ref(button)

		assert emit(ref) == button.js_name
