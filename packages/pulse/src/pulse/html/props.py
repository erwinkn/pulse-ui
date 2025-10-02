# Adapted from @types/react 19.0
# NOT the same thing as the properties in `elements.py` (but very similar)
from typing import Any, List, Literal, TypedDict, Union

from pulse.css import CssReference
from pulse.helpers import CSSProperties
from pulse.html.elements import (  # noqa: F401
    GenericHTMLElement,
    HTMLAnchorElement,
    HTMLAreaElement,
    HTMLAudioElement,
    HTMLBaseElement,
    HTMLBodyElement,
    HTMLBRElement,
    HTMLButtonElement,
    HTMLCiteElement,
    HTMLDataElement,
    HTMLDetailsElement,
    HTMLDialogElement,
    HTMLDivElement,
    HTMLDListElement,
    HTMLEmbedElement,
    HTMLFieldSetElement,
    HTMLFormElement,
    HTMLHeadElement,
    HTMLHeadingElement,
    HTMLHRElement,
    HTMLHtmlElement,
    HTMLIFrameElement,
    HTMLImageElement,
    HTMLInputElement,
    HTMLLabelElement,
    HTMLLiElement,
    HTMLLinkElement,
    HTMLMapElement,
    HTMLMediaElement,
    HTMLMenuElement,
    HTMLMetaElement,
    HTMLMeterElement,
    HTMLModElement,
    HTMLObjectElement,
    HTMLOListElement,
    HTMLOptGroupElement,
    HTMLOptionElement,
    HTMLOutputElement,
    HTMLParagraphElement,
    HTMLPictureElement,
    HTMLPreElement,
    HTMLProgressElement,
    HTMLQuoteElement,
    HTMLScriptElement,
    HTMLSelectElement,
    HTMLSlotElement,
    HTMLSourceElement,
    HTMLSpanElement,
    HTMLStyleElement,
    HTMLTableCaptionElement,
    HTMLTableCellElement,
    HTMLTableColElement,
    HTMLTableElement,
    HTMLTableRowElement,
    HTMLTableSectionElement,
    HTMLTemplateElement,
    HTMLTextAreaElement,
    HTMLTimeElement,
    HTMLTitleElement,
    HTMLTrackElement,
    HTMLUListElement,
    HTMLVideoElement,
)
from pulse.html.events import (
    DialogDOMEvents,
    DOMEvents,
    InputDOMEvents,
    SelectDOMEvents,
    TElement,
    TextAreaDOMEvents,
)

Booleanish = Literal[True, False, "true", "false"]
CrossOrigin = Literal["anonymous", "use-credentials", ""] | None
ClassName = str | CssReference

class BaseHTMLProps(TypedDict, total=False):
    # React-specific Attributes
    defaultChecked: bool
    defaultValue: Union[str, int, List[str]]
    suppressContentEditableWarning: bool
    suppressHydrationWarning: bool

    # Standard HTML Attributes
    accessKey: str
    autoCapitalize: Literal["off", "none", "on", "sentences", "words", "characters"]
    autoFocus: bool
    className: ClassName
    contentEditable: Union[Booleanish, Literal["inherit", "plaintext-only"]]
    contextMenu: str
    dir: str
    draggable: Booleanish
    enterKeyHint: Literal["enter", "done", "go", "next", "previous", "search", "send"]
    hidden: bool
    id: str
    lang: str
    nonce: str
    slot: str
    spellCheck: Booleanish
    style: CSSProperties
    tabIndex: int
    title: str
    translate: Literal["yes", "no"]

    # Unknown
    radioGroup: str  # <command>, <menuitem>

    # role: skipped

    # RDFa Attributes
    about: str
    content: str
    datatype: str
    inlist: Any
    prefix: str
    property: str
    rel: str
    resource: str
    rev: str
    typeof: str
    vocab: str

    # Non-standard Attributes
    autoCorrect: str
    autoSave: str
    color: str
    itemProp: str
    itemScope: bool
    itemType: str
    itemId: str
    itemRef: str
    results: int
    security: str
    unselectable: Literal["on", "off"]

    # Popover API
    popover: Literal["", "auto", "manual"]
    popoverTargetAction: Literal["toggle", "show", "hide"]
    popoverTarget: str

    # Living Standard
    # https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/inert
    inert: bool
    # Hints at the type of data that might be entered by the user while editing the element or its contents
    # https://html.spec.whatwg.org/multipage/interaction.html#input-modalities:-the-inputmode-attribute
    inputMode: Literal[
        "none", "text", "tel", "url", "email", "numeric", "decimal", "search"
    ]

    # Specify that a standard HTML element should behave like a defined custom built-in element
    # https://html.spec.whatwg.org/multipage/custom-elements.html#attr-is
    is_: str
    # https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/exportparts
    exportparts: str
    # https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/part
    part: str


class HTMLProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False): ...


HTMLAttributeReferrerPolicy = Literal[
    "",
    "no-referrer",
    "no-referrer-when-downgrade",
    "origin",
    "origin-when-cross-origin",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
    "unsafe-url",
]


class HTMLAnchorProps(BaseHTMLProps, DOMEvents[HTMLAnchorElement], total=False):
    download: str
    href: str
    media: str
    ping: str
    target: str
    type: str
    referrerPolicy: HTMLAttributeReferrerPolicy


class HTMLAreaProps(BaseHTMLProps, DOMEvents[HTMLAreaElement], total=False):
    alt: str
    coords: str
    download: str
    href: str
    hrefLang: str
    media: str
    referrerPolicy: HTMLAttributeReferrerPolicy
    shape: str
    target: str


class HTMLBaseProps(BaseHTMLProps, DOMEvents[HTMLBaseElement], total=False):
    href: str
    target: str


class HTMLBlockquoteProps(BaseHTMLProps, DOMEvents[HTMLQuoteElement], total=False):
    cite: str


class HTMLButtonProps(BaseHTMLProps, DOMEvents[HTMLButtonElement], total=False):
    disabled: bool
    form: str
    # NOTE: support form_action callbacks?
    formAction: str
    formEncType: str
    formMethod: str
    formNoValidate: bool
    formTarget: str
    name: str
    type: Literal["submit", "reset", "button"]
    value: Union[str, List[str], int]


class HTMLCanvasProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    height: Union[int, str]
    width: Union[int, str]


class HTMLColProps(BaseHTMLProps, DOMEvents[HTMLTableColElement], total=False):
    span: int
    width: Union[int, str]


class HTMLColgroupProps(BaseHTMLProps, DOMEvents[HTMLTableColElement], total=False):
    span: int


class HTMLDataProps(BaseHTMLProps, DOMEvents[HTMLDataElement], total=False):
    value: Union[str, List[str], int]


class HTMLDetailsProps(BaseHTMLProps, DOMEvents[HTMLDetailsElement], total=False):
    open: bool
    name: str


class HTMLDelProps(BaseHTMLProps, DOMEvents[HTMLModElement], total=False):
    cite: str
    dateTime: str


class HTMLDialogProps(BaseHTMLProps, DialogDOMEvents, total=False):
    open: bool


class HTMLEmbedProps(BaseHTMLProps, DOMEvents[HTMLEmbedElement], total=False):
    height: Union[int, str]
    src: str
    type: str
    width: Union[int, str]


class HTMLFieldsetProps(BaseHTMLProps, DOMEvents[HTMLFieldSetElement], total=False):
    disabled: bool
    form: str
    name: str


class HTMLFormProps(BaseHTMLProps, DOMEvents[HTMLFormElement], total=False):
    acceptCharset: str
    # NOTE: support action callbacks?
    action: str
    autoComplete: str
    encType: str
    method: str
    name: str
    noValidate: bool
    target: str


class HTMLHtmlProps(BaseHTMLProps, DOMEvents[HTMLHtmlElement], total=False):
    manifest: str


class HTMLIframeProps(BaseHTMLProps, DOMEvents[HTMLIFrameElement], total=False):
    allow: str
    allowFullScreen: bool
    allowTransparency: bool
    frameBorder: Union[int, str]
    height: Union[int, str]
    loading: Literal["eager", "lazy"]
    marginHeight: int
    marginWidth: int
    name: str
    referrerPolicy: HTMLAttributeReferrerPolicy
    sandbox: str
    scrolling: str
    seamless: bool
    src: str
    srcDoc: str
    width: Union[int, str]


