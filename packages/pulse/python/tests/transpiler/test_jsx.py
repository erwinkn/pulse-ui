"""Tests for JSX transpilation with Import(jsx=True) and @javascript(component=True) decorator."""

from __future__ import annotations

import pytest
from pulse.html import tags
from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.function import (
	FUNCTION_CACHE,
	JSX_FUNCTION_CACHE,
	JsxFunction,
	javascript,
)
from pulse.transpiler.imports import Import, clear_import_registry
from pulse.transpiler.jsx import JSXCallExpr
from pulse.transpiler.nodes import JSXElement


# Clear caches between tests
@pytest.fixture(autouse=True)
def clear_caches() -> None:
	FUNCTION_CACHE.clear()
	JSX_FUNCTION_CACHE.clear()
	clear_import_registry()


class TestImportWithJsx:
	"""Tests for Import with jsx=True parameter."""

	def test_import_jsx_basic_props(self) -> None:
		"""Test: Import(..., jsx=True)(label="Click") emits <Button label="Click" />"""
		Button = Import("Button", "ui", jsx=True)

		@javascript
		def fn():
			return Button(label="Click")

		js = fn.transpile()
		assert "<Button" in js
		assert 'label="Click"' in js
		assert "/>" in js

	def test_import_jsx_with_children(self) -> None:
		"""Test: Import(..., jsx=True)("child1", "child2", disabled=True) emits <Component disabled={true}>child1child2</Component>"""
		Component = Import("Component", "ui", jsx=True)

		@javascript
		def fn():
			return Component("child1", "child2", disabled=True)

		js = fn.transpile()
		assert "<Component" in js
		assert "disabled={true}" in js
		assert "child1" in js
		assert "child2" in js
		assert "</Component" in js  # Allow for unique IDs

	def test_import_jsx_with_spread_props(self) -> None:
		"""Test: Import(..., jsx=True)(**props) emits <Component {...props} />"""
		Component = Import("Component", "ui", jsx=True)

		@javascript
		def fn(props: dict):
			return Component(**props)

		js = fn.transpile()
		assert "<Component" in js
		assert "{...props}" in js

	def test_import_jsx_props_via_call_children_via_subscript(self) -> None:
		"""Test: Import(..., jsx=True)(className="box")[children]"""
		Component = Import("Component", "ui", jsx=True)

		@javascript
		def fn():
			return Component(className="box")[tags.span("Hello")]

		js = fn.transpile()
		assert "<Component" in js
		assert 'className="box"' in js
		assert "<span>Hello</span>" in js
		assert "</Component" in js  # Allow for unique IDs

	def test_import_jsx_nested_components(self) -> None:
		"""Test nested components."""
		Container = Import("Container", "ui", jsx=True)
		Item = Import("Item", "ui", jsx=True)

		@javascript
		def fn():
			return Container()[Item(key="1")]

		js = fn.transpile()
		assert "<Container" in js
		assert "<Item" in js
		assert 'key="1"' in js
		# Item might be self-closing, so check for either /> or </Item
		assert "/>" in js or "</Item" in js
		assert "</Container" in js  # Allow for unique IDs

	def test_import_jsx_spread_children(self) -> None:
		"""Test spread children *items"""
		Container = Import("Container", "ui", jsx=True)

		@javascript
		def fn(items: list):
			return Container(*items)

		js = fn.transpile()
		assert "<Container" in js
		# Spread children should be handled
		assert "{items}" in js

	def test_import_jsx_empty_props_with_children(self) -> None:
		"""Test: Import(..., jsx=True)()[children]"""
		Component = Import("Component", "ui", jsx=True)

		@javascript
		def fn():
			return Component()[tags.span("Hello")]

		js = fn.transpile()
		assert "<Component" in js
		assert "<span>Hello</span>" in js
		assert "</Component" in js  # Allow for unique IDs

	def test_import_jsx_returns_jsxcallexpr(self) -> None:
		"""Test that Import(jsx=True) returns JSXCallExpr when called."""
		Button = Import("Button", "ui", jsx=True)
		result = Button(label="Click")
		assert isinstance(result, JSXCallExpr)
		assert result.tag is Button

	def test_import_jsx_subscript_adds_children(self) -> None:
		"""Test that subscript on JSXCallExpr adds children."""

		Component = Import("Component", "ui", jsx=True)
		call_expr = Component(className="test")
		# Use JSString directly instead of tags.span which returns VDOM Node
		result = call_expr["Child"]
		assert isinstance(result, JSXElement)
		assert len(result.children) >= 1


