"""
Tests for React component integration in pulse.html.

This module tests the system for defining and using React components
within the UI tree generation system.
"""

import re
from typing import Any

import pytest
from pulse import (
	Node,
	div,
	h1,
	p,
	react_component,
)
from pulse.react_component import (
	COMPONENT_REGISTRY,
	ComponentRegistry,
	ReactComponent,
	registered_react_components,
)
from pulse.transpiler.imports import clear_import_registry


def assert_mount_point_tag(tag: str, expected_name: str) -> None:
	"""Assert that a mount point tag matches the expected component name with ID suffix.

	Mount point tags have the format '$$<name>_<id>' where id is a hex number.
	"""
	pattern = rf"^\$\${re.escape(expected_name)}_[0-9a-f]+$"
	assert re.match(pattern, tag), (
		f"Expected tag matching '$$<name>_<hex_id>', got {tag!r}"
	)


class TestReactComponent:
	"""Test the ReactComponent class."""

	def test_component_creation(self):
		"""Test creating ReactComponent instances."""
		component = ReactComponent(
			name="TestComponent",
			src="./TestComponent",
			is_default=False,
		)

		assert component.name == "TestComponent"
		assert component.src == "./TestComponent"
		assert component.prop is None
		assert not component.is_default

	def test_component_with_prop(self):
		"""Test ReactComponent with prop for nested component access."""
		component = ReactComponent(
			name="AppShell",
			src="@mantine/core",
			prop="Header",
			is_default=False,
		)

		assert component.name == "AppShell"
		assert component.src == "@mantine/core"
		assert component.prop == "Header"
		assert not component.is_default

	def test_component_with_default_export(self):
		"""Test ReactComponent with default export."""
		component = ReactComponent(
			name="default-component",
			src="./DefaultComponent",
			is_default=True,
		)

		assert component.name == "default-component"
		assert component.src == "./DefaultComponent"
		assert component.is_default


class TestDefineReactComponent:
	"""Test the define_react_component function."""

	def setup_method(self):
		"""Clear the component registry and import registry before each test."""
		# This is a bit of a hack to ensure a clean slate for tests,
		# as the global registry persists.
		COMPONENT_REGISTRY.set(ComponentRegistry())
		clear_import_registry()

	def test_define_component_basic(self):
		"""Test defining a basic React component."""
		TestComponent = ReactComponent(
			name="TestComponent",
			src="./TestComponent",
			is_default=False,
		)

		# Should return a callable
		assert callable(TestComponent)

		# Component should be registered
		components = registered_react_components()
		assert len(components) == 1
		assert components[0].name == "TestComponent"
		assert components[0].src == "./TestComponent"
		assert not components[0].is_default

	def test_define_component_with_prop(self):
		"""Test defining a component with prop for nested access."""
		TestComponent = ReactComponent(
			name="AppShell",
			src="@mantine/core",
			prop="Header",
			is_default=False,
		)
		# Should return a callable
		assert callable(TestComponent)

		# Component should be registered
		components = registered_react_components()
		assert len(components) == 1
		assert components[0].name == "AppShell"
		assert components[0].src == "@mantine/core"
		assert components[0].prop == "Header"
		assert not components[0].is_default

	def test_define_component_default_export(self):
		"""Test defining a component with default export."""
		ReactComponent(name="default-comp", src="./DefaultComponent", is_default=True)

		components = registered_react_components()
		assert len(components) == 1
		assert components[0].name == "default-comp"
		assert components[0].is_default

	def test_component_mount_point_creation(self):
		"""Test that defined components create mount points."""
		TestComponent = ReactComponent(
			name="TestComponent",
			src="./TestComponent",
			is_default=False,
		)

		# Create a mount point
		mount_point = TestComponent(prop1="value1", prop2="value2")

		assert_mount_point_tag(mount_point.tag, "TestComponent")
		assert mount_point.props == {"prop1": "value1", "prop2": "value2"}
		assert mount_point.children is None

	def test_component_with_children(self):
		"""Test creating mount points with children."""
		Container = ReactComponent(
			name="Container",
			src="./Container",
			is_default=False,
		)

		# Create mount point with children
		mount_point = Container(
			"Text child", p()["Paragraph child"], className="container"
		)

		assert_mount_point_tag(mount_point.tag, "Container")
		assert mount_point.props == {"className": "container"}
		assert mount_point.children is not None
		assert len(mount_point.children) == 2
		assert mount_point.children[0] == "Text child"
		p_child = mount_point.children[1]
		assert isinstance(p_child, Node) and p_child.tag == "p"

	def test_component_with_indexing_syntax(self):
		"""Test using indexing syntax with React components."""
		Card = ReactComponent(name="Card", src="./Card", is_default=False)

		# Use indexing syntax
		mount_point = Card(title="Test Card")[p()["Card content"], "Additional text"]

		assert_mount_point_tag(mount_point.tag, "Card")
		assert mount_point.props == {"title": "Test Card"}
		assert mount_point.children is not None
		assert len(mount_point.children) == 2
		p_child = mount_point.children[0]
		assert isinstance(p_child, Node) and p_child.tag == "p"
		assert mount_point.children[1] == "Additional text"

	def test_multiple_components(self):
		"""Test defining multiple components."""
		ReactComponent("Button", "./Button")
		ReactComponent("Input", "./Input")
		ReactComponent("Modal", "./Modal")

		components = registered_react_components()

		assert len(components) == 3
		assert {c.name for c in components} == {"Button", "Input", "Modal"}

	# Alias/overwrite behavior removed in new API; no corresponding test.


