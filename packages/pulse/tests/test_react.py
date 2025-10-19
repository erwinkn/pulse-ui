"""
Tests for React component integration in pulse.html.

This module tests the system for defining and using React components
within the UI tree generation system.
"""

import inspect
from typing import (
	Annotated,
	Any,
	Generic,
	NotRequired,
	Required,
	TypedDict,
	TypeVar,
	Unpack,
	cast,
)

import pytest
from pulse import (
	Node,
	VDOMNode,
	div,
	h1,
	p,
	prop,
	react_component,
)
from pulse.react_component import (
	COMPONENT_REGISTRY,
	DEFAULT,
	ComponentRegistry,
	Prop,
	PropSpec,
	ReactComponent,
	parse_fn_signature,
	parse_typed_dict_props,
	registered_react_components,
)
from pulse.vdom import Child, Element

from .test_utils import assert_node_equal


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
		"""Clear the component registry before each test."""
		# This is a bit of a hack to ensure a clean slate for tests,
		# as the global registry persists.
		COMPONENT_REGISTRY.set(ComponentRegistry())

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

		assert mount_point.tag == "$$TestComponent"
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

		assert mount_point.tag == "$$Container"
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

		assert mount_point.tag == "$$Card"
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
		"""Clear the component registry before each test."""
		COMPONENT_REGISTRY.set(ComponentRegistry())

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
		"""Clear the component registry before each test."""
		COMPONENT_REGISTRY.set(ComponentRegistry())

	def test_mount_point_tag_format(self):
		"""Test that mount points have correct tag format."""
		TestComp = ReactComponent("Test", "./Test")
		mount_point = TestComp()
		assert mount_point.tag == "$$Test"

	def test_mount_point_serialization(self):
		"""Test that mount points serialize correctly."""
		Counter = ReactComponent("Counter", "./Counter")

		mount_point = Counter(count=5, label="Test Counter")[
			p()["Counter description"], "Additional text"
		]

		expected: VDOMNode = {
			"tag": "$$Counter",
			"props": {"count": 5, "label": "Test Counter"},
			"children": [
				{
					"tag": "p",
					"props": {},
					"children": ["Counter description"],
				},
				"Additional text",
			],
		}

		# Compare Node trees using assert_node_equal
		assert_node_equal(mount_point, Node.from_vdom(expected))

	def test_nested_mount_points(self):
		"""Test nesting mount points within each other."""
		Card = ReactComponent("Card", "./Card")
		Button = ReactComponent("Button", "./Button")

		nested_structure = Card(title="Nested Example")[
			p()["This card contains a button:"],
			Button(variant="primary")["Click me!"],
			"And some additional text.",
		]

		expected: VDOMNode = {
			"tag": "$$Card",
			"props": {"title": "Nested Example"},
			"children": [
				{"tag": "p", "props": {}, "children": ["This card contains a button:"]},
				{
					"tag": "$$Button",
					"props": {"variant": "primary"},
					"children": ["Click me!"],
				},
				"And some additional text.",
			],
		}

		assert_node_equal(nested_structure, Node.from_vdom(expected))


class TestComponentIntegrationWithHTML:
	"""Test integration of React components with regular HTML elements."""

	def setup_method(self):
		"""Clear the component registry before each test."""
		COMPONENT_REGISTRY.set(ComponentRegistry())

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

		expected: VDOMNode = {
			"tag": "div",
			"props": {"className": "app"},
			"children": [
				{"tag": "h1", "props": {}, "children": ["My App"]},
				{
					"tag": "$$UserCard",
					"props": {"name": "John Doe", "email": "john@example.com"},
					"children": None,
				},
				{"tag": "p", "props": {}, "children": ["Some regular HTML content"]},
				{
					"tag": "$$Counter",
					"props": {"count": 42},
					"children": ["This counter has children"],
				},
				{"tag": "div", "props": {}, "children": ["More HTML content"]},
			],
		}

		assert_node_equal(mixed_structure, Node.from_vdom(expected))

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


def test_parse_typed_dict_props_no_var_kw():
	def fn(*children: Child, key: str | None = None):
		return cast(Element, None)

	var_kw = None
	spec = parse_typed_dict_props(var_kw)
	assert isinstance(spec, PropSpec)
	assert len(spec.keys()) == 0


def test_parse_typed_dict_props_untyped_kwargs_all_allowed():
	def fn(*children: Child, key: str | None = None, **props):
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	spec = parse_typed_dict_props(var_kw)
	assert isinstance(spec, PropSpec)
	assert len(spec.keys()) == 0
	assert spec.allow_unspecified is True


