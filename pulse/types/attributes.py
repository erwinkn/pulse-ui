# Adapted from @types/react 19.0
# NOT the same thing as the properties in `elements.py` (but very similar)
from typing import Any, Dict, List, Literal, Union, TypedDict

from pulse.types.elements import (  # noqa: F401
    GenericHTMLElement,
    HTMLAnchorElement,
    HTMLAreaElement,
    HTMLAudioElement,
    HTMLBaseElement,
    HTMLButtonElement,
    HTMLCiteElement,
    HTMLDataElement,
    HTMLDetailsElement,
    HTMLDialogElement,
    HTMLEmbedElement,
    HTMLFieldSetElement,
    HTMLFormElement,
    HTMLHeadElement,
    HTMLHtmlElement,
    HTMLIFrameElement,
    HTMLImageElement,
    HTMLInputElement,
    HTMLLabelElement,
    HTMLLiElement,
    HTMLLinkElement,
    HTMLMapElement,
    HTMLMenuElement,
    HTMLMediaElement,
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
from pulse.types.events import (
    DOMEvents,
    DialogDOMEvents,
    InputDOMEvents,
    SelectDOMEvents,
    TextAreaDOMEvents,
)

Booleanish = Literal[True, False, "true", "false"]
CrossOrigin = Literal["anonymous", "use-credentials", ""] | None


class BaseHTMLProps(TypedDict, total=False):
    # React-specific Attributes
    default_checked: bool
    default_value: Union[str, int, List[str]]
    suppress_content_editable_warning: bool
    suppress_hydration_warning: bool

    # Standard HTML Attributes
    access_key: str
    auto_capitalize: Literal["off", "none", "on", "sentences", "words", "characters"]
    auto_focus: bool
    class_name: str
    content_editable: Union[Booleanish, Literal["inherit", "plaintext-only"]]
    context_menu: str
    dir: str
    draggable: Booleanish
    enter_key_hint: Literal["enter", "done", "go", "next", "previous", "search", "send"]
    hidden: bool
    id: str
    lang: str
    nonce: str
    slot: str
    spell_check: Booleanish
    style: Dict[str, Any]
    tab_index: int
    title: str
    translate: Literal["yes", "no"]

    # Unknown
    radio_group: str  # <command>, <menuitem>

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
    auto_correct: str
    auto_save: str
    color: str
    item_prop: str
    item_scope: bool
    item_type: str
    item_id: str
    item_ref: str
    results: int
    security: str
    unselectable: Literal["on", "off"]

    # Popover API
    popover: Literal["", "auto", "manual"]
    popover_target_action: Literal["toggle", "show", "hide"]
    popover_target: str

    # Living Standard
    # https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/inert
    inert: bool
    # Hints at the type of data that might be entered by the user while editing the element or its contents
    # https://html.spec.whatwg.org/multipage/interaction.html#input-modalities:-the-inputmode-attribute
    input_mode: Literal[
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
    referrer_policy: HTMLAttributeReferrerPolicy


class HTMLAreaProps(BaseHTMLProps, DOMEvents[HTMLAreaElement], total=False):
    alt: str
    coords: str
    download: str
    href: str
    href_lang: str
    media: str
    referrer_policy: HTMLAttributeReferrerPolicy
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
    form_action: str
    form_enc_type: str
    form_method: str
    form_no_validate: bool
    form_target: str
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
    date_time: str


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
    accept_charset: str
    # NOTE: support action callbacks?
    action: str
    auto_complete: str
    enc_type: str
    method: str
    name: str
    no_validate: bool
    target: str


class HTMLHtmlProps(BaseHTMLProps, DOMEvents[HTMLHtmlElement], total=False):
    manifest: str


class HTMLIframeProps(BaseHTMLProps, DOMEvents[HTMLIFrameElement], total=False):
    allow: str
    allow_full_screen: bool
    allow_transparency: bool
    frame_border: Union[int, str]
    height: Union[int, str]
    loading: Literal["eager", "lazy"]
    margin_height: int
    margin_width: int
    name: str
    referrer_policy: HTMLAttributeReferrerPolicy
    sandbox: str
    scrolling: str
    seamless: bool
    src: str
    src_doc: str
    width: Union[int, str]


class HTMLImgProps(BaseHTMLProps, DOMEvents[HTMLImageElement], total=False):
    alt: str
    cross_origin: CrossOrigin
    decoding: Literal["async", "auto", "sync"]
    fetch_priority: Literal["high", "low", "auto"]
    height: Union[int, str]
    loading: Literal["eager", "lazy"]
    referrer_policy: HTMLAttributeReferrerPolicy
    sizes: str
    src: str
    src_set: str
    use_map: str
    width: Union[int, str]


class HTMLInsProps(BaseHTMLProps, DOMEvents[HTMLModElement], total=False):
    cite: str
    date_time: str


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
    auto_complete: str  # HTMLInputAutoCompleteAttribute
    capture: Union[bool, Literal["user", "environment"]]
    checked: bool
    disabled: bool
    form: str
    form_action: str
    form_enc_type: str
    form_method: str
    form_no_validate: bool
    form_target: str
    height: Union[int, str]
    list: str
    max: Union[int, str]
    max_length: int
    min: Union[int, str]
    min_length: int
    multiple: bool
    name: str
    pattern: str
    placeholder: str
    read_only: bool
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
    key_type: str
    key_params: str
    name: str


class HTMLLabelProps(BaseHTMLProps, DOMEvents[HTMLLabelElement], total=False):
    form: str
    html_for: str


class HTMLLiProps(BaseHTMLProps, DOMEvents[HTMLLiElement], total=False):
    value: Union[str, List[str], int]


class HTMLLinkProps(BaseHTMLProps, DOMEvents[HTMLLinkElement], total=False):
    href: str
    as_: str
    cross_origin: CrossOrigin
    fetch_priority: Literal["high", "low", "auto"]
    href_lang: str
    integrity: str
    media: str
    image_src_set: str
    image_sizes: str
    referrer_policy: HTMLAttributeReferrerPolicy
    sizes: str
    type: str
    char_set: str
    precedence: str


class HTMLMapProps(BaseHTMLProps, DOMEvents[HTMLMapElement], total=False):
    name: str


class HTMLMenuProps(BaseHTMLProps, DOMEvents[HTMLMenuElement], total=False):
    type: str


class HTMLMediaProps(BaseHTMLProps, DOMEvents[HTMLMediaElement], total=False):
    auto_play: bool
    controls: bool
    controls_list: str
    cross_origin: CrossOrigin
    loop: bool
    media_group: str
    muted: bool
    plays_inline: bool
    preload: str
    src: str


# Note: not alphabetical order due to inheritance
class HTMLAudioProps(HTMLMediaProps, total=False):
    pass


class HTMLMetaProps(BaseHTMLProps, DOMEvents[HTMLMetaElement], total=False):
    char_set: str
    content: str
    http_equiv: str
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
    class_id: str
    data: str
    form: str
    height: Union[int, str]
    name: str
    type: str
    use_map: str
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
    html_for: str
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
    char_set: str  # deprecated
    cross_origin: CrossOrigin
    defer: bool
    integrity: str
    no_module: bool
    referrer_policy: HTMLAttributeReferrerPolicy
    src: str
    type: str


class HTMLSelectProps(BaseHTMLProps, SelectDOMEvents, total=False):
    auto_complete: str
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
    src_set: str
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
    cell_padding: Union[int, str]
    cell_spacing: Union[int, str]
    frame: bool
    rules: Literal["none", "groups", "rows", "columns", "all"]
    summary: str
    width: Union[int, str]


class HTMLTextareaProps(BaseHTMLProps, TextAreaDOMEvents, total=False):
    auto_complete: str
    cols: int
    dir_name: str
    disabled: bool
    form: str
    max_length: int
    min_length: int
    name: str
    placeholder: str
    read_only: bool
    required: bool
    rows: int
    value: Union[str, List[str], int]
    wrap: str


class HTMLTdProps(BaseHTMLProps, DOMEvents[HTMLTableCellElement], total=False):
    align: Literal["left", "center", "right", "justify", "char"]
    col_span: int
    headers: str
    row_span: int
    scope: str
    abbr: str
    height: Union[int, str]
    width: Union[int, str]
    valign: Literal["top", "middle", "bottom", "baseline"]


class HTMLThProps(BaseHTMLProps, DOMEvents[HTMLTableCellElement], total=False):
    align: Literal["left", "center", "right", "justify", "char"]
    col_span: int
    headers: str
    row_span: int
    scope: str
    abbr: str


class HTMLTimeProps(BaseHTMLProps, DOMEvents[HTMLTimeElement], total=False):
    date_time: str


class HTMLTrackProps(BaseHTMLProps, DOMEvents[HTMLTrackElement], total=False):
    default: bool
    kind: str
    label: str
    src: str
    src_lang: str


class HTMLVideoProps(HTMLMediaProps, total=False):
    height: Union[int, str]
    plays_inline: bool
    poster: str
    width: Union[int, str]
    disable_picture_in_picture: bool
    disable_remote_playback: bool


class HTMLSVGProps(TypedDict, total=False):
    """SVG attributes supported by React (subset placeholder).

    Note: Full SVG attribute surface is large; extend as needed.
    """

    # React-specific attributes
    suppress_hydration_warning: bool

    # Shared with HTMLAttributes
    class_name: str  # type: ignore
    color: str
    height: Union[int, str]
    id: str  # type: ignore
    lang: str
    max: Union[int, str]
    media: str
    method: str
    min: Union[int, str]
    name: str
    style: Dict[str, Any]  # type: ignore
    target: str
    type: str
    width: Union[int, str]

    # Other HTML properties
    role: str
    tab_index: int
    cross_origin: str

    # SVG specific attributes
    accent_height: Union[int, str]
    accumulate: Literal["none", "sum"]
    additive: Literal["replace", "sum"]
    alignment_baseline: Literal[
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

    allow_reorder: Literal["no", "yes"]
    alphabetic: Union[int, str]
    amplitude: Union[int, str]
    arabic_form: Literal["initial", "medial", "terminal", "isolated"]
    ascent: Union[int, str]
    attribute_name: str
    attribute_type: str
    auto_reverse: bool
    azimuth: Union[int, str]
    base_frequency: Union[int, str]
    baseline_shift: Union[int, str]
    base_profile: Union[int, str]
    bbox: Union[int, str]
    begin: Union[int, str]
    bias: Union[int, str]
    by: Union[int, str]
    calc_mode: Union[int, str]
    cap_height: Union[int, str]
    clip: Union[int, str]
    clip_path: str
    clip_path_units: Union[int, str]
    clip_rule: Union[int, str]
    color_interpolation: Union[int, str]
    color_interpolation_filters: Literal["auto", "sRGB", "linearRGB", "inherit"]
    color_profile: Union[int, str]
    color_rendering: Union[int, str]
    content_script_type: Union[int, str]
    content_style_type: Union[int, str]
    cursor: Union[int, str]
    cx: Union[int, str]
    cy: Union[int, str]
    d: str
    decelerate: Union[int, str]
    descent: Union[int, str]
    diffuse_constant: Union[int, str]
    direction: Union[int, str]
    display: Union[int, str]
    divisor: Union[int, str]
    dominant_baseline: Union[int, str]
    dur: Union[int, str]
    dx: Union[int, str]
    dy: Union[int, str]
    edge_mode: Union[int, str]
    elevation: Union[int, str]
    enable_background: Union[int, str]
    end: Union[int, str]
    exponent: Union[int, str]
    external_resources_required: bool
    fill: str
    fill_opacity: Union[int, str]
    fill_rule: Literal["nonzero", "evenodd", "inherit"]
    filter: str
    filter_res: Union[int, str]
    filter_units: Union[int, str]
    flood_color: Union[int, str]
    flood_opacity: Union[int, str]
    focusable: Union[bool, Literal["auto"]]
    font_family: str
    font_size: Union[int, str]
    font_size_adjust: Union[int, str]
    font_stretch: Union[int, str]
    font_style: Union[int, str]
    font_variant: Union[int, str]
    font_weight: Union[int, str]
    format: Union[int, str]
    fr: Union[int, str]
    from_: Union[int, str]
    fx: Union[int, str]
    fy: Union[int, str]
    g1: Union[int, str]
    g2: Union[int, str]
    glyph_name: Union[int, str]
    glyph_orientation_horizontal: Union[int, str]
    glyph_orientation_vertical: Union[int, str]
    glyph_ref: Union[int, str]
    gradient_transform: str
    gradient_units: str
    hanging: Union[int, str]
    horiz_adv_x: Union[int, str]
    horiz_origin_x: Union[int, str]
    href: str
    ideographic: Union[int, str]
    image_rendering: Union[int, str]
    in2: Union[int, str]
    in_: str
    intercept: Union[int, str]
    k1: Union[int, str]
    k2: Union[int, str]
    k3: Union[int, str]
    k4: Union[int, str]
    k: Union[int, str]
    kernel_matrix: Union[int, str]
    kernel_unit_length: Union[int, str]
    kerning: Union[int, str]
    key_points: Union[int, str]
    key_splines: Union[int, str]
    key_times: Union[int, str]
    length_adjust: Union[int, str]
    letter_spacing: Union[int, str]
    lighting_color: Union[int, str]
    limiting_cone_angle: Union[int, str]
    local: Union[int, str]
    marker_end: str
    marker_height: Union[int, str]
    marker_mid: str
    marker_start: str
    marker_units: Union[int, str]
    marker_width: Union[int, str]
    mask: str
    mask_content_units: Union[int, str]
    mask_units: Union[int, str]
    mathematical: Union[int, str]
    mode: Union[int, str]
    num_octaves: Union[int, str]
    offset: Union[int, str]
    opacity: Union[int, str]
    operator: Union[int, str]
    order: Union[int, str]
    orient: Union[int, str]
    orientation: Union[int, str]
    origin: Union[int, str]
    overflow: Union[int, str]
    overline_position: Union[int, str]
    overline_thickness: Union[int, str]
    paint_order: Union[int, str]
    panose1: Union[int, str]
    path: str
    path_length: Union[int, str]
    pattern_content_units: str
    pattern_transform: Union[int, str]
    pattern_units: str
    pointer_events: Union[int, str]
    points: str
    points_at_x: Union[int, str]
    points_at_y: Union[int, str]
    points_at_z: Union[int, str]
    preserve_alpha: bool
    preserve_aspect_ratio: str
    primitive_units: Union[int, str]
    r: Union[int, str]
    radius: Union[int, str]
    ref_x: Union[int, str]
    ref_y: Union[int, str]
    rendering_intent: Union[int, str]
    repeat_count: Union[int, str]
    repeat_dur: Union[int, str]
    required_extensions: Union[int, str]
    required_features: Union[int, str]
    restart: Union[int, str]
    result: str
    rotate: Union[int, str]
    rx: Union[int, str]
    ry: Union[int, str]
    scale: Union[int, str]
    seed: Union[int, str]
    shape_rendering: Union[int, str]
    slope: Union[int, str]
    spacing: Union[int, str]
    specular_constant: Union[int, str]
    specular_exponent: Union[int, str]
    speed: Union[int, str]
    spread_method: str
    start_offset: Union[int, str]
    std_deviation: Union[int, str]
    stemh: Union[int, str]
    stemv: Union[int, str]
    stitch_tiles: Union[int, str]
    stop_color: str
    stop_opacity: Union[int, str]
    strikethrough_position: Union[int, str]
    strikethrough_thickness: Union[int, str]
    string: Union[int, str]
    stroke: str
    stroke_dasharray: Union[int, str]
    stroke_dashoffset: Union[int, str]
    stroke_linecap: Literal["butt", "round", "square", "inherit"]
    stroke_linejoin: Literal["miter", "round", "bevel", "inherit"]
    stroke_miterlimit: Union[int, str]
    stroke_opacity: Union[int, str]
    stroke_width: Union[int, str]
    surface_scale: Union[int, str]
    system_language: Union[int, str]
    table_values: Union[int, str]
    target_x: Union[int, str]
    target_y: Union[int, str]
    text_anchor: str
    text_decoration: Union[int, str]
    text_length: Union[int, str]
    text_rendering: Union[int, str]
    to: Union[int, str]
    transform: str
    u1: Union[int, str]
    u2: Union[int, str]
    underline_position: Union[int, str]
    underline_thickness: Union[int, str]
    unicode: Union[int, str]
    unicode_bidi: Union[int, str]
    unicode_range: Union[int, str]
    units_per_em: Union[int, str]
    v_alphabetic: Union[int, str]
    values: str
    vector_effect: Union[int, str]
    version: str
    vert_adv_y: Union[int, str]
    vert_origin_x: Union[int, str]
    vert_origin_y: Union[int, str]
    v_hanging: Union[int, str]
    v_ideographic: Union[int, str]
    view_box: str
    view_target: Union[int, str]
    visibility: Union[int, str]
    v_mathematical: Union[int, str]
    widths: Union[int, str]
    word_spacing: Union[int, str]
    writing_mode: Union[int, str]
    x1: Union[int, str]
    x2: Union[int, str]
    x: Union[int, str]
    x_channel_selector: str
    x_height: Union[int, str]
    xlink_actuate: str
    xlink_arcrole: str
    xlink_href: str
    xlink_role: str
    xlink_show: str
    xlink_title: str
    xlink_type: str
    xml_base: str
    xml_lang: str
    xmlns: str
    xmlns_xlink: str
    xml_space: str
    y1: Union[int, str]
    y2: Union[int, str]
    y: Union[int, str]
    y_channel_selector: str
    z: Union[int, str]
    zoom_and_pan: str


class WebViewAttributes(BaseHTMLProps):
    allow_full_screen: bool
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
