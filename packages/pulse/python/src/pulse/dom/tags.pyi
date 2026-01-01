from typing import Any, Protocol, Unpack

from pulse.dom.elements import GenericHTMLElement
from pulse.dom.props import (
	HTMLAnchorProps,
	HTMLAreaProps,
	HTMLAudioProps,
	HTMLBaseProps,
	HTMLBlockquoteProps,
	HTMLButtonProps,
	HTMLCanvasProps,
	HTMLColgroupProps,
	HTMLColProps,
	HTMLDataProps,
	HTMLDelProps,
	HTMLDetailsProps,
	HTMLDialogProps,
	HTMLEmbedProps,
	HTMLFieldsetProps,
	HTMLFormProps,
	HTMLHtmlProps,
	HTMLIframeProps,
	HTMLImgProps,
	HTMLInputProps,
	HTMLInsProps,
	HTMLLabelProps,
	HTMLLinkProps,
	HTMLLiProps,
	HTMLMapProps,
	HTMLMenuProps,
	HTMLMetaProps,
	HTMLMeterProps,
	HTMLObjectProps,
	HTMLOlProps,
	HTMLOptgroupProps,
	HTMLOptionProps,
	HTMLOutputProps,
	HTMLParamProps,
	HTMLProgressProps,
	HTMLProps,
	HTMLQuoteProps,
	HTMLScriptProps,
	HTMLSelectProps,
	HTMLSourceProps,
	HTMLStyleProps,
	HTMLSVGProps,
	HTMLTableProps,
	HTMLTdProps,
	HTMLTextareaProps,
	HTMLThProps,
	HTMLTimeProps,
	HTMLTrackProps,
	HTMLVideoProps,
)
from pulse.transpiler.nodes import Element, Node

class Tag(Protocol):
	def __call__(self, *children: Node, **props: Any) -> Element: ...

def define_tag(
	name: str,
	default_props: dict[str, Any] | None = None,
) -> Tag: ...
def define_self_closing_tag(
	name: str,
	default_props: dict[str, Any] | None = None,
) -> Tag: ...

# --- Self-closing tags ----
def area(*, key: str | None = None, **props: Unpack[HTMLAreaProps]) -> Element: ...
def base(*, key: str | None = None, **props: Unpack[HTMLBaseProps]) -> Element: ...
def br(*, key: str | None = None, **props: Unpack[HTMLProps]) -> Element: ...
def col(*, key: str | None = None, **props: Unpack[HTMLColProps]) -> Element: ...
def embed(*, key: str | None = None, **props: Unpack[HTMLEmbedProps]) -> Element: ...
def hr(*, key: str | None = None, **props: Unpack[HTMLProps]) -> Element: ...
def img(*, key: str | None = None, **props: Unpack[HTMLImgProps]) -> Element: ...
def input(*, key: str | None = None, **props: Unpack[HTMLInputProps]) -> Element: ...
def link(*, key: str | None = None, **props: Unpack[HTMLLinkProps]) -> Element: ...
def meta(*, key: str | None = None, **props: Unpack[HTMLMetaProps]) -> Element: ...
def param(*, key: str | None = None, **props: Unpack[HTMLParamProps]) -> Element: ...
def source(*, key: str | None = None, **props: Unpack[HTMLSourceProps]) -> Element: ...
def track(*, key: str | None = None, **props: Unpack[HTMLTrackProps]) -> Element: ...
def wbr(*, key: str | None = None, **props: Unpack[HTMLProps]) -> Element: ...

# --- Regular tags ---