def test_parse_typed_dict_props_non_unpack_annotation_raises():
	def fn(*children: Child, key: str | None = None, **props: Any):
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	with pytest.raises(
		TypeError, match=r"\*\*props must be annotated as typing.Unpack\[Props\]"
	):
		parse_typed_dict_props(var_kw)


def test_parse_typed_dict_props_unpack_must_wrap_typeddict():
	class NotTD:
		a: int

	def fn(*children: Child, key: str | None = None, **props: Unpack[NotTD]):  # type: ignore
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	with pytest.raises(TypeError, match=r"Unpack must wrap a TypedDict class"):
		parse_typed_dict_props(var_kw)


def test_parse_typed_dict_props_required_and_optional_inference():
	class P1(TypedDict):
		a: int
		b: NotRequired[str]

	def fn(*children: Child, key: str | None = None, **props: Unpack[P1]):
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	spec = parse_typed_dict_props(var_kw)
	assert set(spec.keys()) == {"a", "b"}
	a = cast(Prop, spec["a"])
	b = cast(Prop, spec["b"])
	assert a.required is True
	assert b.required is False
	assert a._type is int
	assert b._type is str


def test_total_false_with_required_wrapper():
	class P2(TypedDict, total=False):
		a: Required[int]
		b: str

	def fn(*children: Child, key: str | None = None, **props: Unpack[P2]):
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	spec = parse_typed_dict_props(var_kw)
	a = cast(Prop, spec["a"])
	b = cast(Prop, spec["b"])
	assert a.required is True
	assert b.required is False


def test_parse_typed_dict_props_annotated_with_prop_metadata_and_default():
	# Provide serialize with object param to satisfy contravariant Callable typing
	def serialize_obj(x: object) -> Any:
		return cast(int, x) + 1

	class P3(TypedDict):
		a: Annotated[int, prop(default_factory=lambda: 7, serialize=serialize_obj)]

	def fn(*children: Child, key: str | None = None, **props: Unpack[P3]):
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	spec = parse_typed_dict_props(var_kw)
	a = cast(Prop, spec["a"])
	assert a.required is True
	assert a._type is int
	assert callable(a.default_factory)
	assert callable(a.serialize)


def test_parse_typed_dict_props_annotated_prop_cannot_set_required():
	class P4(TypedDict):
		a: Annotated[int, Prop(required=True)]

	def fn(*children: Child, key: str | None = None, **props: Unpack[P4]):
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	with pytest.raises(
		TypeError,
		match=r"Use total=True \+ NotRequired\[T\] or total=False \+ Required\[T\]",
	):
		parse_typed_dict_props(var_kw)


def test_parse_fn_signature_no_children_annotation():
	def ok(*children, key: str | None = None): ...

	# Should not raise
	parse_fn_signature(ok)


def test_parse_fn_signature_requires_key_param():
	def bad(*children: Child):
		return cast(Element, None)

	with pytest.raises(ValueError, match=r"must define a `key: str \| None = None`"):
		parse_fn_signature(bad)


def test_parse_fn_signature_key_must_default_to_none():
	def bad(*children: Child, key: str | None = "abc"):
		return cast(Element, None)

	with pytest.raises(ValueError, match=r"'key' parameter must default to None"):
		parse_fn_signature(bad)


def test_parse_fn_signature_disallow_positional_only_params():
	def bad(a, /, *children: Child, key: str | None = None):
		return cast(Element, None)

	with pytest.raises(
		ValueError,
		match=r"must not declare positional-only parameters besides \*children",
	):
		parse_fn_signature(bad)


def test_parse_fn_signature_children_annotation_must_be_child():
	def bad(*children: int, key: str | None = None): ...

	with pytest.raises(
		TypeError, match=r"\*children must be annotated as `\*children: ps.Child`"
	):
		parse_fn_signature(bad)


def test_parse_fn_signature_additional_required_positional_is_disallowed():
	def bad(x, *children: Child, key: str | None = None):
		return cast(Element, None)

	with pytest.raises(
		ValueError, match=r"must not declare additional required positional parameters"
	):
		parse_fn_signature(bad)


def test_parse_fn_signature_annotated_param_with_prop_metadata_is_disallowed():
	def bad(
		*children: Child,
		key: str | None = None,
		title: Annotated[str, prop(default="hi")],
	):
		return cast(Element, None)

	with pytest.raises(TypeError, match=r"Annotated\[.*ps\.prop"):
		parse_fn_signature(bad)


def test_parse_fn_signature_explicit_and_unpack_overlap_raises():
	class P(TypedDict):
		title: str

	def bad(
		*children: Child,
		key: str | None = None,
		title: str = "t",
		**props: Unpack[P],  # type: ignore
	):
		return cast(Element, None)

	with pytest.raises(ValueError, match=r"Conflicting prop definitions for: title"):
		parse_fn_signature(bad)


