# ########################
# ##### NOTES ON IMPORT FORMAT
# ########################
#
# This file defines Pulse's public API. Imports need to be structured/formatted so as to to ensure
# that the broadest possible set of static analyzers understand Pulse's public API as intended.
# The below guidelines ensure this is the case.
#
# (1) All imports in this module intended to define exported symbols should be of the form `from
# pulse.foo import X as X`. This is because imported symbols are not by default considered public
# by static analyzers. The redundant alias form `import X as X` overwrites the private imported `X`
# with a public `X` bound to the same value. It is also possible to expose `X` as public by listing
# it inside `__all__`, but the redundant alias form is preferred here due to easier maintainability.

# (2) All imports should target the module in which a symbol is actually defined, rather than a
# container module where it is imported.

# Core app/session
from pulse.app import App as App, DeploymentMode as DeploymentMode
from pulse.render_session import (
    RenderSession as RenderSession,
    RouteMount as RouteMount,
)
from pulse.context import PulseContext as PulseContext

# Environment
from pulse.env import PulseMode as PulseMode, env as env, mode as mode

# State and routing
from pulse.state import State as State
from pulse.routing import Layout as Layout, Route as Route

# Reactivity primitives
from pulse.reactive import (
    AsyncEffect as AsyncEffect,
    AsyncEffectFn as AsyncEffectFn,
    Batch as Batch,
    Computed as Computed,
    Effect as Effect,
    EffectFn as EffectFn,
    IgnoreBatch as IgnoreBatch,
    Signal as Signal,
    Untrack as Untrack,
)

# Reactive containers
from pulse.reactive_extensions import (
    ReactiveDict as ReactiveDict,
    ReactiveList as ReactiveList,
    ReactiveSet as ReactiveSet,
    reactive as reactive,
    unwrap as unwrap,
)

# Hooks - Core
from pulse.hooks.core import (
    HOOK_CONTEXT as HOOK_CONTEXT,
    HooksAPI as HooksAPI,
    HookContext as HookContext,
    Hook as Hook,
    HookError as HookError,
    HookInit as HookInit,
    HookMetadata as HookMetadata,
    HookNamespace as HookNamespace,
    HookNotFoundError as HookNotFoundError,
    HookRegistry as HookRegistry,
    HookRenameCollisionError as HookRenameCollisionError,
    HookState as HookState,
    HookAlreadyRegisteredError as HookAlreadyRegisteredError,
    MISSING as MISSING,
    hooks as hooks,
)

# Hooks - Effects
from pulse.hooks.effects import EffectsHookState as EffectsHookState, effects as effects

# Hooks - Runtime
from pulse.hooks.runtime import (
    RedirectInterrupt as RedirectInterrupt,
    NotFoundInterrupt as NotFoundInterrupt,
    call_api as call_api,
    client_address as client_address,
    global_state as global_state,
    navigate as navigate,
    not_found as not_found,
    redirect as redirect,
    route as route,
    server_address as server_address,
    session as session,
    session_id as session_id,
    set_cookie as set_cookie,
    websocket_id as websocket_id,
    GLOBAL_STATES as GLOBAL_STATES,
    GlobalStateAccessor as GlobalStateAccessor,
)

# Hooks - Setup
from pulse.hooks.setup import (
    SetupHookState as SetupHookState,
    setup as setup,
    setup_key as setup_key,
)

# Hooks - Stable
from pulse.hooks.stable import (
    stable as stable,
    StableEntry as StableEntry,
    StableRegistry as StableRegistry,
)

# Hooks - States
from pulse.hooks.states import StatesHookState as StatesHookState, states as states