class TestComponentRegistry:
	"""Test the component registry functionality."""

	def setup_method(self):
		"""Clear the component registry and import registry before each test."""
		COMPONENT_REGISTRY.set(ComponentRegistry())
		clear_import_registry()

	def test_empty_registry(self):
		"""Test empty component registry."""
		components = registered_react_components()
		assert len(components) == 0

	def test_registry_collects_components(self):
		"""Test that the registry collects added components."""
		ReactComponent("Test", "./Test")

		components = registered_react_components()
		assert len(components) == 1
		assert components[0].name == "Test"

		ReactComponent("New", "./New")
		components = registered_react_components()
		assert len(components) == 2
		assert {c.name for c in components} == {"Test", "New"}


class TestMountPointGeneration:
	"""Test mount point generation from React components."""

	def setup_method(self):
		"""Clear the component registry and import registry before each test."""
		COMPONENT_REGISTRY.set(ComponentRegistry())
		clear_import_registry()

	def test_mount_point_tag_format(self):
		"""Test that mount points have correct tag format."""
		TestComp = ReactComponent("Test", "./Test")
		mount_point = TestComp()
		# Tag format is $$<js_name> where js_name is <name>_<id>
		assert_mount_point_tag(mount_point.tag, "Test")
		assert mount_point.tag == f"$${TestComp.import_.js_name}"

	def test_mount_point_serialization(self):
		"""Test that mount points serialize correctly."""
		Counter = ReactComponent("Counter", "./Counter")

		mount_point = Counter(count=5, label="Test Counter")[
			p()["Counter description"], "Additional text"
		]

		# Verify tag format
		assert_mount_point_tag(mount_point.tag, "Counter")
		# Verify props and children
		assert mount_point.props == {"count": 5, "label": "Test Counter"}
		assert mount_point.children is not None
		assert len(mount_point.children) == 2
		p_child = mount_point.children[0]
		assert isinstance(p_child, Node) and p_child.tag == "p"
		assert mount_point.children[1] == "Additional text"

	def test_nested_mount_points(self):
		"""Test nesting mount points within each other."""
		Card = ReactComponent("Card", "./Card")
		Button = ReactComponent("Button", "./Button")

		nested_structure = Card(title="Nested Example")[
			p()["This card contains a button:"],
			Button(variant="primary")["Click me!"],
			"And some additional text.",
		]

		# Verify tag format
		assert_mount_point_tag(nested_structure.tag, "Card")
		assert nested_structure.props == {"title": "Nested Example"}
		assert nested_structure.children is not None
		assert len(nested_structure.children) == 3
		# First child is a p tag
		p_child = nested_structure.children[0]
		assert isinstance(p_child, Node) and p_child.tag == "p"
		# Second child is a Button mount point
		button_child = nested_structure.children[1]
		assert isinstance(button_child, Node)
		assert_mount_point_tag(button_child.tag, "Button")
		assert button_child.props == {"variant": "primary"}
		# Third child is text
		assert nested_structure.children[2] == "And some additional text."