class HTMLImgProps(BaseHTMLProps, DOMEvents[HTMLImageElement], total=False):
    alt: str
    crossOrigin: CrossOrigin
    decoding: Literal["async", "auto", "sync"]
    fetchPriority: Literal["high", "low", "auto"]
    height: Union[int, str]
    loading: Literal["eager", "lazy"]
    referrerPolicy: HTMLAttributeReferrerPolicy
    sizes: str
    src: str
    srcSet: str
    useMap: str
    width: Union[int, str]


class HTMLInsProps(BaseHTMLProps, DOMEvents[HTMLModElement], total=False):
    cite: str
    dateTime: str


HTMLInputType = (
    Literal[
        "button",
        "checkbox",
        "color",
        "date",
        "datetime-local",
        "email",
        "file",
        "hidden",
        "image",
        "month",
        "number",
        "password",
        "radio",
        "range",
        "reset",
        "search",
        "submit",
        "tel",
        "text",
        "time",
        "url",
        "week",
    ]
    | str
)


class HTMLInputProps(BaseHTMLProps, InputDOMEvents, total=False):
    accept: str
    alt: str
    autoComplete: str  # HTMLInputAutoCompleteAttribute
    capture: Union[bool, Literal["user", "environment"]]
    checked: bool
    disabled: bool
    form: str
    formAction: str
    formEncType: str
    formMethod: str
    formNoValidate: bool
    formTarget: str
    height: Union[int, str]
    list: str
    max: Union[int, str]
    maxLength: int
    min: Union[int, str]
    minLength: int
    multiple: bool
    name: str
    pattern: str
    placeholder: str
    readOnly: bool
    required: bool
    size: int
    src: str
    step: Union[int, str]
    type: HTMLInputType
    value: Union[str, List[str], int]
    width: Union[int, str]


class HTMLKeygenProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    challenge: str
    disabled: bool
    form: str
    keyType: str
    keyParams: str
    name: str


class HTMLLabelProps(BaseHTMLProps, DOMEvents[HTMLLabelElement], total=False):
    form: str
    htmlFor: str


class HTMLLiProps(BaseHTMLProps, DOMEvents[HTMLLiElement], total=False):
    value: Union[str, List[str], int]


class HTMLLinkProps(BaseHTMLProps, DOMEvents[HTMLLinkElement], total=False):
    href: str
    as_: str
    crossOrigin: CrossOrigin
    fetchPriority: Literal["high", "low", "auto"]
    hrefLang: str
    integrity: str
    media: str
    imageSrcSet: str
    imageSizes: str
    referrerPolicy: HTMLAttributeReferrerPolicy
    sizes: str
    type: str
    charSet: str
    precedence: str


class HTMLMapProps(BaseHTMLProps, DOMEvents[HTMLMapElement], total=False):
    name: str


class HTMLMenuProps(BaseHTMLProps, DOMEvents[HTMLMenuElement], total=False):
    type: str


class HTMLMediaProps(BaseHTMLProps, DOMEvents[HTMLMediaElement], total=False):
    autoPlay: bool
    controls: bool
    controlsList: str
    crossOrigin: CrossOrigin
    loop: bool
    mediaGroup: str
    muted: bool
    playsInline: bool
    preload: str
    src: str


# Note: not alphabetical order due to inheritance
class HTMLAudioProps(HTMLMediaProps, total=False):
    pass


class HTMLMetaProps(BaseHTMLProps, DOMEvents[HTMLMetaElement], total=False):
    charSet: str
    content: str
    httpEquiv: str
    media: str
    name: str


class HTMLMeterProps(BaseHTMLProps, DOMEvents[HTMLMeterElement], total=False):
    form: str
    high: int
    low: int
    max: Union[int, str]
    min: Union[int, str]
    optimum: int
    value: Union[str, List[str], int]


class HTMLQuoteProps(BaseHTMLProps, DOMEvents[HTMLQuoteElement], total=False):
    cite: str


class HTMLObjectProps(BaseHTMLProps, DOMEvents[HTMLObjectElement], total=False):
    classId: str
    data: str
    form: str
    height: Union[int, str]
    name: str
    type: str
    useMap: str
    width: Union[int, str]
    wmode: str


class HTMLOlProps(BaseHTMLProps, DOMEvents[HTMLOListElement], total=False):
    reversed: bool
    start: int
    type: Literal["1", "a", "A", "i", "I"]


