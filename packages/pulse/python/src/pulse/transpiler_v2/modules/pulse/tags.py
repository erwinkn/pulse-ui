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
from typing import final, override

from pulse.transpiler_v2.errors import TranspileError
from pulse.transpiler_v2.nodes import (
	Child,
	Element,
	Expr,
	Literal,
	Prop,
)
from pulse.transpiler_v2.py_module import PyModule
from pulse.transpiler_v2.transpiler import Transpiler


@dataclass(slots=True, frozen=True)
class TagExpr(Expr):
	"""Expr that creates JSX elements when called.

	Represents a tag function like `div`, `span`, etc.
	When called, produces an Element with props from kwargs and children from args.
	"""

	tag: str

	@override
	def emit(self, out: list[str]) -> None:
		raise TypeError(f"Tag '{self.tag}' cannot be emitted directly - must be called")

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		kwargs: dict[str, ast.expr],
		ctx: Transpiler,
	) -> Expr:
		"""Handle tag calls: positional args are children, kwargs are props."""
		# Build children from positional args
		children: list[Child] = []
		for a in args:
			children.append(ctx.emit_expr(a))

		# Build props from kwargs
		props: dict[str, Prop] = {}
		key: str | None = None
		for k, v in kwargs.items():
			prop_value = ctx.emit_expr(v)
			if k == "key":
				# Extract key prop
				if isinstance(prop_value, Literal) and isinstance(
					prop_value.value, str
				):
					key = prop_value.value
				else:
					raise TranspileError("key prop must be a string literal")
			else:
				props[k] = prop_value

		# Handle fragment specially
		tag = "" if self.tag == "$$fragment" else self.tag

		return Element(
			tag=tag,
			props=props if props else None,
			children=children if children else None,
			key=key,
		)

	# -------------------------------------------------------------------------
	# Python dunder methods: allow natural syntax in @javascript functions
	# -------------------------------------------------------------------------

	@override
	def __call__(self, *args: object, **kwargs: object) -> Element:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Allow calling TagExpr objects in Python code.

		Returns a placeholder Element for type checking. The actual transpilation
		happens via transpile_call when the transpiler processes the AST.
		"""
		tag = "" if self.tag == "$$fragment" else self.tag
		return Element(tag=tag, props=None, children=None, key=None)


def _create_tag(tag_name: str) -> TagExpr:
	"""Create a TagExpr for an HTML tag."""
	return TagExpr(tag_name)


@final
class PulseTags(PyModule):
	"""Provides transpilation for pulse.dom.tags to JSX elements."""

	# Regular tags
	a = _create_tag("a")
	abbr = _create_tag("abbr")
	address = _create_tag("address")
	article = _create_tag("article")
	aside = _create_tag("aside")
	audio = _create_tag("audio")
	b = _create_tag("b")
	bdi = _create_tag("bdi")
	bdo = _create_tag("bdo")
	blockquote = _create_tag("blockquote")
	body = _create_tag("body")
	button = _create_tag("button")
	canvas = _create_tag("canvas")
	caption = _create_tag("caption")
	cite = _create_tag("cite")
	code = _create_tag("code")
	colgroup = _create_tag("colgroup")
	data = _create_tag("data")
	datalist = _create_tag("datalist")
	dd = _create_tag("dd")
	del_ = _create_tag("del")
	details = _create_tag("details")
	dfn = _create_tag("dfn")
	dialog = _create_tag("dialog")
	div = _create_tag("div")
	dl = _create_tag("dl")
	dt = _create_tag("dt")
	em = _create_tag("em")
	fieldset = _create_tag("fieldset")
	figcaption = _create_tag("figcaption")
	figure = _create_tag("figure")
	footer = _create_tag("footer")
	form = _create_tag("form")
	h1 = _create_tag("h1")
	h2 = _create_tag("h2")
	h3 = _create_tag("h3")
	h4 = _create_tag("h4")
	h5 = _create_tag("h5")
	h6 = _create_tag("h6")
	head = _create_tag("head")
	header = _create_tag("header")
	hgroup = _create_tag("hgroup")
	html = _create_tag("html")
	i = _create_tag("i")
	iframe = _create_tag("iframe")
	ins = _create_tag("ins")
	kbd = _create_tag("kbd")
	label = _create_tag("label")
	legend = _create_tag("legend")
	li = _create_tag("li")
	main = _create_tag("main")
	map_ = _create_tag("map")
	mark = _create_tag("mark")
	menu = _create_tag("menu")
	meter = _create_tag("meter")
	nav = _create_tag("nav")
	noscript = _create_tag("noscript")
	object_ = _create_tag("object")
	ol = _create_tag("ol")
	optgroup = _create_tag("optgroup")
	option = _create_tag("option")
	output = _create_tag("output")
	p = _create_tag("p")
	picture = _create_tag("picture")
	pre = _create_tag("pre")
	progress = _create_tag("progress")
	q = _create_tag("q")
	rp = _create_tag("rp")
	rt = _create_tag("rt")
	ruby = _create_tag("ruby")
	s = _create_tag("s")
	samp = _create_tag("samp")
	script = _create_tag("script")
	section = _create_tag("section")
	select = _create_tag("select")
	small = _create_tag("small")
	span = _create_tag("span")
	strong = _create_tag("strong")
	style = _create_tag("style")
	sub = _create_tag("sub")
	summary = _create_tag("summary")
	sup = _create_tag("sup")
	table = _create_tag("table")
	tbody = _create_tag("tbody")
	td = _create_tag("td")
	template = _create_tag("template")
	textarea = _create_tag("textarea")
	tfoot = _create_tag("tfoot")
	th = _create_tag("th")
	thead = _create_tag("thead")
	time = _create_tag("time")
	title = _create_tag("title")
	tr = _create_tag("tr")
	u = _create_tag("u")
	ul = _create_tag("ul")
	var = _create_tag("var")
	video = _create_tag("video")

	# Self-closing tags
	area = _create_tag("area")
	base = _create_tag("base")
	br = _create_tag("br")
	col = _create_tag("col")
	embed = _create_tag("embed")
	hr = _create_tag("hr")
	img = _create_tag("img")
	input = _create_tag("input")
	link = _create_tag("link")
	meta = _create_tag("meta")
	param = _create_tag("param")
	source = _create_tag("source")
	track = _create_tag("track")
	wbr = _create_tag("wbr")

	# SVG tags
	svg = _create_tag("svg")
	circle = _create_tag("circle")
	ellipse = _create_tag("ellipse")
	g = _create_tag("g")
	line = _create_tag("line")
	path = _create_tag("path")
	polygon = _create_tag("polygon")
	polyline = _create_tag("polyline")
	rect = _create_tag("rect")
	text = _create_tag("text")
	tspan = _create_tag("tspan")
	defs = _create_tag("defs")
	clipPath = _create_tag("clipPath")
	mask = _create_tag("mask")
	pattern = _create_tag("pattern")
	use = _create_tag("use")

	# React fragment
	fragment = _create_tag("$$fragment")