class TestComponentIntegrationWithHTML:
	"""Test integration of React components with regular HTML elements."""

	def setup_method(self):
		"""Clear the component registry and import registry before each test."""
		COMPONENT_REGISTRY.set(ComponentRegistry())
		clear_import_registry()

	def test_mixed_html_and_components(self):
		"""Test mixing HTML elements and React components."""
		UserCard = ReactComponent("UserCard", "./UserCard")
		Counter = ReactComponent("Counter", "./Counter")

		mixed_structure = div(className="app")[
			h1()["My App"],
			UserCard(name="John Doe", email="john@example.com"),
			p()["Some regular HTML content"],
			Counter(count=42)["This counter has children"],
			div()["More HTML content"],
		]

		# Verify structure
		assert mixed_structure.tag == "div"
		assert mixed_structure.props == {"className": "app"}
		assert mixed_structure.children is not None
		assert len(mixed_structure.children) == 5

		# Check h1
		h1_child = mixed_structure.children[0]
		assert isinstance(h1_child, Node) and h1_child.tag == "h1"

		# Check UserCard mount point
		user_card_child = mixed_structure.children[1]
		assert isinstance(user_card_child, Node)
		assert_mount_point_tag(user_card_child.tag, "UserCard")
		assert user_card_child.props == {
			"name": "John Doe",
			"email": "john@example.com",
		}

		# Check p
		p_child = mixed_structure.children[2]
		assert isinstance(p_child, Node) and p_child.tag == "p"

		# Check Counter mount point
		counter_child = mixed_structure.children[3]
		assert isinstance(counter_child, Node)
		assert_mount_point_tag(counter_child.tag, "Counter")
		assert counter_child.props == {"count": 42}

		# Check div
		div_child = mixed_structure.children[4]
		assert isinstance(div_child, Node) and div_child.tag == "div"

	def test_component_props_types(self):
		"""Test that component props handle various data types."""
		DataComponent = ReactComponent("Data", "./Data")

		mount_point = DataComponent(
			stringProp="text",
			numberProp=42,
			booleanProp=True,
			listProp=[1, 2, 3],
			dictProp={"key": "value"},
		)

		expected_props = {
			"stringProp": "text",
			"numberProp": 42,
			"booleanProp": True,
			"listProp": [1, 2, 3],
			"dictProp": {"key": "value"},
		}

		assert mount_point.props == expected_props


def test_react_component_decorator_basic():
	"""Test basic react_component decorator usage."""

	@react_component(name="Card", src="./Card")
	def Card(*children: Any, key: str | None = None):
		pass

	node = Card()
	assert isinstance(node, Node)
	assert_mount_point_tag(node.tag, "Card")


def test_react_component_decorator_default_export():
	"""Test react_component decorator with default export."""

	@react_component(name="DefaultComp", src="./Comp", is_default=True)
	def DefaultComp(*children: Any, key: str | None = None):
		pass

	node = DefaultComp()
	assert_mount_point_tag(node.tag, "DefaultComp")


def test_react_component_decorator_key_validation():
	"""Test that key validation still works."""

	@react_component(name="Box", src="./Box")
	def Box(*children: Any, key: str | None = None):
		pass

	# Non-string key should raise
	with pytest.raises(ValueError, match=r"key must be a string or None"):
		Box(key=123)  # pyright: ignore[reportArgumentType]

	# String key accepted
	node = Box(key="k1")
	assert_mount_point_tag(node.tag, "Box")
	assert node.key == "k1"
