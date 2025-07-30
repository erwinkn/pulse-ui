"""
HTML library that generates UI tree nodes directly.

This library provides a Python API for building UI trees that match
the TypeScript UINode format exactly, eliminating the need for translation.
"""

from typing import (
    Any,
    Optional,
    Callable,
    Sequence,
    Union,
)
import random
import uuid

__all__ = [
    # Core types and functions
    "Node",
    "Callback",
    "define_tag",
    "define_self_closing_tag",
    # Callback system
    "register_callback",
    "get_callback",
    "clear_callbacks",
    "get_all_callbacks",
    "execute_callback",
    "prepare_ui_response",
    # UI Tree integration
    "ReactComponent",
    "ReactComponent",
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
# Callback System
# ============================================================================


class Callback:
    """
    Wrapper for callback functions that can be passed as props.
    This allows the system to detect and register callbacks efficiently.
    """

    def __init__(self, func: Callable[[], None]):
        if not callable(func):
            raise ValueError("Callback must be a callable function")
        self.func = func
        self.id = str(uuid.uuid4())

    def __call__(self):
        """Make Callback instances callable."""
        return self.func()


# Global callback registry: callback_key -> function
_callback_registry: dict[str, Callable[[], None]] = {}


def register_callback(callback_key: str, func: Callable[[], None]) -> None:
    """Register a callback function with a unique key."""
    _callback_registry[callback_key] = func


def get_callback(callback_key: str) -> Optional[Callable[[], None]]:
    """Get a registered callback function by key."""
    return _callback_registry.get(callback_key)


def clear_callbacks() -> None:
    """Clear all registered callbacks."""
    _callback_registry.clear()


def get_all_callbacks() -> dict[str, Callable[[], None]]:
    """Get all registered callbacks."""
    return _callback_registry.copy()


def execute_callback(callback_key: str) -> bool:
    """Execute a registered callback by its key. Returns True if successful."""
    callback_func = get_callback(callback_key)
    if callback_func:
        try:
            callback_func()
            return True
        except Exception as e:
            print(f"Error executing callback {callback_key}: {e}")
            return False
    return False


def prepare_ui_response(
    root_node: "Node",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Prepare a complete UI response with the tree and callback information.

    Returns:
        Tuple of (ui_tree_dict, callback_info_dict)
    """
    ui_tree = root_node.to_dict()
    callback_info = root_node.get_callback_info()
    return ui_tree, callback_info


# ============================================================================
# Core UI Tree Node
# ============================================================================

NodeChild = Union["Node", str, int, bool, float]


class Node:
    """
    A UI tree node that matches the TypeScript UIElementNode format.
    This directly generates the structure expected by the React frontend.
    """

    def __init__(
        self,
        tag: str,
        props: dict[str, Any] | None = None,
        children: Sequence[NodeChild] | None = None,
        key: str | None = None,
    ):
        self.tag = tag
        self.props = props or {}
        self.children = children or []
        self.key = key

        # Process callbacks in props
        self._callback_keys: dict[str, str] = {}
        self._process_callbacks()

    def _process_callbacks(self) -> None:
        """Process props to detect and register callbacks."""
        for prop_name, prop_value in list(self.props.items()):
            # Check if the prop value is a callable (lambda/function)
            if callable(prop_value) and not isinstance(prop_value, type):
                # Generate unique callback key using UUID
                callback_key = str(uuid.uuid4())

                # Register the callback
                register_callback(callback_key, prop_value)

                # Store the callback key for this prop
                self._callback_keys[prop_name] = callback_key

                # Replace the callable with the callback key in props
                self.props[prop_name] = f"__callback:{callback_key}"

    def __getitem__(
        self,
        children_arg: Union[NodeChild, tuple[NodeChild, ...]],
    ):
        """Support indexing syntax: div()[children] or div()["text"]"""
        if self.children:
            raise ValueError(f"Node already has children: {self.children}")

        if isinstance(children_arg, (list, tuple)):
            new_children = list(children_arg)
        else:
            new_children = [children_arg]

        new_node = Node(
            tag=self.tag,
            props=self.props.copy(),
            children=new_children,
            key=self.key,
        )
        # Copy callback keys from the original node
        new_node._callback_keys = self._callback_keys.copy()
        return new_node

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        result = {
            "tag": self.tag,
            "props": self.props,
            "children": [
                child.to_dict() if isinstance(child, Node) else child
                for child in self.children
            ],
        }
        if self.key is not None:
            result["key"] = self.key
        return result

    def get_callback_info(self) -> dict[str, Any]:
        """Get callback information for this node and its children."""
        callback_info = {}

        # Add this node's callbacks if any - use callback keys directly since nodes don't have IDs anymore
        if self._callback_keys:
            # Use a temporary unique identifier for callback grouping
            node_key = str(uuid.uuid4())
            callback_info[node_key] = {"callbacks": self._callback_keys}

        # Recursively collect callback info from children
        for child in self.children:
            if isinstance(child, Node):
                child_callbacks = child.get_callback_info()
                callback_info.update(child_callbacks)

        return callback_info


# ============================================================================
# Tag Definition Functions
# ============================================================================


def define_tag(name: str, default_props: dict[str, Any] | None = None):
    """
    Define a standard HTML tag that creates UITreeNode instances.

    Args:
        name: The tag name (e.g., "div", "span")
        default_props: Default props to apply to all instances

    Returns:
        A function that creates UITreeNode instances
    """
    default_props = default_props or {}

    def create_element(*children: NodeChild, **props: Any) -> Node:
        """Create a UITreeNode for this tag."""
        merged_props = {**default_props, **props}
        return Node(
            tag=name, props=merged_props, children=list(children) if children else []
        )

    return create_element


def define_self_closing_tag(name: str, default_props: dict[str, Any] | None = None):
    """
    Define a self-closing HTML tag that creates UITreeNode instances.

    Args:
        name: The tag name (e.g., "br", "img")
        default_props: Default props to apply to all instances

    Returns:
        A function that creates UITreeNode instances (no children allowed)
    """
    default_props = default_props or {}

    def create_element(**props: Any) -> Node:
        """Create a self-closing UITreeNode for this tag."""
        merged_props = {**default_props, **props}
        return Node(
            tag=name,
            props=merged_props,
            children=[],  # Self-closing tags never have children
        )

    return create_element


# ============================================================================
# React Component Integration
# ============================================================================


COMPONENT_REGISTRY: "dict[str, ReactComponent]" = {}


class ReactComponent:
    """
    A React component that can be used within the UI tree.
    Returns a function that creates mount point UITreeNode instances.

    Args:
        component_key: Unique key for the component registry
        import_path: Path to import the component from
        export_name: Name of the export (use "default" for default exports)
        is_default_export: Whether this is a default export

    Returns:
        A function that creates UITreeNode instances with mount point tags
    """

    def __init__(
        self,
        component_key: str,
        import_path: str,
        export_name: str = "default",
        is_default_export: bool = True,
    ):
        if component_key in COMPONENT_REGISTRY:
            raise ValueError(f"Duplicate component key {component_key}")
        self.component_key = component_key
        self.import_path = import_path
        self.export_name = export_name
        self.is_default_export = is_default_export
        COMPONENT_REGISTRY[component_key] = self

    def __call__(self, *children: NodeChild, **props) -> Node:
        return Node(
            tag=f"$${self.component_key}",
            props=props,
            children=list(children) if children else [],
        )


def react_component_registry() -> dict[str, ReactComponent]:
    """Get all registered React components."""
    return COMPONENT_REGISTRY.copy()


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