def test_parse_fn_signature_builds_propspec_from_annotation_and_defaults():
	DEFAULT_TITLE_PROP: Any = prop(default="Untitled")

	class P(TypedDict, total=False):
		count: Required[int]

	def good(
		*children: Child,
		key: str | None = None,
		title: str = DEFAULT_TITLE_PROP,
		disabled: bool = False,
		**props: Unpack[P],
	):
		return cast(Element, None)

	spec = parse_fn_signature(good)
	assert set(spec.keys()) == {"title", "disabled", "count"}
	title = cast(Prop, spec["title"])
	disabled = cast(Prop, spec["disabled"])
	count = cast(Prop, spec["count"])
	assert title._type is str
	assert title.default == "Untitled"
	assert disabled._type is bool
	assert disabled.default is False
	assert count._type is int
	assert count.required is True


def test_react_component_decorator_explicit_props_and_children():
	TITLE_DEFAULT = prop(default="Untitled")

	@react_component(name="Card", src="./Card")
	def Card(
		*children: Child,
		key: str | None = None,
		title: str = TITLE_DEFAULT,
		disabled: bool = False,
	) -> Element:
		return cast(Element, None)

	# With children and partial props (title default applies)
	node = Card(p()["Body"], disabled=True)
	assert isinstance(node, Node)
	assert node.tag == "$$Card"
	assert node.props == {"title": "Untitled", "disabled": True}
	assert node.children is not None and len(node.children) == 1

	# Unknown prop should be rejected since spec is closed
	with pytest.raises(ValueError, match=r"Unexpected prop\(s\) for component 'Card'"):
		Card(unknown=1)  # type: ignore


def test_react_component_decorator_typed_dict_unpack_and_mapping():
	class Props(TypedDict, total=False):
		label: Required[str]
		class_name: Annotated[str, prop(map_to="className")]
		count: NotRequired[int]

	@react_component(name="Badge", src="./Badge")
	def Badge(
		*children: Child,
		key: str | None = None,
		disabled: bool = False,
		**props: Unpack[Props],
	) -> Element:
		return cast(Element, None)

	# Missing required label -> error
	with pytest.raises(ValueError, match=r"Missing required props: label"):
		Badge()  # type: ignore

	node = Badge("txt", label="New", class_name="pill", count=2, disabled=True)
	assert node.tag == "$$Badge"
	# class_name mapped to className, label preserved
	assert node.props == {
		"disabled": True,
		"label": "New",
		"className": "pill",
		"count": 2,
	}
	assert node.children == ("txt",)


def test_react_component_decorator_default_export_and_alias_rules():
	# default export allowed
	@react_component(name="DefaultComp", src="./Comp", is_default=True)
	def DefaultComp(*children: Child, key: str | None = None) -> Element:
		return cast(Element, None)

	node = DefaultComp()
	assert node.tag == "$$DefaultComp"


def test_react_component_decorator_key_validation():
	@react_component(name="Box", src="./Box")
	def Box(*children: Child, key: str | None = None) -> Element:
		return cast(Element, None)

	# Non-string key should raise
	with pytest.raises(ValueError, match=r"key must be a string or None"):
		Box(key=123)  # type: ignore[arg-type]

	# String key accepted
	node = Box(key="k1")
	assert node.tag == "$$Box"
	assert node.key == "k1"


def test_react_component_decorator_untyped_kwargs_allows_unknown():
	@react_component(name="Pane", src="./Pane")
	def Pane(
		*children: Child,
		key: str | None = None,
		disabled: bool = False,
		**props,
	) -> Element:
		return cast(Element, None)

	# Should not raise for unknown props
	node = Pane(dataAttr=1)
	# Unknowns are allowed and included since untyped kwargs are allowed
	assert node.props == {"disabled": False, "dataAttr": 1}


def test_default_sentinel_omits_explicit_prop():
	@react_component(name="CardDefaultExplicit", src="./Card")
	def Card(
		*children: Child,
		key: str | None = None,
		title: str = "Untitled",
		disabled: bool = DEFAULT,
	) -> Element:
		return cast(Element, None)

	# Passing DEFAULT should omit the prop entirely
	node = Card()
	assert node.tag == "$$CardDefaultExplicit"
	assert node.props == {"title": "Untitled"}

	# Passing None should keep the key with None value (serialize to null client-side)
	node_none = Card(title=cast(Any, None), disabled=False)
	assert node_none.props == {"title": None, "disabled": False}


