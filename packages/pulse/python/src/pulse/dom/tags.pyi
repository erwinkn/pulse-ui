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
from pulse.transpiler_v2.nodes import Element
from pulse.transpiler_v2.nodes import Node as Child

class Tag(Protocol):
	def __call__(self, *children: Child, **props: Any) -> Element: ...

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
	*children: Child, key: str | None = None, **props: Unpack[HTMLAnchorProps]
) -> Element: ...
def abbr(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def address(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def article(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def aside(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def audio(
	*children: Child, key: str | None = None, **props: Unpack[HTMLAudioProps]
) -> Element: ...
def b(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def bdi(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def bdo(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def blockquote(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLBlockquoteProps],
) -> Element: ...
def body(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def button(
	*children: Child, key: str | None = None, **props: Unpack[HTMLButtonProps]
) -> Element: ...
def canvas(
	*children: Child, key: str | None = None, **props: Unpack[HTMLCanvasProps]
) -> Element: ...
def caption(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def cite(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def code(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def colgroup(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLColgroupProps],
) -> Element: ...
def data(
	*children: Child, key: str | None = None, **props: Unpack[HTMLDataProps]
) -> Element: ...
def datalist(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dd(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def del_(
	*children: Child, key: str | None = None, **props: Unpack[HTMLDelProps]
) -> Element: ...
def details(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLDetailsProps],
) -> Element: ...
def dfn(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dialog(
	*children: Child, key: str | None = None, **props: Unpack[HTMLDialogProps]
) -> Element: ...
def div(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dl(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def dt(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def em(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def fieldset(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLFieldsetProps],
) -> Element: ...
def figcaption(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def figure(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def footer(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def form(
	*children: Child, key: str | None = None, **props: Unpack[HTMLFormProps]
) -> Element: ...
def h1(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h2(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h3(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h4(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h5(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def h6(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def head(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def header(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def hgroup(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def html(
	*children: Child, key: str | None = None, **props: Unpack[HTMLHtmlProps]
) -> Element: ...
def i(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def iframe(
	*children: Child, key: str | None = None, **props: Unpack[HTMLIframeProps]
) -> Element: ...
def ins(
	*children: Child, key: str | None = None, **props: Unpack[HTMLInsProps]
) -> Element: ...
def kbd(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def label(
	*children: Child, key: str | None = None, **props: Unpack[HTMLLabelProps]
) -> Element: ...
def legend(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def li(
	*children: Child, key: str | None = None, **props: Unpack[HTMLLiProps]
) -> Element: ...
def main(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def map_(
	*children: Child, key: str | None = None, **props: Unpack[HTMLMapProps]
) -> Element: ...
def mark(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def menu(
	*children: Child, key: str | None = None, **props: Unpack[HTMLMenuProps]
) -> Element: ...
def meter(
	*children: Child, key: str | None = None, **props: Unpack[HTMLMeterProps]
) -> Element: ...
def nav(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def noscript(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def object_(
	*children: Child, key: str | None = None, **props: Unpack[HTMLObjectProps]
) -> Element: ...
def ol(
	*children: Child, key: str | None = None, **props: Unpack[HTMLOlProps]
) -> Element: ...
def optgroup(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLOptgroupProps],
) -> Element: ...
def option(
	*children: Child, key: str | None = None, **props: Unpack[HTMLOptionProps]
) -> Element: ...
def output(
	*children: Child, key: str | None = None, **props: Unpack[HTMLOutputProps]
) -> Element: ...
def p(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def picture(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def pre(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def progress(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLProgressProps],
) -> Element: ...
def q(
	*children: Child, key: str | None = None, **props: Unpack[HTMLQuoteProps]
) -> Element: ...
def rp(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def rt(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def ruby(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def s(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def samp(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def script(
	*children: Child, key: str | None = None, **props: Unpack[HTMLScriptProps]
) -> Element: ...
def section(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def select(
	*children: Child, key: str | None = None, **props: Unpack[HTMLSelectProps]
) -> Element: ...
def small(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def span(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def strong(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def style(
	*children: Child, key: str | None = None, **props: Unpack[HTMLStyleProps]
) -> Element: ...
def sub(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def summary(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def sup(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def table(
	*children: Child, key: str | None = None, **props: Unpack[HTMLTableProps]
) -> Element: ...
def tbody(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def td(
	*children: Child, key: str | None = None, **props: Unpack[HTMLTdProps]
) -> Element: ...
def template(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def textarea(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLTextareaProps],
) -> Element: ...
def tfoot(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def th(
	*children: Child, key: str | None = None, **props: Unpack[HTMLThProps]
) -> Element: ...
def thead(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def time(
	*children: Child, key: str | None = None, **props: Unpack[HTMLTimeProps]
) -> Element: ...
def title(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def tr(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def u(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def ul(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def var(
	*children: Child, key: str | None = None, **props: Unpack[HTMLProps]
) -> Element: ...
def video(
	*children: Child, key: str | None = None, **props: Unpack[HTMLVideoProps]
) -> Element: ...

# -- React Fragment ---
def fragment(*children: Child, key: str | None = None) -> Element: ...

# -- SVG --
def svg(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def circle(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def ellipse(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def g(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def line(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def path(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def polygon(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def polyline(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def rect(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def text(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def tspan(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def defs(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def clipPath(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def mask(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def pattern(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...
def use(
	*children: Child,
	key: str | None = None,
	**props: Unpack[HTMLSVGProps[GenericHTMLElement]],
) -> Element: ...

# Lists exported for JS transpiler
TAGS: list[tuple[str, dict[str, Any] | None]]
SELF_CLOSING_TAGS: list[tuple[str, dict[str, Any] | None]]
