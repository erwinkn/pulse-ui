import { createExtractor } from "./extractor";

// Base extractors (camelCase) similar to events.ts style
const lowerTagName = (e: Element) => e.tagName.toLowerCase();

const ELEMENT_KEYS = [
  "id",
  "className",
  "tagName",
  "localName",
  "clientHeight",
  "clientLeft",
  "clientTop",
  "clientWidth",
  "scrollHeight",
  "scrollLeft",
  "scrollTop",
  "scrollWidth",
  "slot",
] as const satisfies readonly (keyof Element)[];

const HTML_OR_SVG_KEYS = [
  "autofocus",
  "tabIndex",
  "nonce",
] as const satisfies readonly (keyof HTMLOrSVGElement)[];

const HTML_ELEMENT_BASE_KEYS = [
  "accessKey",
  "accessKeyLabel",
  "autocapitalize",
  "dir",
  "draggable",
  "hidden",
  "inert",
  "lang",
  "offsetHeight",
  "offsetLeft",
  "offsetTop",
  "offsetWidth",
  "popover",
  "spellcheck",
  "title",
  "translate",
  "writingSuggestions",
  "contentEditable",
  "enterKeyHint",
  "isContentEditable",
  "inputMode",
] as const satisfies readonly (keyof HTMLElement)[];

const extractElement = createExtractor<Element>()(ELEMENT_KEYS, {
  tagName: lowerTagName,
});

const extractHTMLOrSVGElement =
  createExtractor<HTMLOrSVGElement>()(HTML_OR_SVG_KEYS);

const extractHTMLElementBaseOnly = createExtractor<HTMLElement>()(
  HTML_ELEMENT_BASE_KEYS
);

function extractHTMLElementBase(elt: HTMLElement) {
  return {
    ...extractElement(elt),
    ...extractHTMLOrSVGElement(elt as HTMLOrSVGElement),
    ...extractHTMLElementBaseOnly(elt),
  };
}

// Helper to compose per-element extractors with the shared base
function withBase<T extends HTMLElement>(
  keys: readonly (keyof T)[],
  computed?: Partial<Record<string, (src: T) => any>>
) {
  const only = createExtractor<T>()(keys, computed as any);
  return (elt: T) => ({ ...extractHTMLElementBase(elt), ...only(elt) });
}

const HTML_ANCHOR_KEYS = [
  "hash",
  "host",
  "hostname",
  "href",
  "origin",
  "password",
  "pathname",
  "port",
  "protocol",
  "search",
  "target",
  "download",
  "rel",
  "hreflang",
  "type",
  "username",
  "ping",
  "referrerPolicy",
  "text",
] as const satisfies readonly (keyof HTMLAnchorElement)[];
const anchorExtractor = withBase<HTMLAnchorElement>(HTML_ANCHOR_KEYS);

const HTML_AREA_KEYS = [
  "alt",
  "coords",
  "download",
  "hash",
  "host",
  "hostname",
  "href",
  "origin",
  "password",
  "pathname",
  "port",
  "protocol",
  "rel",
  "search",
  "shape",
  "target",
  "username",
  "ping",
  "referrerPolicy",
] as const satisfies readonly (keyof HTMLAreaElement)[];
const areaExtractor = withBase<HTMLAreaElement>(HTML_AREA_KEYS);

const HTML_MEDIA_KEYS = [
  "autoplay",
  "controls",
  "crossOrigin",
  "currentSrc",
  "currentTime",
  "defaultMuted",
  "defaultPlaybackRate",
  "duration",
  "ended",
  "loop",
  "muted",
  "networkState",
  "paused",
  "playbackRate",
  "preload",
  "readyState",
  "seeking",
  "src",
  "volume",
  "preservesPitch",
] as const satisfies readonly (keyof HTMLMediaElement)[];
const mediaExtractor = withBase<HTMLMediaElement>(HTML_MEDIA_KEYS);

const audioExtractor = (elt: HTMLAudioElement) => mediaExtractor(elt);