# HTML Elements
from pulse.html.elements import (
    HTMLOrSVGElement as HTMLOrSVGElement,
    HTMLElementBase as HTMLElementBase,
    HTMLElement as HTMLElement,
    GenericHTMLElement as GenericHTMLElement,
    HTMLAnchorElement as HTMLAnchorElement,
    HTMLAreaElement as HTMLAreaElement,
    HTMLMediaElement as HTMLMediaElement,
    HTMLAudioElement as HTMLAudioElement,
    HTMLButtonElement as HTMLButtonElement,
    HTMLDataElement as HTMLDataElement,
    HTMLEmbedElement as HTMLEmbedElement,
    HTMLFieldSetElement as HTMLFieldSetElement,
    HTMLFormElement as HTMLFormElement,
    HTMLIFrameElement as HTMLIFrameElement,
    HTMLImageElement as HTMLImageElement,
    HTMLInputElement as HTMLInputElement,
    HTMLLabelElement as HTMLLabelElement,
    HTMLLiElement as HTMLLiElement,
    HTMLLinkElement as HTMLLinkElement,
    HTMLMapElement as HTMLMapElement,
    HTMLMeterElement as HTMLMeterElement,
    HTMLModElement as HTMLModElement,
    HTMLOListElement as HTMLOListElement,
    HTMLObjectElement as HTMLObjectElement,
    HTMLOptGroupElement as HTMLOptGroupElement,
    HTMLOptionElement as HTMLOptionElement,
    HTMLOutputElement as HTMLOutputElement,
    HTMLProgressElement as HTMLProgressElement,
    HTMLQuoteElement as HTMLQuoteElement,
    HTMLCiteElement as HTMLCiteElement,
    HTMLScriptElement as HTMLScriptElement,
    HTMLSelectElement as HTMLSelectElement,
    HTMLSlotElement as HTMLSlotElement,
    HTMLSourceElement as HTMLSourceElement,
    HTMLTableCaptionElement as HTMLTableCaptionElement,
    HTMLTableCellElement as HTMLTableCellElement,
    HTMLTableColElement as HTMLTableColElement,
    HTMLTableElement as HTMLTableElement,
    HTMLTableRowElement as HTMLTableRowElement,
    HTMLTableSectionElement as HTMLTableSectionElement,
    HTMLTemplateElement as HTMLTemplateElement,
    HTMLTextAreaElement as HTMLTextAreaElement,
    HTMLTimeElement as HTMLTimeElement,
    HTMLTrackElement as HTMLTrackElement,
    HTMLVideoElement as HTMLVideoElement,
    HTMLBRElement as HTMLBRElement,
    HTMLBaseElement as HTMLBaseElement,
    HTMLBodyElement as HTMLBodyElement,
    HTMLDListElement as HTMLDListElement,
    HTMLDetailsElement as HTMLDetailsElement,
    HTMLDialogElement as HTMLDialogElement,
    HTMLDivElement as HTMLDivElement,
    HTMLHeadElement as HTMLHeadElement,
    HTMLHeadingElement as HTMLHeadingElement,
    HTMLHRElement as HTMLHRElement,
    HTMLHtmlElement as HTMLHtmlElement,
    HTMLMenuElement as HTMLMenuElement,
    HTMLMetaElement as HTMLMetaElement,
    HTMLParagraphElement as HTMLParagraphElement,
    HTMLPictureElement as HTMLPictureElement,
    HTMLPreElement as HTMLPreElement,
    HTMLSpanElement as HTMLSpanElement,
    HTMLStyleElement as HTMLStyleElement,
    HTMLTitleElement as HTMLTitleElement,
    HTMLUListElement as HTMLUListElement,
)

# HTML Events
from pulse.html.events import (
    DataTransferItem as DataTransferItem,
    DataTransfer as DataTransfer,
    Touch as Touch,
    SyntheticEvent as SyntheticEvent,
    UIEvent as UIEvent,
    MouseEvent as MouseEvent,
    ClipboardEvent as ClipboardEvent,
    CompositionEvent as CompositionEvent,
    DragEvent as DragEvent,
    PointerEvent as PointerEvent,
    FocusEvent as FocusEvent,
    FormEvent as FormEvent,
    InvalidEvent as InvalidEvent,
    ChangeEvent as ChangeEvent,
    KeyboardEvent as KeyboardEvent,
    TouchEvent as TouchEvent,
    WheelEvent as WheelEvent,
    AnimationEvent as AnimationEvent,
    ToggleEvent as ToggleEvent,
    TransitionEvent as TransitionEvent,
    DOMEvents as DOMEvents,
    FormControlDOMEvents as FormControlDOMEvents,
    InputDOMEvents as InputDOMEvents,
    TextAreaDOMEvents as TextAreaDOMEvents,
    SelectDOMEvents as SelectDOMEvents,
    DialogDOMEvents as DialogDOMEvents,
)

