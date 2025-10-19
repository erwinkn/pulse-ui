# Adapted from @types/react 19.0
# NOT the same thing as the properties in `elements.py` (but very similar)
from typing import Any, Literal, TypedDict

from pulse.css import CssReference
from pulse.helpers import CSSProperties
from pulse.html.elements import (
	GenericHTMLElement,
	HTMLAnchorElement,
	HTMLAreaElement,
	HTMLBaseElement,
	HTMLBodyElement,
	HTMLBRElement,
	HTMLButtonElement,
	HTMLCiteElement,
	HTMLDataElement,
	HTMLDetailsElement,
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
	HTMLSlotElement,
	HTMLSourceElement,
	HTMLSpanElement,
	HTMLStyleElement,
	HTMLTableCaptionElement,
	HTMLTableCellElement,
	HTMLTableColElement,
	HTMLTableElement,
	HTMLTableSectionElement,
	HTMLTemplateElement,
	HTMLTimeElement,
	HTMLTitleElement,
	HTMLTrackElement,
	HTMLUListElement,
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
	defaultValue: str | int | list[str]
	suppressContentEditableWarning: bool
	suppressHydrationWarning: bool

	# Standard HTML Attributes
	accessKey: str
	autoCapitalize: Literal["off", "none", "on", "sentences", "words", "characters"]
	autoFocus: bool
	className: ClassName
	contentEditable: Booleanish | Literal["inherit", "plaintext-only"]
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
	value: str | list[str] | int


class HTMLCanvasProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
	height: int | str
	width: int | str


class HTMLColProps(BaseHTMLProps, DOMEvents[HTMLTableColElement], total=False):
	span: int
	width: int | str


class HTMLColgroupProps(BaseHTMLProps, DOMEvents[HTMLTableColElement], total=False):
	span: int


class HTMLDataProps(BaseHTMLProps, DOMEvents[HTMLDataElement], total=False):
	value: str | list[str] | int


class HTMLDetailsProps(BaseHTMLProps, DOMEvents[HTMLDetailsElement], total=False):
	open: bool
	name: str


class HTMLDelProps(BaseHTMLProps, DOMEvents[HTMLModElement], total=False):
	cite: str
	dateTime: str


class HTMLDialogProps(BaseHTMLProps, DialogDOMEvents, total=False):
	open: bool


class HTMLEmbedProps(BaseHTMLProps, DOMEvents[HTMLEmbedElement], total=False):
	height: int | str
	src: str
	type: str
	width: int | str


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
	frameBorder: int | str
	height: int | str
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
	width: int | str


class HTMLImgProps(BaseHTMLProps, DOMEvents[HTMLImageElement], total=False):
	alt: str
	crossOrigin: CrossOrigin
	decoding: Literal["async", "auto", "sync"]
	fetchPriority: Literal["high", "low", "auto"]
	height: int | str
	loading: Literal["eager", "lazy"]
	referrerPolicy: HTMLAttributeReferrerPolicy
	sizes: str
	src: str
	srcSet: str
	useMap: str
	width: int | str


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
	capture: bool | Literal["user", "environment"]
	checked: bool
	disabled: bool
	form: str
	formAction: str
	formEncType: str
	formMethod: str
	formNoValidate: bool
	formTarget: str
	height: int | str
	list: str
	max: int | str
	maxLength: int
	min: int | str
	minLength: int
	multiple: bool
	name: str
	pattern: str
	placeholder: str
	readOnly: bool
	required: bool
	size: int
	src: str
	step: int | str
	type: HTMLInputType
	value: str | list[str] | int
	width: int | str


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
	value: str | list[str] | int


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
	max: int | str
	min: int | str
	optimum: int
	value: str | list[str] | int


class HTMLQuoteProps(BaseHTMLProps, DOMEvents[HTMLQuoteElement], total=False):
	cite: str


class HTMLObjectProps(BaseHTMLProps, DOMEvents[HTMLObjectElement], total=False):
	classId: str
	data: str
	form: str
	height: int | str
	name: str
	type: str
	useMap: str
	width: int | str
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
	value: str | list[str] | int


class HTMLOutputProps(BaseHTMLProps, DOMEvents[HTMLOutputElement], total=False):
	form: str
	htmlFor: str
	name: str


class HTMLParamProps(BaseHTMLProps, DOMEvents[GenericHTMLElement], total=False):
	name: str
	value: str | list[str] | int


class HTMLProgressProps(BaseHTMLProps, DOMEvents[HTMLProgressElement], total=False):
	max: int | str
	value: str | list[str] | int


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
	value: str | list[str] | int


class HTMLSourceProps(BaseHTMLProps, DOMEvents[HTMLSourceElement], total=False):
	height: int | str
	media: str
	sizes: str
	src: str
	srcSet: str
	type: str
	width: int | str


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
	cellPadding: int | str
	cellSpacing: int | str
	frame: bool
	rules: Literal["none", "groups", "rows", "columns", "all"]
	summary: str
	width: int | str


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
	value: str | list[str] | int
	wrap: str


class HTMLTdProps(BaseHTMLProps, DOMEvents[HTMLTableCellElement], total=False):
	align: Literal["left", "center", "right", "justify", "char"]
	colSpan: int
	headers: str
	rowSpan: int
	scope: str
	abbr: str
	height: int | str
	width: int | str
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
	height: int | str
	playsInline: bool
	poster: str
	width: int | str
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
	height: int | str
	id: str  # type: ignore
	lang: str
	max: int | str
	media: str
	method: str
	min: int | str
	name: str
	style: CSSProperties
	target: str
	type: str
	width: int | str

	# Other HTML properties
	role: str
	tabIndex: int
	crossOrigin: str

	# SVG specific attributes
	accentHeight: int | str
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
	alphabetic: int | str
	amplitude: int | str
	arabicForm: Literal["initial", "medial", "terminal", "isolated"]
	ascent: int | str
	attributeName: str
	attributeType: str
	autoReverse: bool
	azimuth: int | str
	baseFrequency: int | str
	baselineShift: int | str
	baseProfile: int | str
	bbox: int | str
	begin: int | str
	bias: int | str
	by: int | str
	calcMode: int | str
	capHeight: int | str
	clip: int | str
	clipPath: str
	clipPathUnits: int | str
	clipRule: int | str
	colorInterpolation: int | str
	colorInterpolationFilters: Literal["auto", "sRGB", "linearRGB", "inherit"]
	colorProfile: int | str
	colorRendering: int | str
	contentScriptType: int | str
	contentStyleType: int | str
	cursor: int | str
	cx: int | str
	cy: int | str
	d: str
	decelerate: int | str
	descent: int | str
	diffuseConstant: int | str
	direction: int | str
	display: int | str
	divisor: int | str
	dominantBaseline: int | str
	dur: int | str
	dx: int | str
	dy: int | str
	edgeMode: int | str
	elevation: int | str
	enableBackground: int | str
	end: int | str
	exponent: int | str
	externalResourcesRequired: bool
	fill: str
	fillOpacity: int | str
	fillRule: Literal["nonzero", "evenodd", "inherit"]
	filter: str
	filterRes: int | str
	filterUnits: int | str
	floodColor: int | str
	floodOpacity: int | str
	focusable: bool | Literal["auto"]
	fontFamily: str
	fontSize: int | str
	fontSizeAdjust: int | str
	fontStretch: int | str
	fontStyle: int | str
	fontVariant: int | str
	fontWeight: int | str
	format: int | str
	fr: int | str
	from_: int | str
	fx: int | str
	fy: int | str
	g1: int | str
	g2: int | str
	glyphName: int | str
	glyphOrientationHorizontal: int | str
	glyphOrientationVertical: int | str
	glyphRef: int | str
	gradientTransform: str
	gradientUnits: str
	hanging: int | str
	horizAdvX: int | str
	horizOriginX: int | str
	href: str
	ideographic: int | str
	imageRendering: int | str
	in2: int | str
	in_: str
	intercept: int | str
	k1: int | str
	k2: int | str
	k3: int | str
	k4: int | str
	k: int | str
	kernelMatrix: int | str
	kernelUnitLength: int | str
	kerning: int | str
	keyPoints: int | str
	keySplines: int | str
	keyTimes: int | str
	lengthAdjust: int | str
	letterSpacing: int | str
	lightingColor: int | str
	limitingConeAngle: int | str
	local: int | str
	markerEnd: str
	markerHeight: int | str
	markerMid: str
	markerStart: str
	markerUnits: int | str
	markerWidth: int | str
	mask: str
	maskContentUnits: int | str
	maskUnits: int | str
	mathematical: int | str
	mode: int | str
	numOctaves: int | str
	offset: int | str
	opacity: int | str
	operator: int | str
	order: int | str
	orient: int | str
	orientation: int | str
	origin: int | str
	overflow: int | str
	overlinePosition: int | str
	overlineThickness: int | str
	paintOrder: int | str
	panose1: int | str
	path: str
	pathLength: int | str
	patternContentUnits: str
	patternTransform: int | str
	patternUnits: str
	pointerEvents: int | str
	points: str
	pointsAtX: int | str
	pointsAtY: int | str
	pointsAtZ: int | str
	preserveAlpha: bool
	preserveAspectRatio: str
	primitiveUnits: int | str
	r: int | str
	radius: int | str
	refX: int | str
	refY: int | str
	renderingIntent: int | str
	repeatCount: int | str
	repeatDur: int | str
	requiredExtensions: int | str
	requiredFeatures: int | str
	restart: int | str
	result: str
	rotate: int | str
	rx: int | str
	ry: int | str
	scale: int | str
	seed: int | str
	shapeRendering: int | str
	slope: int | str
	spacing: int | str
	specularConstant: int | str
	specularExponent: int | str
	speed: int | str
	spreadMethod: str
	startOffset: int | str
	stdDeviation: int | str
	stemh: int | str
	stemv: int | str
	stitchTiles: int | str
	stopColor: str
	stopOpacity: int | str
	strikethroughPosition: int | str
	strikethroughThickness: int | str
	string: int | str
	stroke: str
	strokeDasharray: int | str
	strokeDashoffset: int | str
	strokeLinecap: Literal["butt", "round", "square", "inherit"]
	strokeLinejoin: Literal["miter", "round", "bevel", "inherit"]
	strokeMiterlimit: int | str
	strokeOpacity: int | str
	strokeWidth: int | str
	surfaceScale: int | str
	systemLanguage: int | str
	tableValues: int | str
	targetX: int | str
	targetY: int | str
	textAnchor: str
	textDecoration: int | str
	textLength: int | str
	textRendering: int | str
	to: int | str
	transform: str
	u1: int | str
	u2: int | str
	underlinePosition: int | str
	underlineThickness: int | str
	unicode: int | str
	unicodeBidi: int | str
	unicodeRange: int | str
	unitsPerEm: int | str
	vAlphabetic: int | str
	values: str
	vectorEffect: int | str
	version: str
	vertAdvY: int | str
	vertOriginX: int | str
	vertOriginY: int | str
	vHanging: int | str
	vIdeographic: int | str
	viewBox: str
	viewTarget: int | str
	visibility: int | str
	vMathematical: int | str
	widths: int | str
	wordSpacing: int | str
	writingMode: int | str
	x1: int | str
	x2: int | str
	x: int | str
	xChannelSelector: str
	xHeight: int | str
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
	y1: int | str
	y2: int | str
	y: int | str
	yChannelSelector: str
	z: int | str
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
