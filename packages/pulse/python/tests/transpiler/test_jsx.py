"""
Tests for JSX support: tags, JsxFunction, ReactComponent, and related functionality.
"""

# pyright: reportPrivateUsage=false

from typing import Any

import pytest
from pulse.transpiler import (
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
)
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import (
	Element,
	Jsx,
	Member,
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
		from pulse.transpiler.modules.pulse.tags import TagExpr

		div = TagExpr("div")

		@javascript
		def render() -> Any:
			return div("Hello")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_1() {\nreturn <div>{"Hello"}</div>;\n}'

	def test_div_with_props(self):
		"""div(className=...) produces Element with props."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

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
		from pulse.transpiler.modules.pulse.tags import TagExpr

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
		from pulse.transpiler.modules.pulse.tags import TagExpr

		img = TagExpr("img")

		@javascript
		def render() -> Any:
			return img(src="photo.jpg")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_1() {\nreturn <img src="photo.jpg" />;\n}'

	def test_fragment(self):
		"""Fragment produces <>...</> JSX."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		fragment = TagExpr("")

		@javascript
		def render() -> Any:
			return fragment("one", "two")

		fn = render.transpile()
		code = emit(fn)
		assert code == 'function render_1() {\nreturn <>{"one"}{"two"}</>;\n}'

	def test_tag_with_key(self):
		"""Tag with key=... extracts key prop."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		li = TagExpr("li")

		@javascript
		def render() -> Any:
			return li("item", key="item-1")

		fn = render.transpile()
		code = emit(fn)
		assert (
			code == 'function render_1() {\nreturn <li key="item-1">{"item"}</li>;\n}'
		)

	def test_tag_expr_emit_directly(self):
		"""TagExpr emits as string literal when not called (for render props)."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		div = TagExpr("div")
		out: list[str] = []
		div.emit(out)
		assert out == ['"div"']

		# Fragment emits as empty string
		fragment = TagExpr("")
		out = []
		fragment.emit(out)
		assert out == ['""']

	def test_pytags_module_registration(self):
		"""PyTags registers all standard tags."""
		from pulse.transpiler.modules.pulse.tags import PulseTags, TagExpr

		# Check a few standard tags exist
		assert isinstance(PulseTags._transpiler.get("div"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("span"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("a"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("button"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("img"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("fragment"), TagExpr)

	def test_pytags_svg_tags(self):
		"""PyTags includes SVG tags."""
		from pulse.transpiler.modules.pulse.tags import PulseTags, TagExpr

		assert isinstance(PulseTags._transpiler.get("svg"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("path"), TagExpr)
		assert isinstance(PulseTags._transpiler.get("circle"), TagExpr)


class TestTagsIntegration:
	"""Test pulse.dom.tags integration with the full system."""

	def test_tags_registered_in_expr_registry(self):
		"""pulse.dom.tags values are registered in EXPR_REGISTRY."""
		import pulse.transpiler.modules  # noqa: F401 - triggers registration
		from pulse.dom import tags
		from pulse.transpiler.nodes import EXPR_REGISTRY

		# div should be registered
		assert id(tags.div) in EXPR_REGISTRY

	def test_tags_via_pymodule(self):
		"""Can access tags via PyModule.transpile_getattr."""
		import pulse.transpiler.modules  # noqa: F401 - triggers registration
		from pulse.dom import tags
		from pulse.transpiler.modules.pulse.tags import TagExpr
		from pulse.transpiler.nodes import EXPR_REGISTRY

		tags_module = EXPR_REGISTRY[id(tags)]
		# Access div through the module
		div_expr = tags_module.transpile_getattr("div", None)  # pyright: ignore[reportArgumentType]
		assert isinstance(div_expr, TagExpr)
		assert div_expr.tag == "div"


class TestPulseModuleIntegration:
	"""Test main pulse module integration for `import pulse as ps` pattern."""

	def test_pulse_module_registered_in_expr_registry(self):
		"""Main pulse module is registered in EXPR_REGISTRY."""
		import pulse as ps
		import pulse.transpiler.modules  # noqa: F401 - triggers registration
		from pulse.transpiler.nodes import EXPR_REGISTRY

		# pulse module should be registered
		assert id(ps) in EXPR_REGISTRY

	def test_pulse_div_registered_in_expr_registry(self):
		"""pulse.div is registered in EXPR_REGISTRY."""
		import pulse as ps
		import pulse.transpiler.modules  # noqa: F401 - triggers registration
		from pulse.transpiler.nodes import EXPR_REGISTRY

		# pulse.div should be registered (same as pulse.dom.tags.div)
		assert id(ps.div) in EXPR_REGISTRY

	def test_pulse_module_tags_via_pymodule(self):
		"""Can access tags via main pulse module PyModule.transpile_getattr."""
		import pulse as ps
		import pulse.transpiler.modules  # noqa: F401 - triggers registration
		from pulse.transpiler.modules.pulse.tags import TagExpr
		from pulse.transpiler.nodes import EXPR_REGISTRY

		pulse_module = EXPR_REGISTRY[id(ps)]
		# Access div through the pulse module
		div_expr = pulse_module.transpile_getattr("div", None)  # pyright: ignore[reportArgumentType]
		assert isinstance(div_expr, TagExpr)
		assert div_expr.tag == "div"

	def test_pulse_as_ps_div_in_transpiled_function(self):
		"""ps.div() works in @javascript(jsx=True) function with import pulse as ps."""
		import pulse as ps

		@javascript(jsx=True)
		def render() -> Any:
			return ps.div("Hello")

		fn = render.transpile()
		code = emit(fn)
		# JSX functions use props destructuring for React compatibility
		assert code == 'function render_1({}) {\nreturn <div>{"Hello"}</div>;\n}'

	def test_pulse_as_ps_nested_tags(self):
		"""Nested ps.div/ps.span calls work in transpiled function."""
		import pulse as ps

		@javascript(jsx=True)
		def render() -> Any:
			return ps.div(ps.span("inner"))

		fn = render.transpile()
		code = emit(fn)
		# JSX functions use props destructuring for React compatibility
		assert (
			code
			== 'function render_1({}) {\nreturn <div><span>{"inner"}</span></div>;\n}'
		)

	def test_pulse_as_ps_with_props(self):
		"""ps.div(className=...) produces Element with props."""
		import pulse as ps

		@javascript(jsx=True)
		def render() -> Any:
			return ps.div("Hello", className="container")

		fn = render.transpile()
		code = emit(fn)
		# JSX functions use props destructuring for React compatibility
		assert (
			code
			== 'function render_1({}) {\nreturn <div className="container">{"Hello"}</div>;\n}'
		)

	def test_pulse_as_ps_button_with_onclick(self):
		"""ps.button with onClick handler works in transpiled function."""
		import pulse as ps

		@javascript(jsx=True)
		def render() -> Any:
			return ps.button(
				"Click me",
				onClick=lambda e: None,  # type: ignore
			)

		fn = render.transpile()
		code = emit(fn)
		assert "<button" in code
		assert "onClick=" in code
		assert "Click me" in code

	def test_pulse_as_ps_self_closing_tag(self):
		"""ps.img() produces self-closing JSX element."""
		import pulse as ps

		@javascript(jsx=True)
		def render() -> Any:
			return ps.img(src="photo.jpg")

		fn = render.transpile()
		code = emit(fn)
		# JSX functions use props destructuring for React compatibility
		assert code == 'function render_1({}) {\nreturn <img src="photo.jpg" />;\n}'


# =============================================================================
# JSX Support - Jsx(JsFunction)
# =============================================================================


class TestJsxFunction:
	"""Test @javascript(jsx=True) returns JsxFunction."""

	def test_jsx_function_basic(self):
		"""@javascript(jsx=True) creates JsxFunction."""
		from pulse.transpiler.function import JsxFunction

		@javascript(jsx=True)
		def MyComponent(name: str) -> str:
			return name

		assert isinstance(MyComponent, JsxFunction)
		# JsxFunction is a parallel implementation, not a wrapper
		assert hasattr(MyComponent, "fn")
		assert hasattr(MyComponent, "id")
		assert hasattr(MyComponent, "deps")

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
		"""JsxFunction.transpile() wraps in React component with props destructuring."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		div = TagExpr("div")

		@javascript(jsx=True)
		def Greeting(name: str) -> Any:
			return div(name)

		fn = Greeting.transpile()
		code = emit(fn)
		# JSX functions use props destructuring: {name} instead of name
		assert code == "function Greeting_1({name}) {\nreturn <div>{name}</div>;\n}"

	def test_jsx_function_caching(self):
		"""JsxFunction is cached in FUNCTION_CACHE."""
		from pulse.transpiler.function import FUNCTION_CACHE, JsxFunction

		def MyComp() -> str:
			return "hi"

		comp1 = javascript(jsx=True)(MyComp)
		comp2 = javascript(jsx=True)(MyComp)
		# JsxFunction is cached directly
		assert comp1 is comp2
		assert MyComp in FUNCTION_CACHE
		assert isinstance(FUNCTION_CACHE[MyComp], JsxFunction)

	def test_jsx_function_as_dependency(self):
		"""JsxFunction can be used as dependency in another function."""
		from pulse.transpiler.function import JsxFunction

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
		from pulse.transpiler.function import JsxFunction

		Button = Import("Button", "@ui/core")

		@javascript(jsx=True)
		def Card() -> Any:
			from pulse.transpiler.nodes import Jsx

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
		from pulse.transpiler.function import JsFunction, JsxFunction

		@javascript
		def regular() -> int:
			return 1

		@javascript(jsx=True)
		def jsx_fn() -> int:
			return 1

		assert isinstance(regular, JsFunction)
		assert isinstance(jsx_fn, JsxFunction)
		# JsxFunction is a parallel implementation, not a wrapper

	def test_jsx_function_js_name(self):
		"""Underlying JsFunction.js_name is unique."""

		@javascript(jsx=True)
		def Widget() -> str:
			return "w"

		assert Widget.js_name.startswith("Widget_")
		assert Widget.js_name == f"Widget_{Widget.id}"

	def test_jsx_function_with_default_values(self):
		"""JsxFunction with default param values uses props destructuring."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		div = TagExpr("div")

		@javascript(jsx=True)
		def Toggle(visible: bool = True) -> Any:
			return div("content" if visible else "hidden")

		fn = Toggle.transpile()
		code = emit(fn)
		# Should destructure with default value
		assert "{visible = true}" in code
		assert "function Toggle_" in code

	def test_jsx_function_with_children_and_defaults(self):
		"""JsxFunction with *children and default kwargs works as React component."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		div = TagExpr("div")

		@javascript(jsx=True)
		def Container(*children: Any, className: str = "default") -> Any:
			return div(className=className)

		fn = Container.transpile()
		code = emit(fn)
		# Should have both children and className with default
		assert "{children, className = " in code
		assert '"default"' in code


# =============================================================================
# ReactComponent Tests
# =============================================================================


class TestReactComponent:
	"""Test Jsx(expr) pattern for React components."""

	def test_jsx_with_import(self):
		"""Jsx(Import) uses the import's js_name in emission."""

		button_import = Import("Button", "@mantine/core")
		Button = Jsx(button_import)

		# Check emit outputs the import's js_name
		assert emit(Button) == button_import.js_name

	def test_jsx_with_member(self):
		"""Jsx(Member) for AppShell.Header patterns."""

		app_shell = Import("AppShell", "@mantine/core")
		header_expr = Member(app_shell, "Header")
		Header = Jsx(header_expr)

		# Check emit includes member access
		assert ".Header" in emit(Header)
		assert "AppShell_" in emit(Header)

	def test_jsx_call_produces_element(self):
		"""Calling Jsx(expr) produces Element with expr as tag."""

		button_import = Import("Button", "@mantine/core")
		Button = Jsx(button_import)

		elem = Button("Click me", variant="primary")
		# tag is now the underlying expr (e.g. Import)
		assert elem.tag is button_import
		assert elem.children == ["Click me"]
		assert elem.props is not None
		assert elem.props["variant"] == "primary"

	def test_jsx_transpile_call(self):
		"""Jsx(expr).transpile_call produces Element with expr as tag."""

		card_import = Import("Card", "@mantine/core")
		Card = Jsx(card_import)

		@javascript(jsx=True)
		def render() -> Any:
			return Card("Content", shadow="sm")

		fn = render.transpile()
		code = emit(fn)
		# Should produce Element with the import's js_name as tag
		assert f"<{card_import.js_name}" in code
		assert 'shadow="sm"' in code
		assert "Content" in code

	def test_jsx_member_transpile_call(self):
		"""Member-based Jsx produces correct JSX in transpilation."""

		app_shell = Import("AppShell", "@mantine/core")
		Header = Jsx(Member(app_shell, "Header"))

		@javascript(jsx=True)
		def render() -> Any:
			return Header(height=60)

		fn = render.transpile()
		code = emit(fn)
		assert f"<{app_shell.js_name}.Header height={{60}} />" in code

	def test_react_component_decorator(self):
		"""The @react_component decorator returns a Jsx(expr)."""
		from pulse.transpiler.react_component import react_component

		@react_component(Import("Button", "@mantine/core"))
		def Button(children: str, variant: str = "default") -> Element: ...

		# Should be a Jsx
		assert isinstance(Button, Jsx)


# =============================================================================
# Jsx Standalone Behavior
# =============================================================================


class TestJsxStandalone:
	"""Test Jsx wrapper behavior."""

	def test_jsx_transpile_getattr(self):
		"""Jsx.transpile_getattr delegates to wrapped expr."""

		app_shell = Import("AppShell", "@mantine/core")
		jsx_shell = Jsx(app_shell)

		# Access .Header via transpile_getattr
		header = jsx_shell.transpile_getattr("Header", None)  # pyright: ignore[reportArgumentType]
		# Delegates to wrapped expr, so Member wraps the Import, not the Jsx
		assert isinstance(header, Member)
		assert header.obj is app_shell
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
# Expression Keys in JSX
# =============================================================================


class TestExpressionKeys:
	"""Test expression keys in JSX elements."""

	def test_numeric_key(self):
		"""Numeric keys are supported."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		li = TagExpr("li")

		@javascript
		def render(index: int) -> Any:
			return li("item", key=index)

		fn = render.transpile()
		code = emit(fn)
		assert "key={index}" in code

	def test_variable_key(self):
		"""Variable keys are supported."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		li = TagExpr("li")

		@javascript
		def render(item_id: str) -> Any:
			return li("item", key=item_id)

		fn = render.transpile()
		code = emit(fn)
		assert "key={item_id}" in code

	def test_expression_key(self):
		"""Expression keys (like member access) are supported."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		li = TagExpr("li")

		@javascript
		def render(item: Any) -> Any:
			return li(item.name, key=item.id)

		fn = render.transpile()
		code = emit(fn)
		assert "key={item.id}" in code

	def test_fstring_key(self):
		"""F-string keys are supported."""
		from pulse.transpiler.modules.pulse.tags import TagExpr

		li = TagExpr("li")

		@javascript
		def render(prefix: str, index: int) -> Any:
			return li("item", key=f"{prefix}-{index}")

		fn = render.transpile()
		code = emit(fn)
		assert "key={`${prefix}-${index}`}" in code