def test_default_sentinel_omits_unpack_prop_and_skips_serialize():
	# Serializer that must not be called if DEFAULT is provided
	def bomb(x: object) -> Any:
		raise AssertionError("serialize should not be called when DEFAULT is used")

	class Props(TypedDict):
		label: NotRequired[Annotated[str, prop(serialize=bomb)]]

	@react_component(name="BadgeDefaultUnpack", src="./Badge")
	def Badge(
		*children: Child,
		key: str | None = None,
		**props: Unpack[Props],
	) -> Element:
		return cast(Element, None)

	node = Badge()
	assert node.tag == "$$BadgeDefaultUnpack"
	# Omitted entirely
	assert node.props is None


def test_default_sentinel_omits_unknown_when_untyped_kwargs():
	@react_component(name="PaneDefaultUnknown", src="./Pane")
	def Pane(
		*children: Child,
		key: str | None = None,
		disabled: bool = False,
		**props,
	) -> Element:
		return cast(Element, None)

	node = Pane(dataAttr=DEFAULT)
	# Unknowns are allowed but DEFAULT should ensure omission
	assert node.tag == "$$PaneDefaultUnknown"
	assert node.props == {"disabled": False}


def test_default_sentinel_props_in_fn_and_typed_dict():
	class PaneProps(TypedDict):
		label: NotRequired[Annotated[str, prop(DEFAULT)]]
		# This one should be required, despite the DEFAULT value
		name: Annotated[str, prop(DEFAULT)]

	@react_component(name="Pane", src="./Pane")
	def Pane(
		*children: Child,
		key: str | None = None,
		disabled: bool = DEFAULT,
		**props: Unpack[PaneProps],
	) -> Element:
		return cast(Element, None)

	node = Pane(name="hi")
	assert node.props == {"name": "hi"}


def test_parse_typed_dict_props_inheritance_two_levels():
	class BaseProps(TypedDict):
		a: int
		b: NotRequired[str]

	class MidProps(BaseProps, total=False):
		c: Required[bool]
		d: float  # optional because total=False

	class FinalProps(MidProps):
		e: NotRequired[Annotated[int, prop(map_to="ee")]]

	def fn(*children: Child, key: str | None = None, **props: Unpack[FinalProps]): ...

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	spec = parse_typed_dict_props(var_kw)

	# Keys present from all inheritance levels
	keys = ["a", "b", "c", "d", "e"]
	assert set(spec.keys()) == set(keys)

	a, b, c, d, e = [spec[k] for k in keys]

	assert a.required is True and a._type is int
	assert b.required is False and b._type is str
	assert c.required is True and c._type is bool
	assert d.required is False and d._type is float
	assert e.required is False and e._type is int and e.map_to == "ee"

	# Apply should accept only requireds and map e->ee when provided
	applied_min = spec.apply("Final", {"a": 1, "c": False})
	assert applied_min == {"a": 1, "c": False}

	applied_with_e = spec.apply("Final", {"a": 1, "c": True, "e": 7})
	assert applied_with_e == {"a": 1, "c": True, "ee": 7}


def test_parse_typed_dict_props_generic_like_typed_dict_with_typevars():
	T = TypeVar("T")

	class GenericLikeProps(TypedDict, Generic[T]):
		required: T
		optional: NotRequired[list[T]]

	def fn(*children: Child, key: str | None = None, **props: Unpack[GenericLikeProps]):
		return cast(Element, None)

	var_kw = list(inspect.signature(fn).parameters.values())[-1]
	spec = parse_typed_dict_props(var_kw)

	# Keys and required/optional inference
	assert set(spec.keys()) == {"required", "optional"}
	required_prop = cast(Prop, spec["required"])
	optional_prop = cast(Prop, spec["optional"])

	# total=True by default: required is required, optional is NotRequired
	assert required_prop.required is True
	assert optional_prop.required is False

	# Runtime types: TypeVar collapses to object, parametrized containers map to their origin
	assert required_prop._type is object
	assert optional_prop._type is list


def test_react_component_accepts_generic_like_typed_dict_props():
	T = TypeVar("T")

	class Parent(TypedDict, total=False):
		label: str

	class DataProps(Parent, Generic[T], total=False):
		value: T

	@react_component(name="DataBox", src="./DataBox")
	def DataBox(
		*children: Child, key: str | None = None, **props: Unpack[DataProps[int]]
	) -> Element:
		return cast(Element, None)

	node = DataBox(value=123, label="n")
	assert isinstance(node, Node)
	assert node.tag == "$$DataBox"
	# Value typed by TypeVar should be accepted and passed through unchanged
	assert node.props == {"value": 123, "label": "n"}