def a(
	*children: Node, key: str | None = None, **props: Unpack[HTMLAnchorProps]
) -> Element: ...
def abbr(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def address(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def article(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def aside(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def audio(
	*children: Node, key: str | None = None, **props: Unpack[HTMLAudioProps]
) -> Element: ...
def b(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def bdi(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def bdo(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def blockquote(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLBlockquoteProps],
) -> Element: ...
def body(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def button(
	*children: Node, key: str | None = None, **props: Unpack[HTMLButtonProps]
) -> Element: ...
def canvas(
	*children: Node, key: str | None = None, **props: Unpack[HTMLCanvasProps]
) -> Element: ...
def caption(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def cite(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def code(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def colgroup(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLColgroupProps],
) -> Element: ...
def data(
	*children: Node, key: str | None = None, **props: Unpack[HTMLDataProps]
) -> Element: ...
def datalist(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dd(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def del_(
	*children: Node, key: str | None = None, **props: Unpack[HTMLDelProps]
) -> Element: ...
def details(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLDetailsProps],
) -> Element: ...
def dfn(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dialog(
	*children: Node, key: str | None = None, **props: Unpack[HTMLDialogProps]
) -> Element: ...
def div(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dl(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dt(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def em(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def fieldset(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLFieldsetProps],
) -> Element: ...
def figcaption(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def figure(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def footer(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def form(
	*children: Node, key: str | None = None, **props: Unpack[HTMLFormProps]
) -> Element: ...
def h1(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h2(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h3(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h4(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h5(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h6(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def head(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def header(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def hgroup(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def html(
	*children: Node, key: str | None = None, **props: Unpack[HTMLHtmlProps]
) -> Element: ...
def i(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def iframe(
	*children: Node, key: str | None = None, **props: Unpack[HTMLIframeProps]
) -> Element: ...
def ins(
	*children: Node, key: str | None = None, **props: Unpack[HTMLInsProps]
) -> Element: ...
def kbd(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def label(
	*children: Node, key: str | None = None, **props: Unpack[HTMLLabelProps]
) -> Element: ...
def legend(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def li(
	*children: Node, key: str | None = None, **props: Unpack[HTMLLiProps]
) -> Element: ...
def main(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def map_(
	*children: Node, key: str | None = None, **props: Unpack[HTMLMapProps]
) -> Element: ...
def mark(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def menu(
	*children: Node, key: str | None = None, **props: Unpack[HTMLMenuProps]
) -> Element: ...
def meter(
	*children: Node, key: str | None = None, **props: Unpack[HTMLMeterProps]
) -> Element: ...
def nav(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def noscript(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def object_(
	*children: Node, key: str | None = None, **props: Unpack[HTMLObjectProps]
) -> Element: ...
def ol(
	*children: Node, key: str | None = None, **props: Unpack[HTMLOlProps]
) -> Element: ...
def optgroup(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLOptgroupProps],
) -> Element: ...
def option(
	*children: Node, key: str | None = None, **props: Unpack[HTMLOptionProps]
) -> Element: ...
def output(
	*children: Node, key: str | None = None, **props: Unpack[HTMLOutputProps]
) -> Element: ...
def p(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def picture(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def pre(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def progress(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLProgressProps],
) -> Element: ...
def q(
	*children: Node, key: str | None = None, **props: Unpack[HTMLQuoteProps]
) -> Element: ...
def rp(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def rt(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def ruby(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def s(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def samp(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def script(
	*children: Node, key: str | None = None, **props: Unpack[HTMLScriptProps]
) -> Element: ...
def section(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def select(
	*children: Node, key: str | None = None, **props: Unpack[HTMLSelectProps]
) -> Element: ...
def small(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def span(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def strong(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def style(
	*children: Node, key: str | None = None, **props: Unpack[HTMLStyleProps]
) -> Element: ...
def sub(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def summary(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def sup(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def table(
	*children: Node, key: str | None = None, **props: Unpack[HTMLTableProps]
) -> Element: ...
def tbody(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def td(
	*children: Node, key: str | None = None, **props: Unpack[HTMLTdProps]
) -> Element: ...
def template(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def textarea(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLTextareaProps],
) -> Element: ...
def tfoot(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def th(
	*children: Node, key: str | None = None, **props: Unpack[HTMLThProps]
) -> Element: ...
def thead(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def time(
	*children: Node, key: str | None = None, **props: Unpack[HTMLTimeProps]
) -> Element: ...
def title(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def tr(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def u(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def ul(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def var(
	*children: Node, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def video(
	*children: Node, key: str | None = None, **props: Unpack[HTMLVideoProps]
) -> Element: ...

# -- React Fragment ---
def fragment(*children: Node, key: str | None = None) -> Element: ...

# -- SVG --
def svg(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def circle(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def ellipse(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def g(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def line(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def path(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def polygon(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def polyline(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def rect(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def text(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def tspan(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def defs(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def clipPath(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def mask(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def pattern(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def use(
	*children: Node,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...

# Lists exported for JS transpiler
TAGS: list[tuple[str, dict[str, Any] | None]]
SELF_CLOSING_TAGS: list[tuple[str, dict[str, Any] | None]]