# HTML Props
from pulse.html.props import (
    ClassName as ClassName,
    BaseHTMLProps as BaseHTMLProps,
    HTMLProps as HTMLProps,
    HTMLAbbrProps as HTMLAbbrProps,
    HTMLAddressProps as HTMLAddressProps,
    HTMLAnchorProps as HTMLAnchorProps,
    HTMLAreaProps as HTMLAreaProps,
    HTMLArticleProps as HTMLArticleProps,
    HTMLAsideProps as HTMLAsideProps,
    HTMLAudioProps as HTMLAudioProps,
    HTMLBProps as HTMLBProps,
    HTMLBDIProps as HTMLBDIProps,
    HTMLBDOProps as HTMLBDOProps,
    HTMLBaseProps as HTMLBaseProps,
    HTMLBlockquoteProps as HTMLBlockquoteProps,
    HTMLBodyProps as HTMLBodyProps,
    HTMLBRProps as HTMLBRProps,
    HTMLButtonProps as HTMLButtonProps,
    HTMLCanvasProps as HTMLCanvasProps,
    HTMLCaptionProps as HTMLCaptionProps,
    HTMLCiteProps as HTMLCiteProps,
    HTMLCircleProps as HTMLCircleProps,
    HTMLClipPathProps as HTMLClipPathProps,
    HTMLCodeProps as HTMLCodeProps,
    HTMLColProps as HTMLColProps,
    HTMLColgroupProps as HTMLColgroupProps,
    HTMLDatalistProps as HTMLDatalistProps,
    HTMLDataProps as HTMLDataProps,
    HTMLDDProps as HTMLDDProps,
    HTMLDefsProps as HTMLDefsProps,
    HTMLDelProps as HTMLDelProps,
    HTMLDetailsProps as HTMLDetailsProps,
    HTMLDFNProps as HTMLDFNProps,
    HTMLDialogProps as HTMLDialogProps,
    HTMLDivProps as HTMLDivProps,
    HTMLDLProps as HTMLDLProps,
    HTMLDTProps as HTMLDTProps,
    HTMLEllipseProps as HTMLEllipseProps,
    HTMLEmbedProps as HTMLEmbedProps,
    HTMLEMProps as HTMLEMProps,
    HTMLFieldsetProps as HTMLFieldsetProps,
    HTMLFigcaptionProps as HTMLFigcaptionProps,
    HTMLFigureProps as HTMLFigureProps,
    HTMLFooterProps as HTMLFooterProps,
    HTMLFormProps as HTMLFormProps,
    HTMLFragmentProps as HTMLFragmentProps,
    HTMLGProps as HTMLGProps,
    HTMLH1Props as HTMLH1Props,
    HTMLH2Props as HTMLH2Props,
    HTMLH3Props as HTMLH3Props,
    HTMLH4Props as HTMLH4Props,
    HTMLH5Props as HTMLH5Props,
    HTMLH6Props as HTMLH6Props,
    HTMLHeadProps as HTMLHeadProps,
    HTMLHeaderProps as HTMLHeaderProps,
    HTMLHgroupProps as HTMLHgroupProps,
    HTMLHRProps as HTMLHRProps,
    HTMLHtmlProps as HTMLHtmlProps,
    HTMLIProps as HTMLIProps,
    HTMLIframeProps as HTMLIframeProps,
    HTMLImgProps as HTMLImgProps,
    HTMLInsProps as HTMLInsProps,
    HTMLInputProps as HTMLInputProps,
    HTMLKBDProps as HTMLKBDProps,
    HTMLKeygenProps as HTMLKeygenProps,
    HTMLLabelProps as HTMLLabelProps,
    HTMLLegendProps as HTMLLegendProps,
    HTMLLiProps as HTMLLiProps,
    HTMLLineProps as HTMLLineProps,
    HTMLLinkProps as HTMLLinkProps,
    HTMLMainProps as HTMLMainProps,
    HTMLMapProps as HTMLMapProps,
    HTMLMarkProps as HTMLMarkProps,
    HTMLMaskProps as HTMLMaskProps,
    HTMLMediaProps as HTMLMediaProps,
    HTMLMenuProps as HTMLMenuProps,
    HTMLMetaProps as HTMLMetaProps,
    HTMLMeterProps as HTMLMeterProps,
    HTMLNavProps as HTMLNavProps,
    HTMLNoscriptProps as HTMLNoscriptProps,
    HTMLObjectProps as HTMLObjectProps,
    HTMLOlProps as HTMLOlProps,
    HTMLOptgroupProps as HTMLOptgroupProps,
    HTMLOptionProps as HTMLOptionProps,
    HTMLOutputProps as HTMLOutputProps,
    HTMLPProps as HTMLPProps,
    HTMLParamProps as HTMLParamProps,
    HTMLPathProps as HTMLPathProps,
    HTMLPatternProps as HTMLPatternProps,
    HTMLPictureProps as HTMLPictureProps,
    HTMLPolygonProps as HTMLPolygonProps,
    HTMLPolylineProps as HTMLPolylineProps,
    HTMLPreProps as HTMLPreProps,
    HTMLProgressProps as HTMLProgressProps,
    HTMLQProps as HTMLQProps,
    HTMLQuoteProps as HTMLQuoteProps,
    HTMLRPProps as HTMLRPProps,
    HTMLRTProps as HTMLRTProps,
    HTMLRectProps as HTMLRectProps,
    HTMLRubyProps as HTMLRubyProps,
    HTMLSProps as HTMLSProps,
    HTMLSampProps as HTMLSampProps,
    HTMLScriptProps as HTMLScriptProps,
    HTMLSectionProps as HTMLSectionProps,
    HTMLSelectProps as HTMLSelectProps,
    HTMLSlotProps as HTMLSlotProps,
    HTMLSmallProps as HTMLSmallProps,
    HTMLSourceProps as HTMLSourceProps,
    HTMLSpanProps as HTMLSpanProps,
    HTMLStrongProps as HTMLStrongProps,
    HTMLStyleProps as HTMLStyleProps,
    HTMLSubProps as HTMLSubProps,
    HTMLSummaryProps as HTMLSummaryProps,
    HTMLSupProps as HTMLSupProps,
    HTMLSVGProps as HTMLSVGProps,
    HTMLTableProps as HTMLTableProps,
    HTMLTBODYProps as HTMLTBODYProps,
    HTMLTdProps as HTMLTdProps,
    HTMLTemplateProps as HTMLTemplateProps,
    HTMLTextProps as HTMLTextProps,
    HTMLTextareaProps as HTMLTextareaProps,
    HTMLThProps as HTMLThProps,
    HTMLTimeProps as HTMLTimeProps,
    HTMLTitleProps as HTMLTitleProps,
    HTMLTrackProps as HTMLTrackProps,
    HTMLTspanProps as HTMLTspanProps,
    HTMLUProps as HTMLUProps,
    HTMLULProps as HTMLULProps,
    HTMLUseProps as HTMLUseProps,
    HTMLVarProps as HTMLVarProps,
    HTMLVideoProps as HTMLVideoProps,
    HTMLWBRProps as HTMLWBRProps,
    WebViewAttributes as WebViewAttributes,
)