const HTML_BUTTON_KEYS = [
  "disabled",
  "name",
  "type",
  "value",
  "formAction",
  "formEnctype",
  "formMethod",
  "formNoValidate",
  "formTarget",
  "popoverTargetAction",
] as const satisfies readonly (keyof HTMLButtonElement)[];
const buttonExtractor = withBase<HTMLButtonElement>(HTML_BUTTON_KEYS);

const HTML_DATA_KEYS = [
  "value",
] as const satisfies readonly (keyof HTMLDataElement)[];
const dataExtractor = withBase<HTMLDataElement>(HTML_DATA_KEYS);

const HTML_EMBED_KEYS = [
  "height",
  "src",
  "type",
  "width",
  "align",
  "name",
] as const satisfies readonly (keyof HTMLEmbedElement)[];
const embedExtractor = withBase<HTMLEmbedElement>(HTML_EMBED_KEYS);

const HTML_FIELDSET_KEYS = [
  "disabled",
  "name",
  "type",
  "validationMessage",
  "willValidate",
] as const satisfies readonly (keyof HTMLFieldSetElement)[];
const fieldsetExtractor = withBase<HTMLFieldSetElement>(HTML_FIELDSET_KEYS);

const HTML_FORM_KEYS = [
  "acceptCharset",
  "action",
  "autocomplete",
  "encoding",
  "enctype",
  "length",
  "method",
  "name",
  "noValidate",
  "target",
  "rel",
] as const satisfies readonly (keyof HTMLFormElement)[];
const formExtractor = withBase<HTMLFormElement>(HTML_FORM_KEYS);

const HTML_IFRAME_KEYS = [
  "allow",
  "allowFullscreen",
  "height",
  "name",
  "referrerPolicy",
  "src",
  "srcdoc",
  "width",
  "align",
  "frameBorder",
  "longDesc",
  "marginHeight",
  "marginWidth",
  "scrolling",
  "sandbox",
] as const satisfies readonly (keyof HTMLIFrameElement)[];
const iframeExtractor = withBase<HTMLIFrameElement>(HTML_IFRAME_KEYS);

const HTML_IMAGE_KEYS = [
  "alt",
  "crossOrigin",
  "decoding",
  "height",
  "isMap",
  "loading",
  "naturalHeight",
  "naturalWidth",
  "referrerPolicy",
  "sizes",
  "src",
  "srcset",
  "useMap",
  "width",
  "align",
  "border",
  "complete",
  "hspace",
  "longDesc",
  "lowsrc",
  "name",
  "vspace",
  "x",
  "y",
  "fetchPriority",
] as const satisfies readonly (keyof HTMLImageElement)[];
const imageExtractor = withBase<HTMLImageElement>(HTML_IMAGE_KEYS);

const HTML_INPUT_KEYS = [
  "accept",
  "alt",
  "autocomplete",
  "checked",
  "defaultChecked",
  "defaultValue",
  "dirName",
  "disabled",
  "height",
  "indeterminate",
  "max",
  "maxLength",
  "min",
  "minLength",
  "multiple",
  "name",
  "pattern",
  "placeholder",
  "readOnly",
  "required",
  "selectionDirection",
  "selectionEnd",
  "selectionStart",
  "size",
  "src",
  "step",
  "type",
  "value",
  "valueAsNumber",
  "width",
  "align",
  "capture",
  "formAction",
  "formEnctype",
  "formMethod",
  "formNoValidate",
  "formTarget",
  "useMap",
  "validationMessage",
  "willValidate",
  "popoverTargetAction",
] as const satisfies readonly (keyof HTMLInputElement)[];
const inputExtractor = withBase<HTMLInputElement>(HTML_INPUT_KEYS);

const HTML_LABEL_KEYS = [
  "htmlFor",
] as const satisfies readonly (keyof HTMLLabelElement)[];
const labelExtractor = withBase<HTMLLabelElement>(HTML_LABEL_KEYS);

const HTML_LI_KEYS = [
  "value",
  "type",
] as const satisfies readonly (keyof HTMLLIElement)[];
const liExtractor = withBase<HTMLLIElement>(HTML_LI_KEYS);

