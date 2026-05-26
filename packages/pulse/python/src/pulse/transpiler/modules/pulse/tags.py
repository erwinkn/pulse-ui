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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from pulse.components.for_ import emit_for
from pulse.transpiler.nodes import (
	Element,
	Expr,
	Literal,
	Node,
	Prop,
	Spread,
	spread_dict,
)
from pulse.transpiler.py_module import PyModule
from pulse.transpiler.transpiler import Transpiler


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
	def render(self):
		return self.tag

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		"""Handle tag calls: positional args are children, kwargs are props.

		Spread (**expr) is supported for prop spreading.
		"""
		# Build children from positional args
		children: list[Node] = []
		for a in args:
			children.append(ctx.emit_expr(a))

		# Build props from kwargs
		props: list[tuple[str, Prop] | Spread] = []
		key: str | Expr | None = None
		for kw in keywords:
			if kw.arg is None:
				# **spread syntax
				props.append(spread_dict(ctx.emit_expr(kw.value)))
			else:
				k = kw.arg
				prop_value = ctx.emit_expr(kw.value)
				if k == "key":
					# Accept any expression as key for transpilation
					if isinstance(prop_value, Literal) and isinstance(
						prop_value.value, str
					):
						key = prop_value.value  # Optimize string literals
					else:
						key = prop_value  # Keep as expression
				else:
					props.append((k, prop_value))

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