# HTML Tags
from pulse.html.tags import (
    a as a,
    abbr as abbr,
    address as address,
    article as article,
    aside as aside,
    audio as audio,
    b as b,
    bdi as bdi,
    bdo as bdo,
    blockquote as blockquote,
    body as body,
    button as button,
    canvas as canvas,
    caption as caption,
    cite as cite,
    code as code,
    colgroup as colgroup,
    data as data,
    datalist as datalist,
    dd as dd,
    del_ as del_,
    details as details,
    dfn as dfn,
    dialog as dialog,
    div as div,
    dl as dl,
    dt as dt,
    em as em,
    fieldset as fieldset,
    figcaption as figcaption,
    figure as figure,
    footer as footer,
    form as form,
    h1 as h1,
    h2 as h2,
    h3 as h3,
    h4 as h4,
    h5 as h5,
    h6 as h6,
    head as head,
    header as header,
    hgroup as hgroup,
    html as html,
    i as i,
    iframe as iframe,
    ins as ins,
    kbd as kbd,
    label as label,
    legend as legend,
    li as li,
    main as main,
    map_ as map_,
    mark as mark,
    menu as menu,
    meter as meter,
    nav as nav,
    noscript as noscript,
    object_ as object_,
    ol as ol,
    optgroup as optgroup,
    option as option,
    output as output,
    p as p,
    picture as picture,
    pre as pre,
    progress as progress,
    q as q,
    rp as rp,
    rt as rt,
    ruby as ruby,
    s as s,
    samp as samp,
    script as script,
    section as section,
    select as select,
    small as small,
    span as span,
    strong as strong,
    style as style,
    sub as sub,
    summary as summary,
    sup as sup,
    table as table,
    tbody as tbody,
    td as td,
    template as template,
    textarea as textarea,
    tfoot as tfoot,
    th as th,
    thead as thead,
    time as time,
    title as title,
    tr as tr,
    u as u,
    ul as ul,
    var as var,
    video as video,
    area as area,
    base as base,
    br as br,
    col as col,
    embed as embed,
    hr as hr,
    img as img,
    input as input,
    link as link,
    meta as meta,
    param as param,
    source as source,
    track as track,
    wbr as wbr,
    fragment as fragment,
    svg as svg,
    circle as circle,
    ellipse as ellipse,
    g as g,
    line as line,
    path as path,
    polygon as polygon,
    polyline as polyline,
    rect as rect,
    text as text,
    tspan as tspan,
    defs as defs,
    clipPath as clipPath,
    mask as mask,
    pattern as pattern,
    use as use,
)