const HTML_LINK_KEYS = [
  "as",
  "crossOrigin",
  "disabled",
  "fetchPriority",
  "href",
  "hreflang",
  "imageSizes",
  "imageSrcset",
  "integrity",
  "media",
  "referrerPolicy",
  "rel",
  "type",
  "charset",
  "rev",
  "target",
  "sizes",
] as const satisfies readonly (keyof HTMLLinkElement)[];
const linkExtractor = withBase<HTMLLinkElement>(HTML_LINK_KEYS);

const HTML_MAP_KEYS = [
  "name",
] as const satisfies readonly (keyof HTMLMapElement)[];
const mapExtractor = withBase<HTMLMapElement>(HTML_MAP_KEYS);

const HTML_METER_KEYS = [
  "high",
  "low",
  "max",
  "min",
  "optimum",
  "value",
] as const satisfies readonly (keyof HTMLMeterElement)[];
const meterExtractor = withBase<HTMLMeterElement>(HTML_METER_KEYS);

const HTML_MOD_KEYS = [
  "cite",
  "dateTime",
] as const satisfies readonly (keyof HTMLModElement)[];
const modExtractor = withBase<HTMLModElement>(HTML_MOD_KEYS);

const HTML_OL_KEYS = [
  "reversed",
  "start",
  "type",
  "compact",
] as const satisfies readonly (keyof HTMLOListElement)[];
const olistExtractor = withBase<HTMLOListElement>(HTML_OL_KEYS);

const HTML_OBJECT_KEYS = [
  "data",
  "height",
  "name",
  "type",
  "useMap",
  "width",
  "validationMessage",
  "willValidate",
  "align",
  "archive",
  "border",
  "code",
  "codeBase",
  "codeType",
  "declare",
  "hspace",
  "standby",
  "vspace",
] as const satisfies readonly (keyof HTMLObjectElement)[];
const objectExtractor = withBase<HTMLObjectElement>(HTML_OBJECT_KEYS);

const HTML_OPTGROUP_KEYS = [
  "disabled",
  "label",
] as const satisfies readonly (keyof HTMLOptGroupElement)[];
const optgroupExtractor = withBase<HTMLOptGroupElement>(HTML_OPTGROUP_KEYS);

const HTML_OPTION_KEYS = [
  "defaultSelected",
  "disabled",
  "index",
  "label",
  "selected",
  "text",
  "value",
] as const satisfies readonly (keyof HTMLOptionElement)[];
const optionExtractor = withBase<HTMLOptionElement>(HTML_OPTION_KEYS);

const HTML_OUTPUT_KEYS = [
  "defaultValue",
  "name",
  "type",
  "value",
  "htmlFor",
  "validationMessage",
  "willValidate",
] as const satisfies readonly (keyof HTMLOutputElement)[];
const outputExtractor = withBase<HTMLOutputElement>(HTML_OUTPUT_KEYS);

const HTML_PROGRESS_KEYS = [
  "max",
  "position",
  "value",
] as const satisfies readonly (keyof HTMLProgressElement)[];
const progressExtractor = withBase<HTMLProgressElement>(HTML_PROGRESS_KEYS);

const HTML_QUOTE_KEYS = [
  "cite",
] as const satisfies readonly (keyof HTMLQuoteElement)[];
const quoteExtractor = withBase<HTMLQuoteElement>(HTML_QUOTE_KEYS);

const citeExtractor = (elt: HTMLElement) => extractHTMLElementBase(elt);

const HTML_SCRIPT_KEYS = [
  "async",
  "crossOrigin",
  "defer",
  "fetchPriority",
  "integrity",
  "noModule",
  "referrerPolicy",
  "src",
  "text",
  "type",
  "charset",
] as const satisfies readonly (keyof HTMLScriptElement)[];
const extractHTMLScriptOnly = createExtractor<HTMLScriptElement>()(
  HTML_SCRIPT_KEYS,
  {
    event: (s) => (s as any).event,
    htmlFor: (s) => (s as any).htmlFor,
  }
);
const scriptExtractor = (elt: HTMLScriptElement) => ({
  ...extractHTMLElementBase(elt),
  ...extractHTMLScriptOnly(elt),
});