class HTMLOptgroupProps(BaseHTMLProps, DOMEvents[HTMLOptGroupElement], total=False):
    disabled: bool
    label: str


class HTMLOptionProps(BaseHTMLProps, DOMEvents[HTMLOptionElement], total=False):
    disabled: bool
    label: str
    selected: bool
    value: Union[str, List[str], int]


class HTMLOutputProps(BaseHTMLProps, DOMEvents[HTMLOutputElement], total=False):
    form: str
    htmlFor: str
    name: str


class HTMLParamProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    name: str
    value: Union[str, List[str], int]


class HTMLProgressProps(BaseHTMLProps, DOMEvents[HTMLProgressElement], total=False):
    max: Union[int, str]
    value: Union[str, List[str], int]


class HTMLSlotProps(BaseHTMLProps, DOMEvents[HTMLSlotElement], total=False):
    name: str


class HTMLScriptProps(BaseHTMLProps, DOMEvents[HTMLScriptElement], total=False):
    async_: bool
    charSet: str  # deprecated
    crossOrigin: CrossOrigin
    defer: bool
    integrity: str
    noModule: bool
    referrerPolicy: HTMLAttributeReferrerPolicy
    src: str
    type: str


class HTMLSelectProps(BaseHTMLProps, SelectDOMEvents, total=False):
    autoComplete: str
    disabled: bool
    form: str
    multiple: bool
    name: str
    required: bool
    size: int
    value: Union[str, List[str], int]


class HTMLSourceProps(BaseHTMLProps, DOMEvents[HTMLSourceElement], total=False):
    height: Union[int, str]
    media: str
    sizes: str
    src: str
    srcSet: str
    type: str
    width: Union[int, str]


class HTMLStyleProps(BaseHTMLProps, DOMEvents[HTMLStyleElement], total=False):
    media: str
    scoped: bool
    type: str
    href: str
    precedence: str


class HTMLTableProps(BaseHTMLProps, DOMEvents[HTMLTableElement], total=False):
    align: Literal["left", "center", "right"]
    bgcolor: str
    border: int
    cellPadding: Union[int, str]
    cellSpacing: Union[int, str]
    frame: bool
    rules: Literal["none", "groups", "rows", "columns", "all"]
    summary: str
    width: Union[int, str]


class HTMLTextareaProps(BaseHTMLProps, TextAreaDOMEvents, total=False):
    autoComplete: str
    cols: int
    dirName: str
    disabled: bool
    form: str
    maxLength: int
    minLength: int
    name: str
    placeholder: str
    readOnly: bool
    required: bool
    rows: int
    value: Union[str, List[str], int]
    wrap: str


class HTMLTdProps(BaseHTMLProps, DOMEvents[HTMLTableCellElement], total=False):
    align: Literal["left", "center", "right", "justify", "char"]
    colSpan: int
    headers: str
    rowSpan: int
    scope: str
    abbr: str
    height: Union[int, str]
    width: Union[int, str]
    valign: Literal["top", "middle", "bottom", "baseline"]


class HTMLThProps(BaseHTMLProps, DOMEvents[HTMLTableCellElement], total=False):
    align: Literal["left", "center", "right", "justify", "char"]
    colSpan: int
    headers: str
    rowSpan: int
    scope: str
    abbr: str


class HTMLTimeProps(BaseHTMLProps, DOMEvents[HTMLTimeElement], total=False):
    dateTime: str


class HTMLTrackProps(BaseHTMLProps, DOMEvents[HTMLTrackElement], total=False):
    default: bool
    kind: str
    label: str
    src: str
    srcLang: str


class HTMLVideoProps(HTMLMediaProps, total=False):
    height: Union[int, str]
    playsInline: bool
    poster: str
    width: Union[int, str]
    disablePictureInPicture: bool
    disableRemotePlayback: bool


