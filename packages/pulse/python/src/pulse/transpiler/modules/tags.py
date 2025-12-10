"""HTML tag function transpilation to JSX elements.

This module provides transpilation from pulse.html.tags (like div, span, etc.)
to JSX elements. Tag functions can be called with props and subscripted with children:

    # Python
    div(className="container")[span("Hello"), p("World")]

    # JavaScript
    <div className="container"><span>Hello</span><p>World</p></div>
"""

# pyright: reportUnannotatedClassAttribute=false

from __future__ import annotations

from typing import Any

from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.jsx import JSXCallExpr, build_jsx_props, convert_jsx_child
from pulse.transpiler.nodes import JSExpr, JSXFragment
from pulse.transpiler.py_module import PyModule


def _create_tag_function(tag_name: str):
	"""Create a tag function that returns JSXCallExpr when called."""

	@staticmethod
	def tag_func(*args: Any, **kwargs: Any) -> JSExpr:
		"""Tag function that creates JSXCallExpr with props and children."""
		props_list = build_jsx_props(kwargs)
		children_list = [convert_jsx_child(c) for c in args]
		return JSXCallExpr(tag_name, tuple(props_list), tuple(children_list))

	return tag_func


class PyTags(PyModule):
	"""Provides transpilation for pulse.html.tags to JSX elements."""

	# Regular tags - each is a function that returns JSXCallExpr when called
	a = _create_tag_function("a")
	abbr = _create_tag_function("abbr")
	address = _create_tag_function("address")
	article = _create_tag_function("article")
	aside = _create_tag_function("aside")
	audio = _create_tag_function("audio")
	b = _create_tag_function("b")
	bdi = _create_tag_function("bdi")
	bdo = _create_tag_function("bdo")
	blockquote = _create_tag_function("blockquote")
	body = _create_tag_function("body")
	button = _create_tag_function("button")
	canvas = _create_tag_function("canvas")
	caption = _create_tag_function("caption")
	cite = _create_tag_function("cite")
	code = _create_tag_function("code")
	colgroup = _create_tag_function("colgroup")
	data = _create_tag_function("data")
	datalist = _create_tag_function("datalist")
	dd = _create_tag_function("dd")
	del_ = _create_tag_function("del")
	details = _create_tag_function("details")
	dfn = _create_tag_function("dfn")
	dialog = _create_tag_function("dialog")
	div = _create_tag_function("div")
	dl = _create_tag_function("dl")
	dt = _create_tag_function("dt")
	em = _create_tag_function("em")
	fieldset = _create_tag_function("fieldset")
	figcaption = _create_tag_function("figcaption")
	figure = _create_tag_function("figure")
	footer = _create_tag_function("footer")
	form = _create_tag_function("form")
	h1 = _create_tag_function("h1")
	h2 = _create_tag_function("h2")
	h3 = _create_tag_function("h3")
	h4 = _create_tag_function("h4")
	h5 = _create_tag_function("h5")
	h6 = _create_tag_function("h6")
	head = _create_tag_function("head")
	header = _create_tag_function("header")
	hgroup = _create_tag_function("hgroup")
	html = _create_tag_function("html")
	i = _create_tag_function("i")
	iframe = _create_tag_function("iframe")
	ins = _create_tag_function("ins")
	kbd = _create_tag_function("kbd")
	label = _create_tag_function("label")
	legend = _create_tag_function("legend")
	li = _create_tag_function("li")
	main = _create_tag_function("main")
	map_ = _create_tag_function("map")
	mark = _create_tag_function("mark")
	menu = _create_tag_function("menu")
	meter = _create_tag_function("meter")
	nav = _create_tag_function("nav")
	noscript = _create_tag_function("noscript")
	object_ = _create_tag_function("object")
	ol = _create_tag_function("ol")
	optgroup = _create_tag_function("optgroup")
	option = _create_tag_function("option")
	output = _create_tag_function("output")
	p = _create_tag_function("p")
	picture = _create_tag_function("picture")
	pre = _create_tag_function("pre")
	progress = _create_tag_function("progress")
	q = _create_tag_function("q")
	rp = _create_tag_function("rp")
	rt = _create_tag_function("rt")
	ruby = _create_tag_function("ruby")
	s = _create_tag_function("s")
	samp = _create_tag_function("samp")
	script = _create_tag_function("script")
	section = _create_tag_function("section")
	select = _create_tag_function("select")
	small = _create_tag_function("small")
	span = _create_tag_function("span")
	strong = _create_tag_function("strong")
	style = _create_tag_function("style")
	sub = _create_tag_function("sub")
	summary = _create_tag_function("summary")
	sup = _create_tag_function("sup")
	table = _create_tag_function("table")
	tbody = _create_tag_function("tbody")
	td = _create_tag_function("td")
	template = _create_tag_function("template")
	textarea = _create_tag_function("textarea")
	tfoot = _create_tag_function("tfoot")
	th = _create_tag_function("th")
	thead = _create_tag_function("thead")
	time = _create_tag_function("time")
	title = _create_tag_function("title")
	tr = _create_tag_function("tr")
	u = _create_tag_function("u")
	ul = _create_tag_function("ul")
	var = _create_tag_function("var")
	video = _create_tag_function("video")

	# Self-closing tags
	area = _create_tag_function("area")
	base = _create_tag_function("base")
	br = _create_tag_function("br")
	col = _create_tag_function("col")
	embed = _create_tag_function("embed")
	hr = _create_tag_function("hr")
	img = _create_tag_function("img")
	input = _create_tag_function("input")
	link = _create_tag_function("link")
	meta = _create_tag_function("meta")
	param = _create_tag_function("param")
	source = _create_tag_function("source")
	track = _create_tag_function("track")
	wbr = _create_tag_function("wbr")

	# SVG tags
	svg = _create_tag_function("svg")
	circle = _create_tag_function("circle")
	ellipse = _create_tag_function("ellipse")
	g = _create_tag_function("g")
	line = _create_tag_function("line")
	path = _create_tag_function("path")
	polygon = _create_tag_function("polygon")
	polyline = _create_tag_function("polyline")
	rect = _create_tag_function("rect")
	text = _create_tag_function("text")
	tspan = _create_tag_function("tspan")
	defs = _create_tag_function("defs")
	clipPath = _create_tag_function("clipPath")
	mask = _create_tag_function("mask")
	pattern = _create_tag_function("pattern")
	use = _create_tag_function("use")

	# React fragment
	@staticmethod
	def fragment(*args: Any, **kwargs: Any) -> JSExpr:
		"""Fragment function that creates JSXFragment with children."""
		if kwargs:
			raise JSCompilationError("React fragments cannot have props")
		children_list = [convert_jsx_child(c) for c in args]
		return JSXFragment(children_list)
