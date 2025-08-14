"""
Tests for React component integration in pulse.html.

This module tests the system for defining and using React components
within the UI tree generation system.
"""

import pytest
from typing import Optional, TypedDict, Unpack, NotRequired, Literal, Union, Any, cast

import pulse as ps
from pulse import (
    Node,
    VDOMNode,
    div,
    p,
    h1,
    react_component,
    prop,
)
from pulse.react_component import (
    COMPONENT_REGISTRY,
    ComponentRegistry,
    ReactComponent,
    PropSpec,
    Prop,
)
from pulse.tests.test_utils import assert_node_equal
from pulse.vdom import NodeTree


class TestReactComponent:
    """Test the ReactComponent class."""

    def test_component_creation(self):
        """Test creating ReactComponent instances."""
        component = ReactComponent(
            tag="TestComponent",
            import_path="./TestComponent",
            alias="test-component",
            is_default=False,
        )

        assert component.key == "test-component"
        assert component.import_path == "./TestComponent"
        assert component.tag == "TestComponent"
        assert not component.is_default

    def test_component_with_default_export(self):
        """Test ReactComponent with default export."""
        component = ReactComponent(
            tag="default-component",
            import_path="./DefaultComponent",
            is_default=True,
        )

        assert component.key == "default-component"
        assert component.import_path == "./DefaultComponent"
        # For default exports, the tag is the key, and the conceptual "export name" is "default"
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
            tag="TestComponent",
            import_path="./TestComponent",
            alias="test",
            is_default=False,
        )

        # Should return a callable
        assert callable(TestComponent)

        # Component should be registered
        components = COMPONENT_REGISTRY.get().items()
        assert "test" in components
        assert components["test"].tag == "TestComponent"
        assert components["test"].import_path == "./TestComponent"
        assert not components["test"].is_default

    def test_define_component_default_export(self):
        """Test defining a component with default export."""
        ReactComponent(
            tag="default-comp", import_path="./DefaultComponent", is_default=True
        )

        components = COMPONENT_REGISTRY.get().items()
        assert "default-comp" in components
        assert components["default-comp"].is_default

    def test_component_mount_point_creation(self):
        """Test that defined components create mount points."""
        TestComponent = ReactComponent(
            tag="TestComponent",
            import_path="./TestComponent",
            alias="test-component",
            is_default=False,
        )

        # Create a mount point
        mount_point = TestComponent(prop1="value1", prop2="value2")

        assert mount_point.tag == "$$test-component"
        assert mount_point.props == {"prop1": "value1", "prop2": "value2"}
        assert mount_point.children is None

    def test_component_with_children(self):
        """Test creating mount points with children."""
        Container = ReactComponent(
            tag="Container",
            import_path="./Container",
            alias="container",
            is_default=False,
        )

        # Create mount point with children
        mount_point = Container(
            "Text child", p()["Paragraph child"], className="container"
        )

        assert mount_point.tag == "$$container"
        assert mount_point.props == {"className": "container"}
        assert mount_point.children is not None
        assert len(mount_point.children) == 2
        assert mount_point.children[0] == "Text child"
        p_child = mount_point.children[1]
        assert isinstance(p_child, Node) and p_child.tag == "p"

    def test_component_with_indexing_syntax(self):
        """Test using indexing syntax with React components."""
        Card = ReactComponent(
            tag="Card", import_path="./Card", alias="card", is_default=False
        )

        # Use indexing syntax
        mount_point = Card(title="Test Card")[p()["Card content"], "Additional text"]

        assert mount_point.tag == "$$card"
        assert mount_point.props == {"title": "Test Card"}
        assert mount_point.children is not None
        assert len(mount_point.children) == 2
        p_child = mount_point.children[0]
        assert isinstance(p_child, Node) and p_child.tag == "p"
        assert mount_point.children[1] == "Additional text"

    def test_multiple_components(self):
        """Test defining multiple components."""
        ReactComponent("Button", "./Button", "button", False)
        ReactComponent("Input", "./Input", "input", False)
        ReactComponent("Modal", "./Modal", "modal", False)

        components = COMPONENT_REGISTRY.get().items()

        assert len(components) == 3
        assert "button" in components
        assert "input" in components
        assert "modal" in components

    def test_component_overwrite(self):
        """Test that defining a component with same key raises an error."""
        # Define first component
        ReactComponent("First", "./First", "test", False)

        # Define second component with same key
        with pytest.raises(ValueError):
            ReactComponent("Second", "./Second", "test", False)


