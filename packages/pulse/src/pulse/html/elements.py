# Adapted from MDN Web Docs and @types/react
# Note: Similar to events, we can only serialize data attributes, not methods or
# complex objects like NodeList.

from typing import Literal, TypedDict, Union


class Element(TypedDict):
	# Basic properties
	id: str
	className: str
	tagName: str
	localName: str
	clientHeight: float
	clientLeft: float
	clientTop: float
	clientWidth: float
	scrollHeight: float
	scrollLeft: float
	scrollTop: float
	scrollWidth: float
	slot: str


class HTMLOrSVGElement(TypedDict):
	autofocus: bool
	tabIndex: int
	nonce: str | None
	# Not including dataset as it's not useful


class HTMLElementBase(Element, HTMLOrSVGElement):
	accessKey: str
	accessKeyLabel: str | None
	autocapitalize: str
	dir: Literal["", "ltr", "rtl", "auto"]
	draggable: bool
	hidden: bool
	inert: bool
	lang: str
	offsetHeight: float  # Read-only layout properties
	offsetLeft: float
	# offset_parent: Element | None # could be complex to serialize
	offsetTop: float
	offsetWidth: float
	popover: str | None
	spellcheck: bool
	title: str
	translate: bool
	writingSuggestions: str

	# Added properties from ELementContentEditable definition
	contentEditable: str
	enterKeyHint: str
	isContentEditable: bool
	inputMode: str

	# Not including inner_text and outer_text as those could be heavy


class GenericHTMLElement(HTMLElementBase): ...


