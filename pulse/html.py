"""
HTML library that generates UI tree nodes directly.

This library provides a Python API for building UI trees that match
the TypeScript UINode format exactly, eliminating the need for translation.
"""

from typing import (
    Any,
    Dict,
    List,
    Optional,
    Callable,
    Sequence,
    Union,
)
import random

__all__ = [
    # Core types and functions
    "UITreeNode",
    "define_tag",
    "define_self_closing_tag",
    # UI Tree integration
    "ReactComponent",
    "define_react_component",
    "Route",
    "define_route",
    # Standard tags
    "a",
    "abbr",
    "address",
    "article",
    "aside",
    "audio",
    "b",
    "bdi",
    "bdo",
    "blockquote",
    "body",
    "button",
    "canvas",
    "caption",
    "cite",
    "code",
    "colgroup",
    "data",
    "datalist",
    "dd",
    "del_",
    "details",
    "dfn",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hgroup",
    "html",
    "i",
    "iframe",
    "ins",
    "kbd",
    "label",
    "legend",
    "li",
    "main",
    "map_",
    "mark",
    "menu",
    "meter",
    "nav",
    "noscript",
    "object_",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "picture",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "script",
    "section",
    "select",
    "small",
    "span",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "template",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "u",
    "ul",
    "var",
    "video",
    # Self-closing tags
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
]


# ============================================================================
# Core UI Tree Node
# ============================================================================