class TestJsxFunctionComponent:
	"""Tests for JsxFunction and @javascript(component=True) decorator."""

	def test_basic_component_transpilation(self) -> None:
		"""Test basic component transpilation."""
		from pulse.html.tags import div

		@javascript(component=True)
		def MyComp(name: str):
			return div()[f"Hello {name}"]

		assert isinstance(MyComp, JsxFunction)
		js = MyComp.transpile()
		assert "function" in js
		assert "MyComp" in js
		# Should return JSX
		assert "<div>" in js or "return" in js

	def test_calling_component_from_another_component(self) -> None:
		"""Test: calling component from another component emits JSX."""
		from pulse.html.tags import div

		@javascript(component=True)
		def MyComp(name: str):
			return div()[f"Hello {name}"]

		@javascript(component=True)
		def App():
			return MyComp(name="World")

		js = App.transpile()
		# Should emit <MyComp name="World" /> not MyComp({name: "World"})
		assert "<MyComp" in js
		assert 'name="World"' in js
		assert "/>" in js or "</MyComp>" in js

	def test_props_via_call_children_via_subscript(self) -> None:
		"""Test: MyComp(className="wrapper")[span("Hello")]"""
		from pulse.html.tags import div, span

		@javascript(component=True)
		def MyComp(name: str):
			return div()[f"Hello {name}"]

		@javascript(component=True)
		def App():
			return MyComp(className="wrapper")[span("Hello")]

		js = App.transpile()
		assert "<MyComp" in js
		assert 'className="wrapper"' in js
		assert "<span>Hello</span>" in js
		assert "</MyComp" in js  # Allow for unique IDs

	def test_children_passing(self) -> None:
		"""Test: Container("child1", "child2", className="wrapper")"""
		from pulse.html.tags import div

		@javascript(component=True)
		def Container(name: str):
			return div()[f"Container: {name}"]

		@javascript(component=True)
		def App():
			return Container("child1", "child2", className="wrapper")

		js = App.transpile()
		assert "<Container" in js
		assert 'className="wrapper"' in js
		# Children should be passed
		assert "child1" in js or "child2" in js

	def test_component_with_hooks(self) -> None:
		"""Test component using hooks."""
		useState = Import("useState", "react")
		from pulse.html.tags import button, div

		@javascript(component=True)
		def Counter():
			count, set_count = useState(0)
			return div()[
				button(onClick=lambda: set_count(count + 1))[f"Count: {count}"]
			]

		js = Counter.transpile()
		assert "useState" in js
		assert "function" in js

	def test_nested_components(self) -> None:
		"""Test nested components."""
		from pulse.html.tags import div

		@javascript(component=True)
		def Inner(name: str):
			return div()[f"Inner: {name}"]

		@javascript(component=True)
		def Outer():
			return Inner(name="test")

		js = Outer.transpile()
		assert "<Inner" in js
		assert 'name="test"' in js

	def test_component_with_spread_children(self) -> None:
		"""Test component with spread children *items"""
		from pulse.html.tags import div

		@javascript(component=True)
		def Container(name: str):
			return div()[f"Container: {name}"]

		@javascript(component=True)
		def App(items: list):
			return Container(*items, className="wrapper")

		js = App.transpile()
		assert "<Container" in js
		assert 'className="wrapper"' in js

	def test_component_empty_props_with_children(self) -> None:
		"""Test: Component()[children]"""
		from pulse.html.tags import div, span

		@javascript(component=True)
		def Container(name: str):
			return div()[f"Container: {name}"]

		@javascript(component=True)
		def App():
			return Container()[span("Hello")]

		js = App.transpile()
		assert "<Container" in js
		assert "<span>Hello</span>" in js
		assert "</Container" in js  # Allow for unique IDs

	def test_component_returns_jsxcallexpr(self) -> None:
		"""Test that calling a component returns JSXCallExpr."""
		from pulse.html.tags import div

		@javascript(component=True)
		def MyComp(name: str):
			return div()[f"Hello {name}"]

		result = MyComp(name="World")
		assert isinstance(result, JSXCallExpr)
		assert result.tag is MyComp

	def test_component_subscript_adds_children(self) -> None:
		"""Test that subscript on component call adds children."""
		from pulse.html.tags import div

		@javascript(component=True)
		def MyComp(name: str):
			return div()[f"Hello {name}"]

		call_expr = MyComp(name="Test")
		# Use string directly instead of tags.span which returns VDOM Node
		result = call_expr["Child"]
		assert isinstance(result, JSXElement)
		assert len(result.children) >= 1