class HTMLSVGProps(DOMEvents[TElement], total=False):
    """SVG attributes supported by React (subset placeholder).

    Note: Full SVG attribute surface is large; extend as needed.
    """

    # React-specific attributes
    suppressHydrationWarning: bool

    # Shared with HTMLAttributes
    className: str  # type: ignore
    color: str
    height: Union[int, str]
    id: str  # type: ignore
    lang: str
    max: Union[int, str]
    media: str
    method: str
    min: Union[int, str]
    name: str
    style: CSSProperties
    target: str
    type: str
    width: Union[int, str]

    # Other HTML properties
    role: str
    tabIndex: int
    crossOrigin: str

    # SVG specific attributes
    accentHeight: Union[int, str]
    accumulate: Literal["none", "sum"]
    additive: Literal["replace", "sum"]
    alignmentBaseline: Literal[
        "auto",
        "baseline",
        "before-edge",
        "text-before-edge",
        "middle",
        "central",
        "after-edge",
        "text-after-edge",
        "ideographic",
        "alphabetic",
        "hanging",
        "mathematical",
        "inherit",
    ]

    allowReorder: Literal["no", "yes"]
    alphabetic: Union[int, str]
    amplitude: Union[int, str]
    arabicForm: Literal["initial", "medial", "terminal", "isolated"]
    ascent: Union[int, str]
    attributeName: str
    attributeType: str
    autoReverse: bool
    azimuth: Union[int, str]
    baseFrequency: Union[int, str]
    baselineShift: Union[int, str]
    baseProfile: Union[int, str]
    bbox: Union[int, str]
    begin: Union[int, str]
    bias: Union[int, str]
    by: Union[int, str]
    calcMode: Union[int, str]
    capHeight: Union[int, str]
    clip: Union[int, str]
    clipPath: str
    clipPathUnits: Union[int, str]
    clipRule: Union[int, str]
    colorInterpolation: Union[int, str]
    colorInterpolationFilters: Literal["auto", "sRGB", "linearRGB", "inherit"]
    colorProfile: Union[int, str]
    colorRendering: Union[int, str]
    contentScriptType: Union[int, str]
    contentStyleType: Union[int, str]
    cursor: Union[int, str]
    cx: Union[int, str]
    cy: Union[int, str]
    d: str
    decelerate: Union[int, str]
    descent: Union[int, str]
    diffuseConstant: Union[int, str]
    direction: Union[int, str]
    display: Union[int, str]
    divisor: Union[int, str]
    dominantBaseline: Union[int, str]
    dur: Union[int, str]
    dx: Union[int, str]
    dy: Union[int, str]
    edgeMode: Union[int, str]
    elevation: Union[int, str]
    enableBackground: Union[int, str]
    end: Union[int, str]
    exponent: Union[int, str]
    externalResourcesRequired: bool
    fill: str
    fillOpacity: Union[int, str]
    fillRule: Literal["nonzero", "evenodd", "inherit"]
    filter: str
    filterRes: Union[int, str]
    filterUnits: Union[int, str]
    floodColor: Union[int, str]
    floodOpacity: Union[int, str]
    focusable: Union[bool, Literal["auto"]]
    fontFamily: str
    fontSize: Union[int, str]
    fontSizeAdjust: Union[int, str]
    fontStretch: Union[int, str]
    fontStyle: Union[int, str]
    fontVariant: Union[int, str]
    fontWeight: Union[int, str]
    format: Union[int, str]
    fr: Union[int, str]
    from_: Union[int, str]
    fx: Union[int, str]
    fy: Union[int, str]
    g1: Union[int, str]
    g2: Union[int, str]
    glyphName: Union[int, str]
    glyphOrientationHorizontal: Union[int, str]
    glyphOrientationVertical: Union[int, str]
    glyphRef: Union[int, str]
    gradientTransform: str
    gradientUnits: str
    hanging: Union[int, str]
    horizAdvX: Union[int, str]
    horizOriginX: Union[int, str]
    href: str
    ideographic: Union[int, str]
    imageRendering: Union[int, str]
    in2: Union[int, str]
    in_: str
    intercept: Union[int, str]
    k1: Union[int, str]
    k2: Union[int, str]
    k3: Union[int, str]
    k4: Union[int, str]
    k: Union[int, str]
    kernelMatrix: Union[int, str]
    kernelUnitLength: Union[int, str]
    kerning: Union[int, str]
    keyPoints: Union[int, str]
    keySplines: Union[int, str]
    keyTimes: Union[int, str]
    lengthAdjust: Union[int, str]
    letterSpacing: Union[int, str]
    lightingColor: Union[int, str]
    limitingConeAngle: Union[int, str]
    local: Union[int, str]
    markerEnd: str
    markerHeight: Union[int, str]
    markerMid: str
    markerStart: str
    markerUnits: Union[int, str]
    markerWidth: Union[int, str]
    mask: str
    maskContentUnits: Union[int, str]
    maskUnits: Union[int, str]
    mathematical: Union[int, str]
    mode: Union[int, str]
    numOctaves: Union[int, str]
    offset: Union[int, str]
    opacity: Union[int, str]
    operator: Union[int, str]
    order: Union[int, str]
    orient: Union[int, str]
    orientation: Union[int, str]
    origin: Union[int, str]
    overflow: Union[int, str]
    overlinePosition: Union[int, str]
    overlineThickness: Union[int, str]
    paintOrder: Union[int, str]
    panose1: Union[int, str]
    path: str
    pathLength: Union[int, str]
    patternContentUnits: str
    patternTransform: Union[int, str]
    patternUnits: str
    pointerEvents: Union[int, str]
    points: str
    pointsAtX: Union[int, str]
    pointsAtY: Union[int, str]
    pointsAtZ: Union[int, str]
    preserveAlpha: bool
    preserveAspectRatio: str
    primitiveUnits: Union[int, str]
    r: Union[int, str]
    radius: Union[int, str]
    refX: Union[int, str]
    refY: Union[int, str]
    renderingIntent: Union[int, str]
    repeatCount: Union[int, str]
    repeatDur: Union[int, str]
    requiredExtensions: Union[int, str]
    requiredFeatures: Union[int, str]
    restart: Union[int, str]
    result: str
    rotate: Union[int, str]
    rx: Union[int, str]
    ry: Union[int, str]
    scale: Union[int, str]
    seed: Union[int, str]
    shapeRendering: Union[int, str]
    slope: Union[int, str]
    spacing: Union[int, str]
    specularConstant: Union[int, str]
    specularExponent: Union[int, str]
    speed: Union[int, str]
    spreadMethod: str
    startOffset: Union[int, str]
    stdDeviation: Union[int, str]
    stemh: Union[int, str]
    stemv: Union[int, str]
    stitchTiles: Union[int, str]
    stopColor: str
    stopOpacity: Union[int, str]
    strikethroughPosition: Union[int, str]
    strikethroughThickness: Union[int, str]
    string: Union[int, str]
    stroke: str
    strokeDasharray: Union[int, str]
    strokeDashoffset: Union[int, str]
    strokeLinecap: Literal["butt", "round", "square", "inherit"]
    strokeLinejoin: Literal["miter", "round", "bevel", "inherit"]
    strokeMiterlimit: Union[int, str]
    strokeOpacity: Union[int, str]
    strokeWidth: Union[int, str]
    surfaceScale: Union[int, str]
    systemLanguage: Union[int, str]
    tableValues: Union[int, str]
    targetX: Union[int, str]
    targetY: Union[int, str]
    textAnchor: str
    textDecoration: Union[int, str]
    textLength: Union[int, str]
    textRendering: Union[int, str]
    to: Union[int, str]
    transform: str
    u1: Union[int, str]
    u2: Union[int, str]
    underlinePosition: Union[int, str]
    underlineThickness: Union[int, str]
    unicode: Union[int, str]
    unicodeBidi: Union[int, str]
    unicodeRange: Union[int, str]
    unitsPerEm: Union[int, str]
    vAlphabetic: Union[int, str]
    values: str
    vectorEffect: Union[int, str]
    version: str
    vertAdvY: Union[int, str]
    vertOriginX: Union[int, str]
    vertOriginY: Union[int, str]
    vHanging: Union[int, str]
    vIdeographic: Union[int, str]
    viewBox: str
    viewTarget: Union[int, str]
    visibility: Union[int, str]
    vMathematical: Union[int, str]
    widths: Union[int, str]
    wordSpacing: Union[int, str]
    writingMode: Union[int, str]
    x1: Union[int, str]
    x2: Union[int, str]
    x: Union[int, str]
    xChannelSelector: str
    xHeight: Union[int, str]
    xlinkActuate: str
    xlinkArcrole: str
    xlinkHref: str
    xlinkRole: str
    xlinkShow: str
    xlinkTitle: str
    xlinkType: str
    xmlBase: str
    xmlLang: str
    xmlns: str
    xmlnsXlink: str
    xmlSpace: str
    y1: Union[int, str]
    y2: Union[int, str]
    y: Union[int, str]
    yChannelSelector: str
    z: Union[int, str]
    zoomAndPan: str