const HTML_SELECT_KEYS = [
  "autocomplete",
  "disabled",
  "length",
  "multiple",
  "name",
  "required",
  "selectedIndex",
  "size",
  "type",
  "value",
  "validationMessage",
  "willValidate",
] as const satisfies readonly (keyof HTMLSelectElement)[];
const selectExtractor = withBase<HTMLSelectElement>(HTML_SELECT_KEYS);

const HTML_SLOT_KEYS = [
  "name",
] as const satisfies readonly (keyof HTMLSlotElement)[];
const slotExtractor = withBase<HTMLSlotElement>(HTML_SLOT_KEYS);

const HTML_SOURCE_KEYS = [
  "height",
  "media",
  "sizes",
  "src",
  "srcset",
  "type",
  "width",
] as const satisfies readonly (keyof HTMLSourceElement)[];
const sourceExtractor = withBase<HTMLSourceElement>(HTML_SOURCE_KEYS);

const HTML_TABLE_CAPTION_KEYS = [
  "align",
] as const satisfies readonly (keyof HTMLTableCaptionElement)[];
const tableCaptionExtractor = withBase<HTMLTableCaptionElement>(
  HTML_TABLE_CAPTION_KEYS
);

const HTML_TABLE_CELL_KEYS = [
  "abbr",
  "cellIndex",
  "colSpan",
  "headers",
  "rowSpan",
  "scope",
  "align",
  "axis",
  "bgColor",
  "ch",
  "chOff",
  "height",
  "noWrap",
  "vAlign",
  "width",
] as const satisfies readonly (keyof HTMLTableCellElement)[];
const tableCellExtractor = withBase<HTMLTableCellElement>(HTML_TABLE_CELL_KEYS);

const HTML_TABLE_COL_KEYS = [
  "span",
  "align",
  "ch",
  "chOff",
  "vAlign",
  "width",
] as const satisfies readonly (keyof HTMLTableColElement)[];
const tableColExtractor = withBase<HTMLTableColElement>(HTML_TABLE_COL_KEYS);

const HTML_TABLE_KEYS = [
  "align",
  "bgColor",
  "border",
  "cellPadding",
  "cellSpacing",
  "frame",
  "rules",
  "summary",
  "width",
] as const satisfies readonly (keyof HTMLTableElement)[];
const tableExtractor = withBase<HTMLTableElement>(HTML_TABLE_KEYS);

const HTML_TR_KEYS = [
  "rowIndex",
  "sectionRowIndex",
  "align",
  "bgColor",
  "ch",
  "chOff",
  "vAlign",
] as const satisfies readonly (keyof HTMLTableRowElement)[];
const tableRowExtractor = withBase<HTMLTableRowElement>(HTML_TR_KEYS);

const HTML_TSECTION_KEYS = [
  "align",
  "ch",
  "chOff",
  "vAlign",
] as const satisfies readonly (keyof HTMLTableSectionElement)[];
const tableSectionExtractor =
  withBase<HTMLTableSectionElement>(HTML_TSECTION_KEYS);

const templateExtractor = (elt: HTMLTemplateElement) =>
  extractHTMLElementBase(elt);

const HTML_TEXTAREA_KEYS = [
  "autocomplete",
  "cols",
  "defaultValue",
  "dirName",
  "disabled",
  "maxLength",
  "minLength",
  "name",
  "placeholder",
  "readOnly",
  "required",
  "rows",
  "selectionDirection",
  "selectionEnd",
  "selectionStart",
  "value",
  "wrap",
  "textLength",
  "validationMessage",
  "willValidate",
] as const satisfies readonly (keyof HTMLTextAreaElement)[];
const textareaExtractor = withBase<HTMLTextAreaElement>(HTML_TEXTAREA_KEYS);

