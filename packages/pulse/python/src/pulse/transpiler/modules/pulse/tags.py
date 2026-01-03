"""HTML tag function transpilation to JSX elements.

This module provides transpilation from pulse.dom.tags (like div, span, etc.)
to JSX elements. Tag functions can be called with props and children:

    # Python
    div("Hello", className="container")

    # JavaScript
    <div className="container">Hello</div>
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, final, override

from pulse.components.for_ import _emit_for
from pulse.transpiler.nodes import Element, Expr, Literal, Node, Prop
from pulse.transpiler.py_module import PyModule
from pulse.transpiler.transpiler import Transpiler
from pulse.transpiler.vdom import VDOMNode


@dataclass(slots=True, frozen=True)
class TagExpr(Expr):
	"""Expr that creates JSX elements when called.

	Represents a tag function like `div`, `span`, etc.
	When called, produces an Element with props from kwargs and children from args.
	"""

	tag: str

	@override
	def emit(self, out: list[str]) -> None:
		out.append(f'"{self.tag}"')

	@override
	def render(self) -> VDOMNode:
		return self.tag

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		kwargs: dict[str, ast.expr],
		ctx: Transpiler,
	) -> Expr:
		"""Handle tag calls: positional args are children, kwargs are props."""
		# Build children from positional args
		children: list[Node] = []
		for a in args:
			children.append(ctx.emit_expr(a))

		# Build props from kwargs
		props: dict[str, Prop] = {}
		key: str | Expr | None = None
		for k, v in kwargs.items():
			prop_value = ctx.emit_expr(v)
			if k == "key":
				# Accept any expression as key for transpilation
				if isinstance(prop_value, Literal) and isinstance(
					prop_value.value, str
				):
					key = prop_value.value  # Optimize string literals
				else:
					key = prop_value  # Keep as expression
			else:
				props[k] = prop_value

		return Element(
			tag=self.tag,
			props=props if props else None,
			children=children if children else None,
			key=key,
		)

	# -------------------------------------------------------------------------
	# Python dunder methods: allow natural syntax in @javascript functions
	# -------------------------------------------------------------------------

	@override
	def __call__(self, *args: Any, **kwargs: Any):  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Allow calling TagExpr objects in Python code.

		Returns a placeholder Element for type checking. The actual transpilation
		happens via transpile_call when the transpiler processes the AST.
		"""
		return Element(tag=self.tag, props=None, children=None, key=None)


@final
class PulseTags(PyModule):
	"""Provides transpilation for pulse.dom.tags to JSX elements."""

	# Regular tags
	a = TagExpr("a")
	abbr = TagExpr("abbr")
	address = TagExpr("address")
	article = TagExpr("article")
	aside = TagExpr("aside")
	audio = TagExpr("audio")
	b = TagExpr("b")
	bdi = TagExpr("bdi")
	bdo = TagExpr("bdo")
	blockquote = TagExpr("blockquote")
	body = TagExpr("body")
	button = TagExpr("button")
	canvas = TagExpr("canvas")
	caption = TagExpr("caption")
	cite = TagExpr("cite")
	code = TagExpr("code")
	colgroup = TagExpr("colgroup")
	data = TagExpr("data")
	datalist = TagExpr("datalist")
	dd = TagExpr("dd")
	del_ = TagExpr("del")
	details = TagExpr("details")
	dfn = TagExpr("dfn")
	dialog = TagExpr("dialog")
	div = TagExpr("div")
	dl = TagExpr("dl")
	dt = TagExpr("dt")
	em = TagExpr("em")
	fieldset = TagExpr("fieldset")
	figcaption = TagExpr("figcaption")
	figure = TagExpr("figure")
	footer = TagExpr("footer")
	form = TagExpr("form")
	h1 = TagExpr("h1")
	h2 = TagExpr("h2")
	h3 = TagExpr("h3")
	h4 = TagExpr("h4")
	h5 = TagExpr("h5")
	h6 = TagExpr("h6")
	head = TagExpr("head")
	header = TagExpr("header")
	hgroup = TagExpr("hgroup")
	html = TagExpr("html")
	i = TagExpr("i")
	iframe = TagExpr("iframe")
	ins = TagExpr("ins")
	kbd = TagExpr("kbd")
	label = TagExpr("label")
	legend = TagExpr("legend")
	li = TagExpr("li")
	main = TagExpr("main")
	map_ = TagExpr("map")
	mark = TagExpr("mark")
	menu = TagExpr("menu")
	meter = TagExpr("meter")
	nav = TagExpr("nav")
	noscript = TagExpr("noscript")
	object_ = TagExpr("object")
	ol = TagExpr("ol")
	optgroup = TagExpr("optgroup")
	option = TagExpr("option")
	output = TagExpr("output")
	p = TagExpr("p")
	picture = TagExpr("picture")
	pre = TagExpr("pre")
	progress = TagExpr("progress")
	q = TagExpr("q")
	rp = TagExpr("rp")
	rt = TagExpr("rt")
	ruby = TagExpr("ruby")
	s = TagExpr("s")
	samp = TagExpr("samp")
	script = TagExpr("script")
	section = TagExpr("section")
	select = TagExpr("select")
	small = TagExpr("small")
	span = TagExpr("span")
	strong = TagExpr("strong")
	style = TagExpr("style")
	sub = TagExpr("sub")
	summary = TagExpr("summary")
	sup = TagExpr("sup")
	table = TagExpr("table")
	tbody = TagExpr("tbody")
	td = TagExpr("td")
	template = TagExpr("template")
	textarea = TagExpr("textarea")
	tfoot = TagExpr("tfoot")
	th = TagExpr("th")
	thead = TagExpr("thead")
	time = TagExpr("time")
	title = TagExpr("title")
	tr = TagExpr("tr")
	u = TagExpr("u")
	ul = TagExpr("ul")
	var = TagExpr("var")
	video = TagExpr("video")

	# Self-closing tags
	area = TagExpr("area")
	base = TagExpr("base")
	br = TagExpr("br")
	col = TagExpr("col")
	embed = TagExpr("embed")
	hr = TagExpr("hr")
	img = TagExpr("img")
	input = TagExpr("input")
	link = TagExpr("link")
	meta = TagExpr("meta")
	param = TagExpr("param")
	source = TagExpr("source")
	track = TagExpr("track")
	wbr = TagExpr("wbr")

	# SVG tags
	svg = TagExpr("svg")
	circle = TagExpr("circle")
	ellipse = TagExpr("ellipse")
	g = TagExpr("g")
	line = TagExpr("line")
	path = TagExpr("path")
	polygon = TagExpr("polygon")
	polyline = TagExpr("polyline")
	rect = TagExpr("rect")
	text = TagExpr("text")
	tspan = TagExpr("tspan")
	defs = TagExpr("defs")
	clipPath = TagExpr("clipPath")
	mask = TagExpr("mask")
	pattern = TagExpr("pattern")
	use = TagExpr("use")

	# React fragment
	fragment = TagExpr("")

	# For component - maps to array.map()
	For = _emit_for