# Basic HTML element props that inherit from HTMLElementBase
class HTMLAbbrProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLAddressProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLArticleProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLAsideProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLBProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLBDIProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLBDOProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLBodyProps(BaseHTMLProps, DOMEvents[HTMLBodyElement], total=False):
    pass


class HTMLCaptionProps(BaseHTMLProps, DOMEvents[HTMLTableCaptionElement], total=False):
    pass


class HTMLCiteProps(BaseHTMLProps, DOMEvents[HTMLCiteElement], total=False):
    pass


class HTMLCodeProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLDatalistProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLDDProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLDFNProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLDivProps(BaseHTMLProps, DOMEvents[HTMLDivElement], total=False):
    pass


class HTMLDLProps(BaseHTMLProps, DOMEvents[HTMLDListElement], total=False):
    pass


class HTMLDTProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLEMProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLFigcaptionProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLFigureProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLFooterProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLH1Props(BaseHTMLProps, DOMEvents[HTMLHeadingElement], total=False):
    pass


class HTMLH2Props(BaseHTMLProps, DOMEvents[HTMLHeadingElement], total=False):
    pass


class HTMLH3Props(BaseHTMLProps, DOMEvents[HTMLHeadingElement], total=False):
    pass


class HTMLH4Props(BaseHTMLProps, DOMEvents[HTMLHeadingElement], total=False):
    pass