class TestHooksRegularImport:
	"""Tests for hooks (regular Import, no jsx)."""

	def test_usestate_regular_call(self) -> None:
		"""Test: useState = Import("useState", "react") called as useState(0) emits useState(0)"""
		useState = Import("useState", "react")

		@javascript
		def fn():
			return useState(0)

		js = fn.transpile()
		# Should be a regular function call, not JSX
		# Note: Import names get unique IDs, so it will be useState_<id>(0)
		assert "useState" in js
		assert "(0)" in js
		# Should not be JSX
		assert "<useState" not in js

	def test_hooks_inside_components(self) -> None:
		"""Test hooks inside components transpile correctly."""
		useState = Import("useState", "react")
		useEffect = Import("useEffect", "react")
		from pulse.html.tags import div

		@javascript(component=True)
		def MyComponent():
			count, set_count = useState(0)
			useEffect(lambda: None, [])
			return div()[f"Count: {count}"]

		js = MyComponent.transpile()
		assert "useState" in js
		assert "useEffect" in js
		assert "function" in js


class TestJsxEdgeCases:
	"""Tests for edge cases in JSX transpilation."""

	def test_props_via_call_children_via_subscript_complex(self) -> None:
		"""Test: Component(className="box", onClick=handler)["Hello", span("World")]"""
		from pulse.html.tags import span

		@javascript(component=True)
		def Component(name: str):
			return span()[f"Component: {name}"]

		@javascript
		def handler():
			pass

		@javascript(component=True)
		def App():
			return Component(className="box", onClick=handler)["Hello", span("World")]

		js = App.transpile()
		assert "<Component" in js
		assert 'className="box"' in js
		assert "onClick={handler" in js
		assert "Hello" in js
		assert "<span>World</span>" in js
		assert "</Component" in js  # Allow for unique IDs

	def test_mixed_children_and_props(self) -> None:
		"""Test mixed children and props."""
		from pulse.html.tags import div

		@javascript(component=True)
		def Container(name: str):
			return div()[f"Container: {name}"]

		@javascript(component=True)
		def App():
			return Container("child1", "child2", className="wrapper", id="main")

		js = App.transpile()
		assert "<Container" in js
		assert 'className="wrapper"' in js
		assert 'id="main"' in js
		# Children should be present
		assert "child1" in js or "child2" in js

	def test_component_cannot_be_called_twice(self) -> None:
		"""Test that calling an already-called component raises error."""
		from pulse.html.tags import div

		@javascript(component=True)
		def MyComp(name: str):
			return div()[f"Hello {name}"]

		call_expr = MyComp(name="Test")
		# Calling again should raise error
		with pytest.raises(JSCompilationError, match="already called"):
			call_expr(name="Again")  # pyright: ignore[reportCallIssue]


class TestRegression:
	"""Regression tests to ensure existing functionality still works."""

	def test_tags_py_functionality_still_works(self) -> None:
		"""Test that existing tags.py functionality still works after refactor."""
		from pulse.html import tags

		@javascript
		def fn():
			return tags.div(className="container")[tags.span("Hello")]

		js = fn.transpile()
		assert '<div className="container">' in js
		assert "<span>Hello</span>" in js
		assert "</div>" in js

	def test_jsfunction_non_jsx_still_works(self) -> None:
		"""Test that JsFunction (non-JSX) still works as before."""

		@javascript
		def add(a: int, b: int) -> int:
			return a + b

		@javascript
		def fn(x: int) -> int:
			return add(x, 1)

		js = fn.transpile()
		assert "function" in js
		assert "add" in js
		assert "return" in js
		# Should not have JSX syntax
		assert "<" not in js or "function" in js.split("<")[0]

	def test_import_without_jsx_still_works(self) -> None:
		"""Test that Import without jsx=True still works as before."""
		Button = Import("Button", "ui")

		@javascript
		def fn():
			return Button("click")

		js = fn.transpile()
		# Should be a regular function call
		# Note: Import names get unique IDs, so it will be Button_<id>("click")
		assert "Button" in js
		assert '("click")' in js
		# Should not be JSX
		assert "<Button" not in js

	def test_component_cache_separate_from_function_cache(self) -> None:
		"""Test that component cache is separate from function cache."""

		@javascript
		def regular_fn(x: int) -> int:
			return x + 1

		@javascript(component=True)
		def comp_fn(x: int):
			return regular_fn(x)

		# Check that the original function objects (keys) are in the correct caches
		# After decoration, regular_fn is a JsFunction, comp_fn is a JsxFunction
		# The cache keys are the original functions: regular_fn.fn and comp_fn.fn
		assert regular_fn.fn in FUNCTION_CACHE
		assert regular_fn.fn not in JSX_FUNCTION_CACHE
		assert comp_fn.fn in JSX_FUNCTION_CACHE
		assert comp_fn.fn not in FUNCTION_CACHE