class UITreeNode:
    """
    A UI tree node that matches the TypeScript UIElementNode format.
    This directly generates the structure expected by the React frontend.
    """

    def __init__(
        self,
        tag: str,
        props: Dict[str, Any] | None = None,
        children: Sequence["UITreeNode | str"] | None = None,
        node_id: str | None = None,
    ):
        self.id = node_id or f"py_{random.randint(100000, 999999)}"
        self.tag = tag
        self.props = props or {}
        self.children = children or []

    def __getitem__(
        self,
        children_arg: Union["UITreeNode", str, tuple[Union["UITreeNode", str], ...]],
    ):
        """Support indexing syntax: div()[children] or div()["text"]"""
        if self.children:
            raise ValueError(f"Node already has children: {self.children}")

        if isinstance(children_arg, (list, tuple)):
            new_children = list(children_arg)
        else:
            new_children = [children_arg]

        return UITreeNode(
            tag=self.tag,
            props=self.props.copy(),
            children=new_children,
            node_id=self.id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        return {
            "id": self.id,
            "tag": self.tag,
            "props": self.props,
            "children": [
                child.to_dict() if isinstance(child, UITreeNode) else child
                for child in self.children
            ],
        }


# ============================================================================
# Tag Definition Functions
# ============================================================================


def define_tag(name: str, default_props: Dict[str, Any] | None = None):
    """
    Define a standard HTML tag that creates UITreeNode instances.

    Args:
        name: The tag name (e.g., "div", "span")
        default_props: Default props to apply to all instances

    Returns:
        A function that creates UITreeNode instances
    """
    default_props = default_props or {}

    def create_element(*children: Union[UITreeNode, str], **props: Any) -> UITreeNode:
        """Create a UITreeNode for this tag."""
        merged_props = {**default_props, **props}
        return UITreeNode(
            tag=name, props=merged_props, children=list(children) if children else []
        )

    return create_element


def define_self_closing_tag(name: str, default_props: Dict[str, Any] | None = None):
    """
    Define a self-closing HTML tag that creates UITreeNode instances.

    Args:
        name: The tag name (e.g., "br", "img")
        default_props: Default props to apply to all instances

    Returns:
        A function that creates UITreeNode instances (no children allowed)
    """
    default_props = default_props or {}

    def create_element(**props: Any) -> UITreeNode:
        """Create a self-closing UITreeNode for this tag."""
        merged_props = {**default_props, **props}
        return UITreeNode(
            tag=name,
            props=merged_props,
            children=[],  # Self-closing tags never have children
        )

    return create_element


# ============================================================================
# React Component Integration
# ============================================================================


class ReactComponent:
    """
    Represents a React component that can be imported and used in the UI tree.
    """

    def __init__(
        self,
        component_key: str,
        import_path: str,
        export_name: str = "default",
        is_default_export: bool = True,
    ):
        self.component_key = component_key
        self.import_path = import_path
        self.export_name = export_name
        self.is_default_export = is_default_export


def define_react_component(
    component_key: str,
    import_path: str,
    export_name: str = "default",
    is_default_export: bool = True,
) -> Callable[..., UITreeNode]:
    """
    Define a React component that can be used within the UI tree.
    Returns a function that creates mount point UITreeNode instances.

    Args:
        component_key: Unique key for the component registry
        import_path: Path to import the component from
        export_name: Name of the export (use "default" for default exports)
        is_default_export: Whether this is a default export

    Returns:
        A function that creates UITreeNode instances with mount point tags
    """
    component = ReactComponent(
        component_key, import_path, export_name, is_default_export
    )

    # Store the component definition globally for later retrieval
    if not hasattr(define_react_component, "_components"):
        define_react_component._components = {}
    define_react_component._components[component_key] = component

    def create_mount_point(
        *children: Union[UITreeNode, str], **props: Any
    ) -> UITreeNode:
        """Create a mount point UITreeNode for this React component."""
        return UITreeNode(
            tag=f"$${component_key}",
            props=props,
            children=list(children) if children else [],
        )

    return create_mount_point


def get_registered_components() -> Dict[str, ReactComponent]:
    """Get all registered React components."""
    if not hasattr(define_react_component, "_components"):
        return {}
    return define_react_component._components.copy()


# ============================================================================
# Route Definition
# ============================================================================


class Route:
    """
    Represents a route definition with its component dependencies.
    """

    def __init__(
        self,
        path: str,
        render_func: Callable[[], UITreeNode],
        components: List[ReactComponent],
    ):
        self.path = path
        self.render_func = render_func
        self.components = components


def define_route(
    path: str, components: List[str] | None = None
) -> Callable[[Callable[[], UITreeNode]], Route]:
    """
    Decorator to define a route with its component dependencies.

    Args:
        path: URL path for the route
        components: List of component keys used by this route

    Returns:
        Decorator function
    """

    def decorator(render_func: Callable[[], UITreeNode]) -> Route:
        # Get the actual ReactComponent objects for the component keys
        all_components = get_registered_components()
        route_components = []

        if components:
            for component_key in components:
                if component_key in all_components:
                    route_components.append(all_components[component_key])
                else:
                    raise ValueError(
                        f"Component '{component_key}' not found. Make sure to define it before using in routes."
                    )

        return Route(path, render_func, route_components)

    return decorator


# ============================================================================
# Standard HTML Tags
# ============================================================================

# Regular tags
a = define_tag("a")
abbr = define_tag("abbr")
address = define_tag("address")
article = define_tag("article")
aside = define_tag("aside")
audio = define_tag("audio")
b = define_tag("b")
bdi = define_tag("bdi")
bdo = define_tag("bdo")
blockquote = define_tag("blockquote")
body = define_tag("body")
button = define_tag("button")
canvas = define_tag("canvas")
caption = define_tag("caption")
cite = define_tag("cite")
code = define_tag("code")
colgroup = define_tag("colgroup")
data = define_tag("data")
datalist = define_tag("datalist")
dd = define_tag("dd")
del_ = define_tag("del")
details = define_tag("details")
dfn = define_tag("dfn")
dialog = define_tag("dialog")
div = define_tag("div")
dl = define_tag("dl")
dt = define_tag("dt")
em = define_tag("em")
fieldset = define_tag("fieldset")
figcaption = define_tag("figcaption")
figure = define_tag("figure")
footer = define_tag("footer")
form = define_tag("form", {"method": "POST"})
h1 = define_tag("h1")
h2 = define_tag("h2")
h3 = define_tag("h3")
h4 = define_tag("h4")
h5 = define_tag("h5")
h6 = define_tag("h6")
head = define_tag("head")
header = define_tag("header")
hgroup = define_tag("hgroup")
html = define_tag("html")
i = define_tag("i")
iframe = define_tag("iframe")
ins = define_tag("ins")
kbd = define_tag("kbd")
label = define_tag("label")
legend = define_tag("legend")
li = define_tag("li")
main = define_tag("main")
map_ = define_tag("map")
mark = define_tag("mark")
menu = define_tag("menu")
meter = define_tag("meter")
nav = define_tag("nav")
noscript = define_tag("noscript")
object_ = define_tag("object")
ol = define_tag("ol")
optgroup = define_tag("optgroup")
option = define_tag("option")
output = define_tag("output")
p = define_tag("p")
picture = define_tag("picture")
pre = define_tag("pre")
progress = define_tag("progress")
q = define_tag("q")
rp = define_tag("rp")
rt = define_tag("rt")
ruby = define_tag("ruby")
s = define_tag("s")
samp = define_tag("samp")
script = define_tag("script", {"type": "text/javascript"})
section = define_tag("section")
select = define_tag("select")
small = define_tag("small")
span = define_tag("span")
strong = define_tag("strong")
style = define_tag("style", {"type": "text/css"})
sub = define_tag("sub")
summary = define_tag("summary")
sup = define_tag("sup")
table = define_tag("table")
tbody = define_tag("tbody")
td = define_tag("td")
template = define_tag("template")
textarea = define_tag("textarea")
tfoot = define_tag("tfoot")
th = define_tag("th")
thead = define_tag("thead")
time = define_tag("time")
title = define_tag("title")
tr = define_tag("tr")
u = define_tag("u")
ul = define_tag("ul")
var = define_tag("var")
video = define_tag("video")

# Self-closing tags
area = define_self_closing_tag("area")
base = define_self_closing_tag("base")
br = define_self_closing_tag("br")
col = define_self_closing_tag("col")
embed = define_self_closing_tag("embed")
hr = define_self_closing_tag("hr")
img = define_self_closing_tag("img")
input = define_self_closing_tag("input")
link = define_self_closing_tag("link")
meta = define_self_closing_tag("meta")
param = define_self_closing_tag("param")
source = define_self_closing_tag("source")
track = define_self_closing_tag("track")
wbr = define_self_closing_tag("wbr")


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    # Test the direct UI tree generation
    test_node = div(className="container")[
        h1()["Test Title"],
        p()["This is a test paragraph."],
        button(onClick="alert('clicked!')")["Click Me"],
    ]

    import json

    print(json.dumps(test_node.to_dict(), indent=2))