class PulseTags(PyModule):
	"""Provides transpilation for pulse.dom.tags to JSX elements."""

	# Regular tags
	a: TagExpr = TagExpr("a")
	abbr: TagExpr = TagExpr("abbr")
	address: TagExpr = TagExpr("address")
	article: TagExpr = TagExpr("article")
	aside: TagExpr = TagExpr("aside")
	audio: TagExpr = TagExpr("audio")
	b: TagExpr = TagExpr("b")
	bdi: TagExpr = TagExpr("bdi")
	bdo: TagExpr = TagExpr("bdo")
	blockquote: TagExpr = TagExpr("blockquote")
	body: TagExpr = TagExpr("body")
	button: TagExpr = TagExpr("button")
	canvas: TagExpr = TagExpr("canvas")
	caption: TagExpr = TagExpr("caption")
	cite: TagExpr = TagExpr("cite")
	code: TagExpr = TagExpr("code")
	colgroup: TagExpr = TagExpr("colgroup")
	data: TagExpr = TagExpr("data")
	datalist: TagExpr = TagExpr("datalist")
	dd: TagExpr = TagExpr("dd")
	del_: TagExpr = TagExpr("del")
	details: TagExpr = TagExpr("details")
	dfn: TagExpr = TagExpr("dfn")
	dialog: TagExpr = TagExpr("dialog")
	div: TagExpr = TagExpr("div")
	dl: TagExpr = TagExpr("dl")
	dt: TagExpr = TagExpr("dt")
	em: TagExpr = TagExpr("em")
	fieldset: TagExpr = TagExpr("fieldset")
	figcaption: TagExpr = TagExpr("figcaption")
	figure: TagExpr = TagExpr("figure")
	footer: TagExpr = TagExpr("footer")
	form: TagExpr = TagExpr("form")
	h1: TagExpr = TagExpr("h1")
	h2: TagExpr = TagExpr("h2")
	h3: TagExpr = TagExpr("h3")
	h4: TagExpr = TagExpr("h4")
	h5: TagExpr = TagExpr("h5")
	h6: TagExpr = TagExpr("h6")
	head: TagExpr = TagExpr("head")
	header: TagExpr = TagExpr("header")
	hgroup: TagExpr = TagExpr("hgroup")
	html: TagExpr = TagExpr("html")
	i: TagExpr = TagExpr("i")
	iframe: TagExpr = TagExpr("iframe")
	ins: TagExpr = TagExpr("ins")
	kbd: TagExpr = TagExpr("kbd")
	label: TagExpr = TagExpr("label")
	legend: TagExpr = TagExpr("legend")
	li: TagExpr = TagExpr("li")
	main: TagExpr = TagExpr("main")
	map_: TagExpr = TagExpr("map")
	mark: TagExpr = TagExpr("mark")
	menu: TagExpr = TagExpr("menu")
	meter: TagExpr = TagExpr("meter")
	nav: TagExpr = TagExpr("nav")
	noscript: TagExpr = TagExpr("noscript")
	object_: TagExpr = TagExpr("object")
	ol: TagExpr = TagExpr("ol")
	optgroup: TagExpr = TagExpr("optgroup")
	option: TagExpr = TagExpr("option")
	output: TagExpr = TagExpr("output")
	p: TagExpr = TagExpr("p")
	picture: TagExpr = TagExpr("picture")
	pre: TagExpr = TagExpr("pre")
	progress: TagExpr = TagExpr("progress")
	q: TagExpr = TagExpr("q")
	rp: TagExpr = TagExpr("rp")
	rt: TagExpr = TagExpr("rt")
	ruby: TagExpr = TagExpr("ruby")
	s: TagExpr = TagExpr("s")
	samp: TagExpr = TagExpr("samp")
	script: TagExpr = TagExpr("script")
	section: TagExpr = TagExpr("section")
	select: TagExpr = TagExpr("select")
	small: TagExpr = TagExpr("small")
	span: TagExpr = TagExpr("span")
	strong: TagExpr = TagExpr("strong")
	style: TagExpr = TagExpr("style")
	sub: TagExpr = TagExpr("sub")
	summary: TagExpr = TagExpr("summary")
	sup: TagExpr = TagExpr("sup")
	table: TagExpr = TagExpr("table")
	tbody: TagExpr = TagExpr("tbody")
	td: TagExpr = TagExpr("td")
	template: TagExpr = TagExpr("template")
	textarea: TagExpr = TagExpr("textarea")
	tfoot: TagExpr = TagExpr("tfoot")
	th: TagExpr = TagExpr("th")
	thead: TagExpr = TagExpr("thead")
	time: TagExpr = TagExpr("time")
	title: TagExpr = TagExpr("title")
	tr: TagExpr = TagExpr("tr")
	u: TagExpr = TagExpr("u")
	ul: TagExpr = TagExpr("ul")
	var: TagExpr = TagExpr("var")
	video: TagExpr = TagExpr("video")

	# Self-closing tags
	area: TagExpr = TagExpr("area")
	base: TagExpr = TagExpr("base")
	br: TagExpr = TagExpr("br")
	col: TagExpr = TagExpr("col")
	embed: TagExpr = TagExpr("embed")
	hr: TagExpr = TagExpr("hr")
	img: TagExpr = TagExpr("img")
	input: TagExpr = TagExpr("input")
	link: TagExpr = TagExpr("link")
	meta: TagExpr = TagExpr("meta")
	param: TagExpr = TagExpr("param")
	source: TagExpr = TagExpr("source")
	track: TagExpr = TagExpr("track")
	wbr: TagExpr = TagExpr("wbr")

	# SVG tags
	svg: TagExpr = TagExpr("svg")
	circle: TagExpr = TagExpr("circle")
	ellipse: TagExpr = TagExpr("ellipse")
	g: TagExpr = TagExpr("g")
	line: TagExpr = TagExpr("line")
	path: TagExpr = TagExpr("path")
	polygon: TagExpr = TagExpr("polygon")
	polyline: TagExpr = TagExpr("polyline")
	rect: TagExpr = TagExpr("rect")
	text: TagExpr = TagExpr("text")
	tspan: TagExpr = TagExpr("tspan")
	defs: TagExpr = TagExpr("defs")
	clipPath: TagExpr = TagExpr("clipPath")
	mask: TagExpr = TagExpr("mask")
	pattern: TagExpr = TagExpr("pattern")
	use: TagExpr = TagExpr("use")

	# React fragment
	fragment: TagExpr = TagExpr("")

	# For component - maps to array.map()
	For: Callable[..., Expr] = emit_for
