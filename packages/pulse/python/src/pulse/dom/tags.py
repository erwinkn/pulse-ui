from typing import Any, ParamSpec

from pulse.vdom import Element, Node

P = ParamSpec("P")


def define_tag(name: str, default_props: dict[str, Any] | None = None):
	"""
	Define a standard HTML tag that creates UITreeNode instances.

	Args:
	    name: The tag name (e.g., "div", "span")
	    default_props: Default props to apply to all instances

	Returns:
	    A function that creates UITreeNode instances
	"""

	def create_element(*children: Element, **props: Any) -> Node:
		"""Create a UITreeNode for this tag."""
		if default_props:
			props = default_props | props
		key = props.pop("key", None)
		return Node(tag=name, key=key, props=props, children=children)

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
	default_props = default_props

	def create_element(**props: Any) -> Node:
		"""Create a self-closing UITreeNode for this tag."""
		if default_props:
			props = default_props | props
		key = props.pop("key", None)
		return Node(
			tag=name,
			key=key,
			props=props,
			children=(),  # Self-closing tags never have children
			allow_children=False,
		)

	return create_element


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

# React fragment
fragment = define_tag("$$fragment")


# SVG tags
svg = define_tag("svg")
circle = define_tag("circle")
ellipse = define_tag("ellipse")
g = define_tag("g")
line = define_tag("line")
path = define_tag("path")
polygon = define_tag("polygon")
polyline = define_tag("polyline")
rect = define_tag("rect")
text = define_tag("text")
tspan = define_tag("tspan")
defs = define_tag("defs")
clipPath = define_tag("clipPath")
mask = define_tag("mask")
pattern = define_tag("pattern")
use = define_tag("use")

# Lists of tag names/default props (referenced by JS transpiler builtins)
TAGS = [
	("a", None),
	("abbr", None),
	("address", None),
	("article", None),
	("aside", None),
	("audio", None),
	("b", None),
	("bdi", None),
	("bdo", None),
	("blockquote", None),
	("body", None),
	("button", None),
	("canvas", None),
	("caption", None),
	("cite", None),
	("code", None),
	("colgroup", None),
	("data", None),
	("datalist", None),
	("dd", None),
	("del", None),
	("details", None),
	("dfn", None),
	("dialog", None),
	("div", None),
	("dl", None),
	("dt", None),
	("em", None),
	("fieldset", None),
	("figcaption", None),
	("figure", None),
	("footer", None),
	("form", {"method": "POST"}),
	("h1", None),
	("h2", None),
	("h3", None),
	("h4", None),
	("h5", None),
	("h6", None),
	("head", None),
	("header", None),
	("hgroup", None),
	("html", None),
	("i", None),
	("iframe", None),
	("ins", None),
	("kbd", None),
	("label", None),
	("legend", None),
	("li", None),
	("main", None),
	("map", None),
	("mark", None),
	("menu", None),
	("meter", None),
	("nav", None),
	("noscript", None),
	("object", None),
	("ol", None),
	("optgroup", None),
	("option", None),
	("output", None),
	("p", None),
	("picture", None),
	("pre", None),
	("progress", None),
	("q", None),
	("rp", None),
	("rt", None),
	("ruby", None),
	("s", None),
	("samp", None),
	("script", {"type": "text/javascript"}),
	("section", None),
	("select", None),
	("small", None),
	("span", None),
	("strong", None),
	("style", {"type": "text/css"}),
	("sub", None),
	("summary", None),
	("sup", None),
	("table", None),
	("tbody", None),
	("td", None),
	("template", None),
	("textarea", None),
	("tfoot", None),
	("th", None),
	("thead", None),
	("time", None),
	("title", None),
	("tr", None),
	("u", None),
	("ul", None),
	("var", None),
	("video", None),
	# SVG tags
	("svg", None),
	("circle", None),
	("ellipse", None),
	("g", None),
	("line", None),
	("path", None),
	("polygon", None),
	("polyline", None),
	("rect", None),
	("text", None),
	("tspan", None),
	("defs", None),
	("clipPath", None),
	("mask", None),
	("pattern", None),
	("use", None),
]

SELF_CLOSING_TAGS = [
	("area", None),
	("base", None),
	("br", None),
	("col", None),
	("embed", None),
	("hr", None),
	("img", None),
	("input", None),
	("link", None),
	("meta", None),
	("param", None),
	("source", None),
	("track", None),
	("wbr", None),
]