class TestComponentRegistry:
    """Test the component registry functionality."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_empty_registry(self):
        """Test empty component registry."""
        components = COMPONENT_REGISTRY.get().items()
        assert components == {}

    def test_registry_isolation(self):
        """Test that get_registered_components returns a copy."""
        ReactComponent("Test", "./Test", "test", False)

        components1 = COMPONENT_REGISTRY.get().items()
        components2 = COMPONENT_REGISTRY.get().items()

        # Should be equal but not the same object
        assert components1 == components2
        assert components1 is not components2

        # Modifying one shouldn't affect the other
        components1["new"] = ReactComponent("New", "./New", "new", False)
        assert "new" not in components2


class TestMountPointGeneration:
    """Test mount point generation from React components."""

    def setup_method(self):
        """Clear the component registry before each test."""
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_mount_point_tag_format(self):
        """Test that mount points have correct tag format."""
        TestComp = ReactComponent("Test", "./Test", "test-component", False)
        mount_point = TestComp()
        assert mount_point.tag == "$$test-component"

    def test_mount_point_serialization(self):
        """Test that mount points serialize correctly."""
        Counter = ReactComponent("Counter", "./Counter", "counter", False)

        mount_point = Counter(count=5, label="Test Counter")[
            p()["Counter description"], "Additional text"
        ]

        expected: VDOMNode = {
            "tag": "$$counter",
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
        Card = ReactComponent("Card", "./Card", "card", False)
        Button = ReactComponent("Button", "./Button", "button", False)

        nested_structure = Card(title="Nested Example")[
            p()["This card contains a button:"],
            Button(variant="primary")["Click me!"],
            "And some additional text.",
        ]

        expected: VDOMNode = {
            "tag": "$$card",
            "props": {"title": "Nested Example"},
            "children": [
                {"tag": "p", "props": {}, "children": ["This card contains a button:"]},
                {
                    "tag": "$$button",
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
        UserCard = ReactComponent("UserCard", "./UserCard", "user-card", False)
        Counter = ReactComponent("Counter", "./Counter", "counter", False)

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
                    "tag": "$$user-card",
                    "props": {"name": "John Doe", "email": "john@example.com"},
                    "children": None,
                },
                {"tag": "p", "props": {}, "children": ["Some regular HTML content"]},
                {
                    "tag": "$$counter",
                    "props": {"count": 42},
                    "children": ["This counter has children"],
                },
                {"tag": "div", "props": {}, "children": ["More HTML content"]},
            ],
        }

        assert_node_equal(mixed_structure, Node.from_vdom(expected))

    def test_component_props_types(self):
        """Test that component props handle various data types."""
        DataComponent = ReactComponent("Data", "./Data", "data", False)

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


class TestPropsAndHintValidation:
    def setup_method(self):
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_props_missing_required_raises(self):
        spec = PropSpec({"title": str}, total=True)
        Comp = ReactComponent("Card", "./Card", "card", False, props=spec)
        with pytest.raises(ValueError):
            Comp()

    def test_props_unexpected_raises(self):
        spec = PropSpec({"title": str}, total=False)
        Comp = ReactComponent("Card", "./Card", "card", False, props=spec)
        with pytest.raises(ValueError):
            Comp(unknown=1)

    def test_props_defaults_and_factories_and_serialize(self):
        spec = PropSpec(
            {
                "title": Prop(str, default="Untitled"),
                "count": Prop(int, default_factory=lambda: 2),
                "flag": Prop(bool, default=False, serialize=lambda b: int(b)),
            },
            total=False,
        )
        Comp = ReactComponent("Card", "./Card", "card", False, props=spec)
        n = Comp()
        assert n.props == {"title": "Untitled", "count": 2, "flag": 0}

    def test_props_type_mismatch_raises(self):
        spec = PropSpec({"count": int})
        Comp = ReactComponent("Counter", "./Counter", "counter", False, props=spec)
        with pytest.raises(TypeError):
            Comp(count="x")

    def test_hint_valid_no_children(self):
        def hint(*, key: Optional[str] = None, value: int = 0):
            return "ok"

        ReactComponent("X", "./X", "x", False, fn_signature=hint)

    def test_hint_valid_with_children(self):
        def hint(*children: NodeTree, key: Optional[str] = None, value: int = 0):
            return "ok"

        ReactComponent("X", "./X", "x", False, fn_signature=hint)

    def test_hint_children_wrong_annotation_raises(self):
        def bad(*children: int, key: Optional[str] = None):
            return "bad"

        with pytest.raises(TypeError):
            ReactComponent("X", "./X", "x", False, fn_signature=bad)

    def test_hint_missing_key_raises(self):
        def bad(*children: NodeTree):
            return "bad"

        with pytest.raises(ValueError):
            ReactComponent("X", "./X", "x", False, fn_signature=bad)

    def test_hint_key_wrong_default_raises(self):
        def bad(*children: NodeTree, key: Optional[str] = "x"):
            return "bad"

        with pytest.raises(ValueError):
            ReactComponent("X", "./X", "x", False, fn_signature=bad)

    def test_hint_extra_fixed_positional_raises(self):
        def bad(x, *children: NodeTree, key: Optional[str] = None):
            return "bad"

        with pytest.raises(ValueError):
            ReactComponent("X", "./X", "x", False, fn_signature=bad)


class TestReactDecorator:
    def setup_method(self):
        COMPONENT_REGISTRY.set(ComponentRegistry())

    def test_decorator_with_unpacked_typeddict_and_children(self):
        class AccordionProps(TypedDict, total=False):
            open: bool
            other: str

        @react_component(tag="Accordion", import_="./Accordion")
        def accordion(
            *children: NodeTree,
            key: Optional[str] = None,
            **props: Unpack[AccordionProps],
        ) -> NodeTree:
            return "hint"

        # Should be callable and registered
        assert callable(accordion)
        assert COMPONENT_REGISTRY.get().get("Accordion") is not None

        n = accordion("child", open=True)
        assert n.tag == "$$Accordion"
        assert n.props == {"open": True}
        assert n.children is not None and len(n.children) == 1

        # Type mismatch raises
        with pytest.raises(TypeError):
            accordion(open=cast(Any, "yes"))

        # Unknown prop raises
        with pytest.raises(ValueError):
            cast(Any, accordion)(bad=1)

    def test_decorator_no_children_signature(self):
        class TooltipProps(TypedDict):
            text: str

        @react_component(tag="Tooltip", import_="./Tooltip")
        def tooltip(
            *, key: Optional[str] = None, **props: Unpack[TooltipProps]
        ) -> NodeTree:
            return "hint"

        n = tooltip(text="hi")
        assert n.tag == "$$Tooltip"
        assert n.props == {"text": "hi"}
        assert n.children is None

    def test_decorator_without_props_allows_only_key(self):
        @react_component(tag="Badge", import_="./Badge")
        def badge(*, key: Optional[str] = None) -> NodeTree:
            return "hint"

        badge(key="k1")
        with pytest.raises(ValueError):
            cast(Any, badge)(color="red")

    def test_required_notrequired_and_total(self):
        class Cfg(TypedDict, total=True):
            a: int
            b: NotRequired[str]

        @react_component(tag="Cfg", import_="./Cfg")
        def cfg(*, key: Optional[str] = None, **props: Unpack[Cfg]) -> NodeTree:
            return "hint"

        # missing required raises
        with pytest.raises(ValueError):
            cast(Any, cfg)()
        # optional omitted OK
        n = cfg(a=1)
        assert n.props == {"a": 1}
        # wrong type raises
        with pytest.raises(TypeError):
            cfg(a=cast(Any, "1"))

    def test_literal_and_union(self):
        class BtnProps(TypedDict, total=False):
            size: Literal["sm", "md", "lg"]
            id_or_num: Union[int, str]

        @react_component(tag="Btn", import_="./Btn")
        def btn(*, key: Optional[str] = None, **props: Unpack[BtnProps]) -> NodeTree:
            return "hint"

        btn(size="sm")
        btn(id_or_num=10)
        btn(id_or_num="x")
        with pytest.raises(TypeError):
            btn(size=cast(Any, 1))  # wrong type

    def test_nested_typeddict_field(self):
        class Inner(TypedDict):
            x: int

        class Outer(TypedDict, total=False):
            inner: Inner

        @react_component(tag="Outer", import_="./Outer")
        def outer(*, key: Optional[str] = None, **props: Unpack[Outer]) -> NodeTree:
            return "hint"

        # nested TypedDict is treated as dict at runtime
        outer(inner={"x": 1})
        with pytest.raises(TypeError):
            outer(inner=cast(Any, 1))

    def test_prop_inference_and_defaults(self):
        class Defaults(TypedDict, total=False):
            a: int = ps.prop(default=1)
            b: str = ps.prop(default="x")
            c: bool = ps.prop(default=True)

        @react_component(tag="D", import_="./D")
        def D(*, key: Optional[str] = None, **props: Unpack[Defaults]) -> NodeTree:
            return "hint"

        n = D()
        assert n.props == {"a": 1, "b": "x", "c": True}

        with pytest.raises(TypeError):
            D(a=cast(Any, "1"))

    def test_serializer(self):
        class SProps(TypedDict, total=False):
            val: int = ps.prop(prop(default=2, serialize=lambda v: str(v)))

        object.__setattr__(
            SProps,
            "val",
        )

        @react_component(tag="S", import_="./S")
        def S(*, key: Optional[str] = None, **props: Unpack[SProps]) -> NodeTree:
            return "hint"

        assert S().props == {"val": "2"}
        assert S(val=3).props == {"val": "3"}

    def test_map_to_and_conflict(self):
        class MProps(TypedDict, total=False):
            href: str
            to: str

        object.__setattr__(MProps, "href", prop(map_to="to"))

        @react_component(tag="M", import_="./M")
        def M(*, key: Optional[str] = None, **props: Unpack[MProps]) -> NodeTree:
            return "hint"

        # href maps to 'to'
        assert M(href="/a").props == {"to": "/a"}
        # setting both href and to is allowed; last one wins at Python level since unknown props are validated
        assert M(to="/b").props == {"to": "/b"}

        # Conflicting map_to targets across two different fields
        class Bad(TypedDict, total=False):
            a: int
            b: int

        object.__setattr__(Bad, "a", prop(map_to="x"))
        object.__setattr__(Bad, "b", prop(map_to="x"))

        @react_component(tag="Bad", import_="./Bad")
        def BadC(*, key: Optional[str] = None, **props: Unpack[Bad]) -> NodeTree:
            return "hint"

        with pytest.raises(ValueError):
            BadC(a=1)

    def test_enforces_unpack_annotation_and_typed_dict(self):
        # Missing **props entirely is allowed (covered elsewhere)

        # Bad: **props without Unpack
        def bad1(*, key: Optional[str] = None, **props) -> NodeTree:
            return "hint"

        with pytest.raises(TypeError):
            react_component(tag="Bad1", import_="./Bad1")(bad1)

        # Bad: Unpack but not a TypedDict
        def bad2(
            *,
            key: Optional[str] = None,
            **props: Unpack[dict[str, int]],  # type: ignore[type-arg]
        ) -> NodeTree:
            return "hint"

        with pytest.raises(TypeError):
            react_component(tag="Bad2", import_="./Bad2")(bad2)

    def test_signature_rules_on_children_and_key(self):
        # Wrong children annotation
        def bad_children(*children: int, key: Optional[str] = None) -> NodeTree:
            return "hint"

        with pytest.raises(TypeError):
            react_component(tag="X", import_="./X")(bad_children)

        # Missing key
        def bad_missing_key(*children: NodeTree):
            return "hint"

        with pytest.raises(ValueError):
            react_component(tag="Y", import_="./Y")(bad_missing_key)

        # Wrong key default
        def bad_key_default(*children: NodeTree, key: Optional[str] = "x") -> NodeTree:
            return "hint"

        with pytest.raises(ValueError):
            react_component(tag="Z", import_="./Z")(bad_key_default)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