const HTML_TIME_KEYS = [
  "dateTime",
] as const satisfies readonly (keyof HTMLTimeElement)[];
const timeExtractor = withBase<HTMLTimeElement>(HTML_TIME_KEYS);

const HTML_TRACK_KEYS = [
  "default",
  "kind",
  "label",
  "readyState",
  "src",
  "srclang",
] as const satisfies readonly (keyof HTMLTrackElement)[];
const trackExtractor = withBase<HTMLTrackElement>(HTML_TRACK_KEYS);

const HTML_VIDEO_KEYS = [
  "height",
  "poster",
  "videoHeight",
  "videoWidth",
  "width",
  "playsInline",
] as const satisfies readonly (keyof HTMLVideoElement)[];
const extractHTMLVideoOnly =
  createExtractor<HTMLVideoElement>()(HTML_VIDEO_KEYS);
const videoExtractor = (elt: HTMLVideoElement) => ({
  ...mediaExtractor(elt),
  ...extractHTMLVideoOnly(elt),
});

const HTML_BR_KEYS = [
  "clear",
] as const satisfies readonly (keyof HTMLBRElement)[];
const brExtractor = withBase<HTMLBRElement>(HTML_BR_KEYS);

const HTML_BASE_KEYS = [
  "href",
  "target",
] as const satisfies readonly (keyof HTMLBaseElement)[];
const baseExtractor = withBase<HTMLBaseElement>(HTML_BASE_KEYS);

const HTML_BODY_KEYS = [
  "aLink",
  "background",
  "bgColor",
  "link",
  "text",
  "vLink",
] as const satisfies readonly (keyof HTMLBodyElement)[];
const bodyExtractor = withBase<HTMLBodyElement>(HTML_BODY_KEYS);

const HTML_DLIST_KEYS = [
  "compact",
] as const satisfies readonly (keyof HTMLDListElement)[];
const dlistExtractor = withBase<HTMLDListElement>(HTML_DLIST_KEYS);

const HTML_DETAILS_KEYS = [
  "open",
] as const satisfies readonly (keyof HTMLDetailsElement)[];
const detailsExtractor = withBase<HTMLDetailsElement>(HTML_DETAILS_KEYS);

const HTML_DIALOG_KEYS = [
  "open",
  "returnValue",
] as const satisfies readonly (keyof HTMLDialogElement)[];
const dialogExtractor = withBase<HTMLDialogElement>(HTML_DIALOG_KEYS);

const HTML_DIV_KEYS = [
  "align",
] as const satisfies readonly (keyof HTMLDivElement)[];
const divExtractor = withBase<HTMLDivElement>(HTML_DIV_KEYS);

const headExtractor = (elt: HTMLHeadElement) => extractHTMLElementBase(elt);

const HTML_HEADING_KEYS = [
  "align",
] as const satisfies readonly (keyof HTMLHeadingElement)[];
const headingExtractor = withBase<HTMLHeadingElement>(HTML_HEADING_KEYS);

const HTML_HR_KEYS = [
  "align",
  "color",
  "noShade",
  "size",
  "width",
] as const satisfies readonly (keyof HTMLHRElement)[];
const hrExtractor = withBase<HTMLHRElement>(HTML_HR_KEYS);

const HTML_HTML_KEYS = [
  "version",
] as const satisfies readonly (keyof HTMLHtmlElement)[];
const htmlExtractor = withBase<HTMLHtmlElement>(HTML_HTML_KEYS);

const menuExtractor = (elt: HTMLMenuElement) => extractHTMLElementBase(elt);

const HTML_META_KEYS = [
  "content",
  "httpEquiv",
  "name",
  "scheme",
] as const satisfies readonly (keyof HTMLMetaElement)[];
const metaExtractor = withBase<HTMLMetaElement>(HTML_META_KEYS);

const HTML_P_KEYS = [
  "align",
] as const satisfies readonly (keyof HTMLParagraphElement)[];
const paragraphExtractor = withBase<HTMLParagraphElement>(HTML_P_KEYS);

const pictureExtractor = (elt: HTMLPictureElement) =>
  extractHTMLElementBase(elt);

