from typing import (
    Mapping,
    NamedTuple,
    Self,
    overload,
    Union,
)

__all__ = [
    # Core types and functions
    "HTMLElement",
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


class HTMLElement(NamedTuple):
    """
    A lightweight representation of an HTML node:
      - tag: the element's tag name (e.g. "div", "span", "html")
      - attributes: mapping of attribute name to its value
      - children: other HTMLElements or string content
      - render: the function responsible for converting the node to HTML
    """

    tag: str
    attributes: Mapping[str, str]
    children: tuple[Self | str, ...]
    whitespace_sensitive: bool = False
    self_closing: bool = False

    def __getitem__(self, children: Self | str | tuple[Self | str, ...]):
        if self.self_closing:
            raise ValueError("Self-closing tags cannot have children")
        if len(self.children) > 0:
            raise ValueError(f"Multiple calls with children for <{self.tag}>")

        # Handle single child or tuple of children
        if isinstance(children, (tuple, list)) and not isinstance(
            children, HTMLElement
        ):
            child_tuple = tuple(children)
        else:
            child_tuple = (children,)

        return HTMLElement(
            self.tag,
            self.attributes,
            child_tuple,
            self.whitespace_sensitive,
            self.self_closing,
        )

    def __eq__(self, other):
        if not isinstance(other, HTMLElement):
            return False
        return (
            self.tag == other.tag
            and self.attributes == other.attributes
            and self.children == other.children
            and self.whitespace_sensitive == other.whitespace_sensitive
            and self.self_closing == other.self_closing
        )

    def __repr__(self):
        return f"HTMLElement(tag={self.tag!r}, attributes={dict(self.attributes)!r}, children={self.children!r}, whitespace_sensitive={self.whitespace_sensitive}, self_closing={self.self_closing})"


class HTMLElementEmpty(HTMLElement):
    """HTMLElement without children - supports indexing and calling with children"""

    def __getitem__(
        self, children: HTMLElement | str | tuple[HTMLElement | str, ...]
    ) -> HTMLElement:
        if self.self_closing:
            raise ValueError("Self-closing tags cannot have children")
        if len(self.children) > 0:
            raise ValueError("Misconstructed HTMLEmptyElement contains children:", self)

        # Handle single child or tuple of children
        if isinstance(children, (tuple, list)) and not isinstance(
            children, HTMLElement
        ):
            child_tuple = tuple(children)
        else:
            child_tuple = (children,)

        return HTMLElement(
            self.tag,
            self.attributes,
            child_tuple,
            self.whitespace_sensitive,
            self.self_closing,
        )


def define_tag(
    name: str,
    default_attrs: dict[str, str] | None = None,
    whitespace_sensitive: bool = False,
):
    """
    Defines a standard tag (non-self-closing) with optional default attributes.
    If whitespace_sensitive=True, uses render_whitespace_sensitive_element;
    otherwise uses render_element.

    The returned function can be called in these ways:
    1. tag() -> HTMLElementEmpty (can use indexing syntax)
    2. tag(**attrs) -> HTMLElementEmpty (can use indexing syntax)
    3. tag(*children) -> HTMLElementWithChildren (indexing not allowed)
    4. tag(**attrs)[children] -> HTMLElementWithChildren (indexing not allowed)
    """

    default_attrs = default_attrs or {}

    @overload
    def create_element() -> HTMLElementEmpty: ...

    @overload
    def create_element(**attrs: str) -> HTMLElementEmpty: ...

    @overload
    def create_element(*children: HTMLElement | str, **attrs) -> HTMLElement: ...

    def create_element(
        *children: HTMLElement | str, **attrs: str
    ) -> Union[HTMLElementEmpty, HTMLElement]:
        if children:
            return HTMLElement(
                tag=name,
                attributes=default_attrs | attrs,
                children=children,
                whitespace_sensitive=whitespace_sensitive,
            )
        else:
            return HTMLElementEmpty(
                tag=name,
                children=(),
                attributes=default_attrs | attrs,
                whitespace_sensitive=whitespace_sensitive,
            )

    return create_element


def define_self_closing_tag(name: str, default_attrs: dict[str, str] | None = None):
    """
    Defines a self-closing tag (e.g. <br />, <img />, <meta />, etc.)
    Self-closing tags cannot have children and do not support indexing.
    """
    default_attrs = default_attrs or {}

    # Self-closing tags cannot have children
    def create_element(**attrs: str) -> HTMLElement:
        return HTMLElement(
            tag=name,
            attributes=default_attrs | attrs,
            children=(),
            self_closing=True,
            whitespace_sensitive=False,
        )

    return create_element


def render(
    elt: HTMLElement,
    indent: int = 2,
    level: int = 0,
) -> str:
    """Render the element with optional indentation."""
    lines: list[str] = []
    _render_into(elt, lines, " " * indent, level)
    separator = "\n" if indent > 0 else ""
    return separator.join(lines)


def _render_into(elt: HTMLElement, lines: list[str], indent: str = " ", level: int = 0):
    offset = indent * level

    # Add doctype for html tag
    if elt.tag == "html":
        lines.append(offset + "<!DOCTYPE html>")

    open_tag = _build_open_tag(elt)

    # Handle self-closing tags
    if elt.self_closing:
        lines.append(offset + open_tag)
        return

    closing_tag = f"</{elt.tag}>"
    # If no children, render everything onto a single line
    if len(elt.children) == 0:
        lines.append(offset + open_tag + closing_tag)
        return

    # For whitespace-sensitive tags, render everything onto a single "line"
    # (may contain newline symbols, but won't get indented etc...)
    if elt.whitespace_sensitive:
        content = _render_children_inline(elt)
        lines.append(offset + open_tag + content + closing_tag)
    # Regular case: render with indentation
    else:
        # Handle multiline cases
        lines.append(offset + open_tag)
        _render_children_into(elt, lines, indent, level + 1)
        lines.append(offset + closing_tag)


def _build_open_tag(elt: HTMLElement) -> str:
    """Build the opening tag with attributes."""
    tag = f"<{elt.tag}"
    for key, val in elt.attributes.items():
        key = attrs_map.get(key, key)
        key = key.replace("_", "-")
        tag += f' {key}="{_escape(val)}"'
    tag += " />" if elt.self_closing else ">"
    return tag


def _render_children_inline(elt: HTMLElement) -> str:
    """Render children without newlines for whitespace sensitive elements."""
    parts = []
    for child in elt.children:
        if isinstance(child, str):
            parts.append(_escape(child))
        else:
            _render_into(child, parts, "", 0)
    return "".join(parts)


def _render_children_into(elt: HTMLElement, lines: list[str], indent: str, level: int):
    """Render children with proper indentation."""
    for child in elt.children:
        if isinstance(child, str):
            lines.append((indent * level) + _escape(child))
        else:
            _render_into(child, lines, indent, level)


# If you want to map special attribute names (like 'classname' -> 'class')
attrs_map = {"classname": "class", "class_": "class"}


# A small utility for escaping special HTML characters.
# If you need to allow "safe" content, you can skip escaping for those strings.
def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


# Example usage: define an <html> tag that automatically prepends a <!DOCTYPE html>.
# (As in the old library, this is a normal tag, not self-closing.)
html = define_tag("html")

# Standard HTML tags
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
code = define_tag("code", whitespace_sensitive=True)
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
form = define_tag("form", default_attrs={"method": "POST"})
h1 = define_tag("h1")
h2 = define_tag("h2")
h3 = define_tag("h3")
h4 = define_tag("h4")
h5 = define_tag("h5")
h6 = define_tag("h6")
head = define_tag("head")
header = define_tag("header")
hgroup = define_tag("hgroup")
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
pre = define_tag("pre", whitespace_sensitive=True)
progress = define_tag("progress")
q = define_tag("q")
rp = define_tag("rp")
rt = define_tag("rt")
ruby = define_tag("ruby")
s = define_tag("s")
samp = define_tag("samp")
script = define_tag("script", default_attrs={"type": "text/javascript"})
section = define_tag("section")
select = define_tag("select")
small = define_tag("small")
span = define_tag("span")
strong = define_tag("strong")
style = define_tag("style", default_attrs={"type": "text/css"})
sub = define_tag("sub")
summary = define_tag("summary")
sup = define_tag("sup")
table = define_tag("table")
tbody = define_tag("tbody")
td = define_tag("td")
template = define_tag("template")
textarea = define_tag("textarea", whitespace_sensitive=True)
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


if __name__ == "__main__":
    print(render(div()))
    # code_block = pre(
    #     code("""def hello():
    # print("Hello, world!")
    # return 42""")
    # )
    # expected = (
    #     "<pre><code>def hello():\n"
    #     '    print(&quot;Hello, world!&quot;)\n'
    #     "    return 42</code></pre>"
    # )
    # print(code_block.render())
    # assert code_block.render(indent=2) == expected