class HTMLH5Props(BaseHTMLProps, DOMEvents[HTMLHeadingElement], total=False):
    pass


class HTMLH6Props(BaseHTMLProps, DOMEvents[HTMLHeadingElement], total=False):
    pass


class HTMLHeadProps(BaseHTMLProps, DOMEvents[HTMLHeadElement], total=False):
    pass


class HTMLHeaderProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLHgroupProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLIProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLKBDProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLLegendProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLMainProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLMarkProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLNavProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLNoscriptProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLPProps(BaseHTMLProps, DOMEvents[HTMLParagraphElement], total=False):
    pass


class HTMLPictureProps(BaseHTMLProps, DOMEvents[HTMLPictureElement], total=False):
    pass


class HTMLPreProps(BaseHTMLProps, DOMEvents[HTMLPreElement], total=False):
    pass


class HTMLQProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLRPProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLRTProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLRubyProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSampProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSectionProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSmallProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSpanProps(BaseHTMLProps, DOMEvents[HTMLSpanElement], total=False):
    pass


class HTMLStrongProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSubProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSummaryProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLSupProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLTBODYProps(BaseHTMLProps, DOMEvents[HTMLTableSectionElement], total=False):
    pass


class HTMLTemplateProps(BaseHTMLProps, DOMEvents[HTMLTemplateElement], total=False):
    pass


class HTMLTitleProps(BaseHTMLProps, DOMEvents[HTMLTitleElement], total=False):
    pass


class HTMLUProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLULProps(BaseHTMLProps, DOMEvents[HTMLUListElement], total=False):
    pass


class HTMLVarProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


# Self-closing elements
class HTMLBRProps(BaseHTMLProps, DOMEvents[HTMLBRElement], total=False):
    pass


class HTMLHRProps(BaseHTMLProps, DOMEvents[HTMLHRElement], total=False):
    pass


class HTMLWBRProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


# Fragment and SVG elements
class HTMLFragmentProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLCircleProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLEllipseProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLGProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLLineProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLPathProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLPolygonProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLPolylineProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLRectProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLTextProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLTspanProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLDefsProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLClipPathProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLMaskProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLPatternProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class HTMLUseProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
    pass


class WebViewAttributes(BaseHTMLProps):
    allowFullScreen: bool
    allowpopups: bool
    autosize: bool
    blinkfeatures: str
    disableblinkfeatures: str
    disableguestresize: bool
    disablewebsecurity: bool
    guestinstance: str
    httpreferrer: str
    nodeintegration: bool
    partition: str
    plugins: bool
    preload: str
    src: str
    useragent: str
    webpreferences: str
