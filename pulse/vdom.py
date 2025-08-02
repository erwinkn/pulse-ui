"""
HTML library that generates UI tree nodes directly.

This library provides a Python API for building UI trees that match
the TypeScript UINode format exactly, eliminating the need for translation.
"""

from typing import (
    Any,
    Literal,
    NotRequired,
    Optional,
    Callable,
    Sequence,
    TypedDict,
    Union,
    cast,
)

__all__ = [
    # Core types and functions
    "Node",
    "define_tag",
    "define_self_closing_tag",
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
# Core VDOM
# ============================================================================

PrimitiveNode = Union[str, int, float]
NodeChild = Union["Node", PrimitiveNode]
Callbacks = dict[str, Callable]


class VDOMNode(TypedDict):
    tag: str
    key: NotRequired[str]
    props: NotRequired[dict[str, Any]]  # does not include callbacks
    children: "NotRequired[Sequence[VDOMNode | PrimitiveNode] | None]"


class Node:
    """
    A UI tree node that matches the TypeScript UIElementNode format.
    This directly generates the structure expected by the React frontend.
    """

    def __init__(
        self,
        tag: str,
        props: Optional[dict[str, Any] | None] = None,
        children: Optional[Sequence["NodeChild"]] = None,
        key: Optional[str] = None,
        callbacks: Optional[dict[str, Callable]] = None,
    ):
        self.tag = tag
        self.props = props
        self.children = children
        self.key = key
        self.callbacks = callbacks

    def __getitem__(
        self,
        children_arg: Union[NodeChild, tuple[NodeChild, ...]],
    ):
        """Support indexing syntax: div()[children] or div()["text"]"""
        if self.children:
            raise ValueError(f"Node already has children: {self.children}")

        if isinstance(children_arg, tuple):
            new_children = cast(list[NodeChild], list(children_arg))
        else:
            new_children = [children_arg]

        return Node(
            tag=self.tag,
            props=self.props,
            callbacks=self.callbacks,
            children=new_children,
            key=self.key,
        )

    def _render_node(self, path: str, callbacks: dict[str, Callable]) -> VDOMNode:
        """Convert to dictionary format for JSON serialization."""
        path_prefix = (path + ".") if path else ""

        vdom: VDOMNode = {
            "tag": self.tag,
        }
        if self.key:
            vdom["key"] = self.key
        if self.props:
            vdom["props"] = self.props
        if self.children:
            vdom["children"] = [
                child._render_node(f"{path_prefix}{i}", callbacks)
                if isinstance(child, Node)
                else child
                for i, child in enumerate(self.children or [])
            ]
        if self.callbacks:
            if "props" not in vdom:
                vdom["props"] = {}
            for callback_name, callback_fn in self.callbacks.items():
                callback_key = f"{path_prefix}{callback_name}"
                # Props are guaranteed to exist here
                vdom["props"][callback_name] = f"$$callback:{callback_key}"
                callbacks[callback_key] = callback_fn

        return vdom

    def list_callbacks(self, path=""):
        if not self.callbacks:
            return {}
        path_prefix = (path + ".") if path else ""
        return {path_prefix + key: callback for key, callback in self.callbacks.items()}

    def render(self, path="") -> tuple[VDOMNode, Callbacks]:
        callbacks: dict[str, Callable] = {}
        tree = self._render_node(path, callbacks)
        return tree, callbacks


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
        props = {**default_props, **props}
        props, callbacks = extract_callbacks_from_props(props)
        return Node(tag=name, props=props, callbacks=callbacks, children=children)

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
        props = {**default_props, **props}
        props, callbacks = extract_callbacks_from_props(props)

        return Node(
            tag=name,
            props=props,
            callbacks=callbacks,
            children=(),  # Self-closing tags never have children
        )

    return create_element


def extract_callbacks_from_props(
    props: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Callable]]:
    clean_props = {}
    callbacks = {}
    for k, v in props.items():
        if callable(v):
            callbacks[k] = v
        else:
            clean_props[k] = v
    return clean_props, callbacks


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
