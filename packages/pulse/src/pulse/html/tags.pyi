from typing import Any, Optional, Protocol, Unpack

from pulse.html.props import (
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
    HTMLSVGProps,
    HTMLScriptProps,
    HTMLSelectProps,
    HTMLSourceProps,
    HTMLStyleProps,
    HTMLTableProps,
    HTMLTdProps,
    HTMLTextareaProps,
    HTMLThProps,
    HTMLTimeProps,
    HTMLTrackProps,
    HTMLVideoProps,
)
from pulse.vdom import Child, Node

class Tag(Protocol):
    def __call__(self, *children: Child, **props) -> Node: ...

def define_tag(
    name: str,
    default_props: Optional[dict[str, Any]] = None,
) -> Tag: ...
def define_self_closing_tag(
    name: str,
    default_props: Optional[dict[str, Any]] = None,
) -> Tag: ...

# --- Self-closing tags ----
def area(*, key: Optional[str] = None, **props: Unpack[HTMLAreaProps]) -> Node: ...
def base(*, key: Optional[str] = None, **props: Unpack[HTMLBaseProps]) -> Node: ...
def br(*, key: Optional[str] = None, **props: Unpack[HTMLProps]) -> Node: ...
def col(*, key: Optional[str] = None, **props: Unpack[HTMLColProps]) -> Node: ...
def embed(*, key: Optional[str] = None, **props: Unpack[HTMLEmbedProps]) -> Node: ...
def hr(*, key: Optional[str] = None, **props: Unpack[HTMLProps]) -> Node: ...
def img(*, key: Optional[str] = None, **props: Unpack[HTMLImgProps]) -> Node: ...
def input(*, key: Optional[str] = None, **props: Unpack[HTMLInputProps]) -> Node: ...
def link(*, key: Optional[str] = None, **props: Unpack[HTMLLinkProps]) -> Node: ...
def meta(*, key: Optional[str] = None, **props: Unpack[HTMLMetaProps]) -> Node: ...
def param(*, key: Optional[str] = None, **props: Unpack[HTMLParamProps]) -> Node: ...
def source(*, key: Optional[str] = None, **props: Unpack[HTMLSourceProps]) -> Node: ...
def track(*, key: Optional[str] = None, **props: Unpack[HTMLTrackProps]) -> Node: ...
def wbr(*, key: Optional[str] = None, **props: Unpack[HTMLProps]) -> Node: ...

# --- Regular tags ---

def a(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLAnchorProps]
) -> Node: ...
def abbr(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def address(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def article(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def aside(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def audio(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLAudioProps]
) -> Node: ...
def b(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def bdi(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def bdo(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def blockquote(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLBlockquoteProps],
) -> Node: ...
def body(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def button(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLButtonProps]
) -> Node: ...
def canvas(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLCanvasProps]
) -> Node: ...
def caption(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def cite(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def code(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def colgroup(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLColgroupProps],
) -> Node: ...
def data(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLDataProps]
) -> Node: ...
def datalist(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def dd(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def del_(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLDelProps]
) -> Node: ...
def details(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLDetailsProps],
) -> Node: ...
def dfn(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def dialog(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLDialogProps]
) -> Node: ...
def div(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def dl(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def dt(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def em(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def fieldset(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLFieldsetProps],
) -> Node: ...
def figcaption(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def figure(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def footer(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def form(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLFormProps]
) -> Node: ...
def h1(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def h2(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def h3(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def h4(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def h5(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def h6(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def head(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def header(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def hgroup(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def html(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLHtmlProps]
) -> Node: ...
def i(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def iframe(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLIframeProps]
) -> Node: ...
def ins(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLInsProps]
) -> Node: ...
def kbd(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def label(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLLabelProps]
) -> Node: ...
def legend(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def li(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLLiProps]
) -> Node: ...
def main(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def map_(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLMapProps]
) -> Node: ...
def mark(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def menu(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLMenuProps]
) -> Node: ...
def meter(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLMeterProps]
) -> Node: ...
def nav(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def noscript(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def object_(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLObjectProps]
) -> Node: ...
def ol(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLOlProps]
) -> Node: ...
def optgroup(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLOptgroupProps],
) -> Node: ...
def option(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLOptionProps]
) -> Node: ...
def output(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLOutputProps]
) -> Node: ...
def p(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def picture(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def pre(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def progress(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLProgressProps],
) -> Node: ...
def q(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLQuoteProps]
) -> Node: ...
def rp(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def rt(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def ruby(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def s(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def samp(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def script(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLScriptProps]
) -> Node: ...
def section(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def select(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSelectProps]
) -> Node: ...
def small(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def span(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def strong(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def style(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLStyleProps]
) -> Node: ...
def sub(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def summary(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def sup(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def table(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLTableProps]
) -> Node: ...
def tbody(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def td(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLTdProps]
) -> Node: ...
def template(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def textarea(
    *children: Child,
    key: Optional[str] = None,
    **props: Unpack[HTMLTextareaProps],
) -> Node: ...
def tfoot(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def th(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLThProps]
) -> Node: ...
def thead(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def time(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLTimeProps]
) -> Node: ...
def title(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def tr(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def u(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def ul(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def var(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLProps]
) -> Node: ...
def video(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLVideoProps]
) -> Node: ...

# -- React Fragment ---
def fragment(*children: Child, key: Optional[str] = None) -> Node: ...

# -- SVG --
def svg(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def circle(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def ellipse(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def g(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def line(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def path(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def polygon(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def polyline(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def rect(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def text(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def tspan(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def defs(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def clipPath(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def mask(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def pattern(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...
def use(
    *children: Child, key: Optional[str] = None, **props: Unpack[HTMLSVGProps]
) -> Node: ...