class HTMLAnchorElement(HTMLElementBase):
	"""Properties specific to <a> elements."""

	tagName: Literal["a"]

	hash: str
	host: str
	hostname: str
	href: str
	origin: str
	password: str
	pathname: str
	port: str
	protocol: str
	search: str
	target: str
	download: str
	rel: str
	hreflang: str
	type: str
	username: str

	# Added properties
	ping: str
	referrerPolicy: Literal[
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
	text: str


class HTMLAreaElement(HTMLElementBase):
	"""Properties specific to <area> elements."""

	tagName: Literal["area"]

	alt: str
	coords: str
	download: str
	hash: str
	host: str
	hostname: str
	href: str
	origin: str
	password: str
	pathname: str
	port: str
	protocol: str
	rel: str
	search: str
	shape: str
	target: str
	username: str

	# Added properties
	ping: str
	referrerPolicy: Literal[
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


class HTMLMediaElement(HTMLElementBase):
	"""Properties specific to media elements like <audio> and <video>."""

	autoplay: bool
	controls: bool
	crossOrigin: Literal["anonymous", "use-credentials"] | None
	currentSrc: str
	currentTime: float
	defaultMuted: bool
	defaultPlaybackRate: float
	duration: float  # Read-only, NaN if unavailable
	ended: bool  # Read-only
	loop: bool
	muted: bool
	networkState: Literal[
		0, 1, 2, 3
	]  # NETWORK_EMPTY, NETWORK_IDLE, NETWORK_LOADING, NETWORK_NO_SOURCE
	paused: bool  # Read-only
	playbackRate: float
	preload: Literal["none", "metadata", "auto", ""]
	readyState: Literal[0, 1, 2, 3, 4]
	seeking: bool  # Read-only
	src: str
	volume: float
	preservesPitch: bool


class HTMLAudioElement(HTMLMediaElement):
	"""Specifies <audio> elements. Currently no differing properties from HTMLMediaElement in this subset."""

	tagName: Literal["audio"]


class HTMLButtonElement(HTMLElementBase):
	"""Properties specific to <button> elements."""

	tagName: Literal["button"]

	disabled: bool
	name: str
	type: Literal["submit", "reset", "button"]
	value: str

	# Added form-related attributes
	formAction: str
	formEnctype: str
	formMethod: str
	formNoValidate: bool
	formTarget: str
	popoverTargetAction: str


class HTMLDataElement(HTMLElementBase):
	"""Properties specific to <data> elements."""

	tagName: Literal["data"]

	value: str


class HTMLEmbedElement(HTMLElementBase):
	"""Properties specific to <embed> elements."""

	tagName: Literal["embed"]

	height: str
	src: str
	type: str
	width: str

	# Added deprecated properties
	align: str
	name: str


class HTMLFieldSetElement(HTMLElementBase):
	"""Properties specific to <fieldset> elements."""

	tagName: Literal["fieldset"]

	disabled: bool
	name: str
	type: str  # Generally "fieldset"

	# Added validation properties
	validationMessage: str
	willValidate: bool


class HTMLFormElement(HTMLElementBase):
	"""Properties specific to <form> elements."""

	tagName: Literal["form"]  # type: ignore[misc]

	acceptCharset: str
	action: str
	autocomplete: Literal["on", "off"]
	encoding: str  # alias for enctype
	enctype: Literal[
		"application/x-www-form-urlencoded",
		"multipart/form-data",
		"text/plain",
	]
	length: int  # Read-only, number of controls in the form
	method: Literal["get", "post", "dialog"]
	name: str
	noValidate: bool
	target: str
	rel: str


class HTMLIFrameElement(HTMLElementBase):
	"""Properties specific to <iframe> elements."""

	tagName: Literal["iframe"]

	allow: str
	allowFullscreen: bool
	height: str
	name: str
	referrerPolicy: Literal[
		"no-referrer",
		"no-referrer-when-downgrade",
		"origin",
		"origin-when-cross-origin",
		"same-origin",
		"strict-origin",
		"strict-origin-when-cross-origin",
		"unsafe-url",
	]
	src: str
	srcdoc: str
	width: str

	# Added deprecated properties
	align: str
	frameBorder: str
	longDesc: str
	marginHeight: str
	marginWidth: str
	scrolling: str
	sandbox: str


class HTMLImageElement(HTMLElementBase):
	"""Properties specific to <img> elements."""

	tagName: Literal["img"]

	alt: str
	crossOrigin: Literal["anonymous", "use-credentials"] | None
	decoding: Literal["sync", "async", "auto"]
	height: int
	isMap: bool
	loading: Literal["eager", "lazy"]
	naturalHeight: int  # Read-only, intrinsic height
	naturalWidth: int  # Read-only, intrinsic width
	referrerPolicy: Literal[
		"no-referrer",
		"no-referrer-when-downgrade",
		"origin",
		"origin-when-cross-origin",
		"same-origin",
		"strict-origin",
		"strict-origin-when-cross-origin",
		"unsafe-url",
	]
	sizes: str
	src: str
	srcset: str
	useMap: str
	width: int

	# Added properties (some deprecated)
	align: str
	border: str
	complete: bool
	hspace: int
	longDesc: str
	lowsrc: str
	name: str
	vspace: int
	x: float
	y: float
	fetchPriority: Literal["high", "low", "auto"]


class HTMLInputElement(HTMLElementBase):
	"""Properties specific to <input> elements."""

	tagName: Literal["input"]

	accept: str
	alt: str
	autocomplete: str
	checked: bool  # For checkbox/radio
	defaultChecked: bool
	defaultValue: str
	dirName: str
	disabled: bool
	height: str  # Only for type="image"
	indeterminate: bool  # For checkbox
	max: str  # Works with number, date, range types etc.
	maxLength: int
	min: str
	minLength: int
	multiple: bool  # For email, file
	name: str
	pattern: str
	placeholder: str
	readOnly: bool
	required: bool
	selectionDirection: Literal["forward", "backward", "none"] | None
	selectionEnd: int | None
	selectionStart: int | None
	size: int
	src: str  # Only for type="image"
	step: str
	type: str  # Input type (text, password, checkbox, etc.)
	value: str  # Current value
	valueAsNumber: float | None  # Parses value as float, NaN if invalid
	width: str  # Only for type="image"

	# Added properties (some deprecated)
	align: str
	capture: str
	formAction: str
	formEnctype: str
	formMethod: str
	formNoValidate: bool
	formTarget: str
	useMap: str
	validationMessage: str
	willValidate: bool
	popoverTargetAction: str


class HTMLLabelElement(HTMLElementBase):
	"""Properties specific to <label> elements."""

	tagName: Literal["label"]

	htmlFor: str  # Corresponds to 'for' attribute


class HTMLLiElement(HTMLElementBase):
	"""Properties specific to <li> elements."""

	tagName: Literal["li"]

	value: int  # Only valid if parent is <ol>
	type: str


class HTMLLinkElement(HTMLElementBase):
	"""Properties specific to <link> elements."""

	tagName: Literal["link"]

	as_: str  # Corresponds to 'as' attribute
	crossOrigin: Literal["anonymous", "use-credentials"] | None
	disabled: bool
	fetchPriority: Literal["high", "low", "auto"]
	href: str
	hreflang: str
	imageSizes: str
	imageSrcset: str
	integrity: str
	media: str
	referrerPolicy: Literal[
		"no-referrer",
		"no-referrer-when-downgrade",
		"origin",
		"origin-when-cross-origin",
		"same-origin",
		"strict-origin",
		"strict-origin-when-cross-origin",
		"unsafe-url",
	]
	rel: str
	type: str

	# Added properties (some deprecated)
	charset: str
	rev: str
	target: str
	sizes: str


class HTMLMapElement(HTMLElementBase):
	"""Properties specific to <map> elements."""

	tagName: Literal["map"]

	name: str


class HTMLMeterElement(HTMLElementBase):
	"""Properties specific to <meter> elements."""

	tagName: Literal["meter"]

	high: float
	low: float
	max: float
	min: float
	optimum: float
	value: float


class HTMLModElement(HTMLElementBase):
	"""Properties specific to <ins> and <del> elements."""

	tagName: Literal["ins", "del"]

	cite: str
	dateTime: str  # Corresponds to 'datetime' attribute


class HTMLOListElement(HTMLElementBase):
	"""Properties specific to <ol> elements."""

	tagName: Literal["ol"]

	reversed: bool
	start: int
	type: Literal["1", "a", "A", "i", "I"]
	compact: bool


class HTMLObjectElement(HTMLElementBase):
	"""Properties specific to <object> elements."""

	tagName: Literal["object"]

	data: str
	# disabled: bool
	height: str
	name: str
	type: str
	useMap: str
	width: str

	# Added properties (some deprecated)
	align: str
	archive: str
	border: str
	code: str
	codeBase: str
	codeType: str
	declare: bool
	hspace: int
	standby: str
	validationMessage: str
	vspace: int
	willValidate: bool


class HTMLOptGroupElement(HTMLElementBase):
	"""Properties specific to <optgroup> elements."""

	tagName: Literal["optgroup"]

	disabled: bool
	label: str


class HTMLOptionElement(HTMLElementBase):
	"""Properties specific to <option> elements."""

	tagName: Literal["option"]

	defaultSelected: bool
	disabled: bool
	index: int  # Read-only
	label: str
	selected: bool
	text: str  # Text content
	value: str


class HTMLOutputElement(HTMLElementBase):
	"""Properties specific to <output> elements."""

	tagName: Literal["output"]

	defaultValue: str
	name: str
	type: str  # Generally "output"
	value: str

	# Added properties
	htmlFor: str
	validationMessage: str
	willValidate: bool


class HTMLProgressElement(HTMLElementBase):
	"""Properties specific to <progress> elements."""

	tagName: Literal["progress"]

	max: float
	position: float  # Read-only, -1 if indeterminate
	value: float


class HTMLQuoteElement(HTMLElementBase):
	"""Properties specific to <q> and <blockquote> elements."""

	tagName: Literal["q", "blockquote"]

	cite: str


class HTMLCiteElement(HTMLElementBase):
	"""Properties specific to <cite> elements."""

	tagName: Literal["cite"]


class HTMLScriptElement(HTMLElementBase):
	"""Properties specific to <script> elements."""

	tagName: Literal["script"]

	async_: bool  # Corresponds to 'async' attribute
	crossOrigin: Literal["anonymous", "use-credentials"] | None
	defer: bool
	fetchPriority: Literal["high", "low", "auto"]
	integrity: str
	noModule: bool
	referrerPolicy: Literal[
		"",
		"no-referrer",
		"no-referrer-when-downgrade",
		"origin",
		"origin-when-cross-origin",
		"same-origin",
		"strict-origin",
		"strict-origin-when-cross-origin",
		"unsafe-url",
	]  # Expanded Literal
	src: str
	text: str  # Script content if inline
	type: str

	# Added deprecated properties
	charset: str
	event: str
	htmlFor: str


class HTMLSelectElement(HTMLElementBase):
	"""Properties specific to <select> elements."""

	tagName: Literal["select"]

	autocomplete: str
	disabled: bool
	length: int  # Read-only, number of options
	multiple: bool
	name: str
	required: bool
	selectedIndex: int
	size: int
	type: Literal["select-one", "select-multiple"]  # Read-only
	value: str  # Value of the first selected option, or ""

	# Added validation properties
	validationMessage: str
	willValidate: bool


class HTMLSlotElement(HTMLElementBase):
	"""Properties specific to <slot> elements."""

	tagName: Literal["slot"]

	name: str


class HTMLSourceElement(HTMLElementBase):
	"""Properties specific to <source> elements."""

	tagName: Literal["source"]

	height: int
	media: str
	sizes: str
	src: str
	srcset: str
	type: str
	width: int


class HTMLTableCaptionElement(HTMLElementBase):
	"""Properties specific to <caption> elements."""

	tagName: Literal["caption"]
	align: str


class HTMLTableCellElement(HTMLElementBase):
	"""Properties specific to <td> and <th> elements."""

	tagName: Literal["td", "th"]

	abbr: str
	cellIndex: int  # Read-only
	colSpan: int
	headers: str  # Corresponds to 'headers' attribute, space-separated list of IDs
	rowSpan: int
	scope: Literal["row", "col", "rowgroup", "colgroup", ""]

	# Added deprecated properties
	align: str
	axis: str
	bgColor: str
	ch: str
	chOff: str
	height: str
	noWrap: bool
	vAlign: str
	width: str


class HTMLTableColElement(HTMLElementBase):
	"""Properties specific to <col> and <colgroup> elements."""

	tagName: Literal["col", "colgroup"]

	span: int

	# Added deprecated properties
	align: str
	ch: str
	chOff: str
	vAlign: str
	width: str


class HTMLTableElement(HTMLElementBase):
	"""Properties specific to <table> elements."""

	tagName: Literal["table"]

	# caption: Optional[HTMLTableCaptionElement]  # Reference, might be tricky
	# t_head: Optional[HTMLTableSectionElement] # Reference
	# t_foot: Optional[HTMLTableSectionElement] # Reference
	# t_bodies: HTMLCollection # Cannot serialize
	# rows: HTMLCollection # Cannot serialize

	# Added deprecated properties
	align: str
	bgColor: str
	border: str
	cellPadding: str
	cellSpacing: str
	frame: str
	rules: str
	summary: str
	width: str


class HTMLTableRowElement(HTMLElementBase):
	"""Properties specific to <tr> elements."""

	tagName: Literal["tr"]

	# cells: HTMLCollection # Cannot serialize
	rowIndex: int  # Read-only
	sectionRowIndex: int  # Read-only

	# Added deprecated properties
	align: str
	bgColor: str
	ch: str
	chOff: str
	vAlign: str


class HTMLTableSectionElement(HTMLElementBase):
	"""Properties specific to <thead>, <tbody>, <tfoot> elements."""

	tagName: Literal["thead", "tbody", "tfoot"]

	# rows: HTMLCollection # Cannot serialize
	# Added deprecated properties
	align: str
	ch: str
	chOff: str
	vAlign: str


class HTMLTemplateElement(HTMLElementBase):
	"""Properties specific to <template> elements."""

	tagName: Literal["template"]

	# content: DocumentFragment # Cannot serialize
	pass


class HTMLTextAreaElement(HTMLElementBase):
	"""Properties specific to <textarea> elements."""

	tagName: Literal["textarea"]

	autocomplete: str
	cols: int
	defaultValue: str
	dirName: str
	disabled: bool
	maxLength: int
	minLength: int
	name: str
	placeholder: str
	readOnly: bool
	required: bool
	rows: int
	selectionDirection: Literal["forward", "backward", "none"] | None
	selectionEnd: int | None
	selectionStart: int | None
	value: str
	wrap: Literal["soft", "hard", "off"]

	# Added properties
	textLength: int
	validationMessage: str
	willValidate: bool


class HTMLTimeElement(HTMLElementBase):
	"""Properties specific to <time> elements."""

	tagName: Literal["time"]

	datetime: str  # Corresponds to 'dateTime' attribute


class HTMLTrackElement(HTMLElementBase):
	"""Properties specific to <track> elements."""

	tagName: Literal["track"]

	default: bool
	kind: Literal["subtitles", "captions", "descriptions", "chapters", "metadata"]
	label: str
	readyState: Literal[0, 1, 2, 3]
	src: str
	srclang: str
	# track: Optional[TextTrack] # Cannot serialize


class HTMLVideoElement(HTMLMediaElement):
	"""Properties specific to <video> elements."""

	tagName: Literal["video"]

	height: int
	poster: str
	videoHeight: int  # Read-only, intrinsic height
	videoWidth: int  # Read-only, intrinsic width
	width: int
	playsInline: bool


class HTMLBRElement(HTMLElementBase):
	"""Properties specific to <br> elements."""

	tagName: Literal["br"]
	clear: str


class HTMLBaseElement(HTMLElementBase):
	"""Properties specific to <base> elements."""

	tagName: Literal["base"]
	href: str
	target: str


class HTMLBodyElement(HTMLElementBase):
	"""Properties specific to <body> elements."""

	tagName: Literal["body"]
	aLink: str
	background: str
	bgColor: str
	link: str
	text: str
	vLink: str


class HTMLDListElement(HTMLElementBase):
	"""Properties specific to <dl> elements."""

	tagName: Literal["dl"]
	compact: bool


class HTMLDetailsElement(HTMLElementBase):
	"""Properties specific to <details> elements."""

	tagName: Literal["details"]
	open: bool


class HTMLDialogElement(HTMLElementBase):
	"""Properties specific to <dialog> elements."""

	tagName: Literal["dialog"]
	open: bool
	returnValue: str


class HTMLDivElement(HTMLElementBase):
	"""Properties specific to <div> elements."""

	tagName: Literal["div"]
	align: str


class HTMLHeadElement(HTMLElementBase):
	"""Properties specific to <head> elements."""

	tagName: Literal["head"]


class HTMLHeadingElement(HTMLElementBase):
	"""Properties specific to <h1> through <h6> elements."""

	tagName: Literal["h1", "h2", "h3", "h4", "h5", "h6"]
	align: str


class HTMLHRElement(HTMLElementBase):
	"""Properties specific to <hr> elements."""

	tagName: Literal["hr"]
	align: str
	color: str
	noShade: bool
	size: str
	width: str


class HTMLHtmlElement(HTMLElementBase):
	"""Properties specific to <html> elements."""

	tagName: Literal["html"]
	version: str


class HTMLMenuElement(HTMLElementBase):
	"""Properties specific to <menu> elements."""

	tagName: Literal["menu"]


class HTMLMetaElement(HTMLElementBase):
	"""Properties specific to <meta> elements."""

	tagName: Literal["meta"]
	content: str
	httpEquiv: str
	name: str
	scheme: str


class HTMLParagraphElement(HTMLElementBase):
	"""Properties specific to <p> elements."""

	tagName: Literal["p"]
	align: str


class HTMLPictureElement(HTMLElementBase):
	"""Properties specific to <picture> elements."""

	tagName: Literal["picture"]


class HTMLPreElement(HTMLElementBase):
	"""Properties specific to <pre> elements."""

	tagName: Literal["pre"]
	width: int


class HTMLSpanElement(HTMLElementBase):
	"""Properties specific to <span> elements."""

	tagName: Literal["span"]
	# No additional properties


class HTMLStyleElement(HTMLElementBase):
	"""Properties specific to <style> elements."""

	tagName: Literal["style"]
	media: str
	type: str
	disabled: bool


class HTMLTitleElement(HTMLElementBase):
	"""Properties specific to <title> elements."""

	tagName: Literal["title"]
	text: str


class HTMLUListElement(HTMLElementBase):
	"""Properties specific to <ul> elements."""

	tagName: Literal["ul"]
	compact: bool
	type: str


HTMLElement = Union[
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
	HTMLMenuElement,
	HTMLMetaElement,
	HTMLMeterElement,
	HTMLModElement,
	HTMLOListElement,
	HTMLObjectElement,
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
]