# Middleware
from pulse.middleware import (
    ConnectResponse as ConnectResponse,
    Deny as Deny,
    MiddlewareStack as MiddlewareStack,
    NotFound as NotFound,
    Ok as Ok,
    PrerenderResponse as PrerenderResponse,
    PulseMiddleware as PulseMiddleware,
    Redirect as Redirect,
    stack as stack,
)

# Plugin
from pulse.plugin import Plugin as Plugin

# React component registry
from pulse.react_component import (
    COMPONENT_REGISTRY as COMPONENT_REGISTRY,
    DEFAULT as DEFAULT,
    ComponentRegistry as ComponentRegistry,
    Prop as Prop,
    ReactComponent as ReactComponent,
    prop as prop,
    react_component as react_component,
    registered_react_components as registered_react_components,
)

# Forms
from pulse.form import (
    Form as Form,
    FormData as FormData,
    FormValue as FormValue,
    ManualForm as ManualForm,
    UploadFile as UploadFile,
)

# Codegen
from pulse.codegen.codegen import CodegenConfig as CodegenConfig

# Channels
from pulse.channel import (
    channel as channel,
    PulseChannel as PulseChannel,
    PulseChannelClosed as PulseChannelClosed,
    PulseChannelTimeout as PulseChannelTimeout,
)

# Router components
from pulse.components.react_router import Link as Link, Outlet as Outlet

# Built-in components
from pulse.components.for_ import For as For
from pulse.components.if_ import If as If

# Types
from pulse.types.event_handler import (
    EventHandler0 as EventHandler0,
    EventHandler1 as EventHandler1,
    EventHandler2 as EventHandler2,
    EventHandler3 as EventHandler3,
    EventHandler4 as EventHandler4,
    EventHandler5 as EventHandler5,
    EventHandler6 as EventHandler6,
    EventHandler7 as EventHandler7,
    EventHandler8 as EventHandler8,
    EventHandler9 as EventHandler9,
    EventHandler10 as EventHandler10,
)

# Helpers
from pulse.helpers import (
    CSSProperties as CSSProperties,
    JsFunction as JsFunction,
    JsObject as JsObject,
    later as later,
    repeat as repeat,
)

# Session context infra
from pulse.user_session import (
    CookieSessionStore as CookieSessionStore,
    InMemorySessionStore as InMemorySessionStore,
    SessionStore as SessionStore,
    UserSession as UserSession,
)

# Cookies
from pulse.cookies import Cookie as Cookie, SetCookie as SetCookie

# CSS
from pulse.css import css as css, css_module as css_module

# Decorators
from pulse.decorators import computed as computed, effect as effect, query as query

# Request
from pulse.request import PulseRequest as PulseRequest

# Serializer
from pulse.serializer_v3 import serialize as serialize, deserialize as deserialize

# VDOM
from pulse.vdom import (
    Child as Child,
    Component as Component,
    ComponentNode as ComponentNode,
    Node as Node,
    Element as Element,
    Primitive as Primitive,
    VDOMNode as VDOMNode,
    component as component,
)