const HTML_PRE_KEYS = [
  "width",
] as const satisfies readonly (keyof HTMLPreElement)[];
const preExtractor = withBase<HTMLPreElement>(HTML_PRE_KEYS);

const spanExtractor = (elt: HTMLSpanElement) => extractHTMLElementBase(elt);

const HTML_STYLE_KEYS = [
  "media",
  "type",
  "disabled",
] as const satisfies readonly (keyof HTMLStyleElement)[];
const styleExtractor = withBase<HTMLStyleElement>(HTML_STYLE_KEYS);

const HTML_TITLE_KEYS = [
  "text",
] as const satisfies readonly (keyof HTMLTitleElement)[];
const titleExtractor = withBase<HTMLTitleElement>(HTML_TITLE_KEYS);

const HTML_UL_KEYS = [
  "compact",
  "type",
] as const satisfies readonly (keyof HTMLUListElement)[];
const ulistExtractor = withBase<HTMLUListElement>(HTML_UL_KEYS);

// Map of tagName -> extractor (concise, like events.ts)
const elementExtractors: Record<string, (elt: any) => object> = {
  A: anchorExtractor,
  AREA: areaExtractor,
  AUDIO: audioExtractor,
  BASE: baseExtractor,
  BLOCKQUOTE: quoteExtractor,
  Q: quoteExtractor,
  BODY: bodyExtractor,
  BR: brExtractor,
  BUTTON: buttonExtractor,
  CANVAS: extractHTMLElementBase,
  CAPTION: tableCaptionExtractor,
  CITE: citeExtractor,
  COL: tableColExtractor,
  COLGROUP: tableColExtractor,
  DATA: dataExtractor,
  DETAILS: detailsExtractor,
  DIALOG: dialogExtractor,
  DIV: divExtractor,
  DL: dlistExtractor,
  EMBED: embedExtractor,
  FIELDSET: fieldsetExtractor,
  FORM: formExtractor,
  H1: headingExtractor,
  H2: headingExtractor,
  H3: headingExtractor,
  H4: headingExtractor,
  H5: headingExtractor,
  H6: headingExtractor,
  HEAD: headExtractor,
  HR: hrExtractor,
  HTML: htmlExtractor,
  IFRAME: iframeExtractor,
  IMG: imageExtractor,
  INPUT: inputExtractor,
  LABEL: labelExtractor,
  LI: liExtractor,
  LINK: linkExtractor,
  MAP: mapExtractor,
  MENU: menuExtractor,
  META: metaExtractor,
  METER: meterExtractor,
  INS: modExtractor,
  DEL: modExtractor,
  OBJECT: objectExtractor,
  OL: olistExtractor,
  OPTGROUP: optgroupExtractor,
  OPTION: optionExtractor,
  OUTPUT: outputExtractor,
  P: paragraphExtractor,
  PICTURE: pictureExtractor,
  PRE: preExtractor,
  PROGRESS: progressExtractor,
  SCRIPT: scriptExtractor,
  SELECT: selectExtractor,
  SLOT: slotExtractor,
  SOURCE: sourceExtractor,
  SPAN: spanExtractor,
  STYLE: styleExtractor,
  TABLE: tableExtractor,
  TBODY: tableSectionExtractor,
  THEAD: tableSectionExtractor,
  TFOOT: tableSectionExtractor,
  TD: tableCellExtractor,
  TH: tableCellExtractor,
  TEMPLATE: templateExtractor,
  TEXTAREA: textareaExtractor,
  TIME: timeExtractor,
  TITLE: titleExtractor,
  TR: tableRowExtractor,
  TRACK: trackExtractor,
  UL: ulistExtractor,
  VIDEO: videoExtractor,
};

export function extractHTMLElement(elt: HTMLElement): object {
  const tagName = elt.tagName.toUpperCase();

  const extractor = elementExtractors[tagName];
  if (extractor) {
    return extractor(elt);
  }
  throw new Error(
    `Unexpected HTML element tag: ${elt.tagName} (update .web/custom/serialize.ts)`
  );
}
