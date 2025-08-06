/* === IMPORTANT === */

// used for untyped stuff, like nativeEvent
export function cleanForSerialization(obj: unknown): unknown {
  const result = _cleanForSerializationRecursive(obj, new WeakSet());
  return result;
}

function _cleanForSerializationRecursive(
  obj: unknown,
  seen: WeakSet<WeakKey>
): unknown {
  if (obj === null || typeof obj !== "object") {
    return obj;
  }
  if (seen.has(obj)) {
    return undefined; // handle circular refs
  }

  seen.add(obj);

  if (Array.isArray(obj)) {
    const cleanedArray = obj
      .map((item) => _cleanForSerializationRecursive(item, seen))
      .filter((item) => item !== undefined);

    return cleanedArray;
  }

  const plainObject: Record<string, any> = {};

  for (const key in obj) {
    if (typeof key !== "string") {
      continue;
    }
    const value = obj[key as keyof typeof obj];
    if (
      typeof value === "function" ||
      typeof value === "symbol" ||
      typeof value === "undefined"
    ) {
      continue;
    }

    const cleanedValue = _cleanForSerializationRecursive(value, seen);
    if (key === "target") {
      console.log("Cleaned target value:", cleanedValue);
    }
    if (cleanedValue !== undefined) {
      plainObject[key] = cleanedValue;
    }
  }

  return plainObject;
}

export function extractElement(elt: Element): object {
  return {
    id: elt.id,
    class_name: elt.className,
    tag_name: elt.tagName.toLowerCase(),
    local_name: elt.localName,
    client_height: elt.clientHeight,
    client_left: elt.clientLeft,
    client_top: elt.clientTop,
    client_width: elt.clientWidth,
    scroll_height: elt.scrollHeight,
    scroll_left: elt.scrollLeft,
    scroll_top: elt.scrollTop,
    scroll_width: elt.scrollWidth,
    slot: elt.slot,
  };
}

export function extractHTMLOrSVGElement(elt: HTMLOrSVGElement) {
  return {
    autofocus: elt.autofocus,
    tab_index: elt.tabIndex,
    nonce: elt.nonce,
  };
}

export function extractHTMLElementBase(elt: HTMLElement) {
  return {
    ...extractElement(elt),
    ...extractHTMLOrSVGElement(elt),
    access_key: elt.accessKey,
    access_key_label: elt.accessKeyLabel,
    autocapitalize: elt.autocapitalize,
    dir: elt.dir,
    draggable: elt.draggable,
    hidden: elt.hidden,
    inert: elt.inert,
    lang: elt.lang,
    offset_height: elt.offsetHeight,
    offset_left: elt.offsetLeft,
    offset_top: elt.offsetTop,
    offset_width: elt.offsetWidth,
    popover: elt.popover,
    spellcheck: elt.spellcheck,
    title: elt.title,
    translate: elt.translate,
    writing_suggestions: elt.writingSuggestions,
    content_editable: elt.contentEditable,
    enter_key_hint: elt.enterKeyHint,
    is_content_editable: elt.isContentEditable,
    input_mode: elt.inputMode,
  };
}

export function extractHTMLAnchorElement(elt: HTMLAnchorElement) {
  return {
    ...extractHTMLElementBase(elt),
    hash: elt.hash,
    host: elt.host,
    hostname: elt.hostname,
    href: elt.href,
    origin: elt.origin,
    password: elt.password,
    pathname: elt.pathname,
    port: elt.port,
    protocol: elt.protocol,
    search: elt.search,
    target: elt.target,
    download: elt.download,
    rel: elt.rel,
    hreflang: elt.hreflang,
    type: elt.type,
    username: elt.username,
    ping: elt.ping,
    referrer_policy: elt.referrerPolicy,
    text: elt.text,
  };
}

export function extractHTMLAreaElement(elt: HTMLAreaElement) {
  return {
    ...extractHTMLElementBase(elt),
    alt: elt.alt,
    coords: elt.coords,
    download: elt.download,
    hash: elt.hash,
    host: elt.host,
    hostname: elt.hostname,
    href: elt.href,
    origin: elt.origin,
    password: elt.password,
    pathname: elt.pathname,
    port: elt.port,
    protocol: elt.protocol,
    rel: elt.rel,
    search: elt.search,
    shape: elt.shape,
    target: elt.target,
    username: elt.username,
    ping: elt.ping,
    referrer_policy: elt.referrerPolicy,
  };
}

export function extractHTMLMediaElement(elt: HTMLMediaElement) {
  return {
    ...extractHTMLElementBase(elt),
    autoplay: elt.autoplay,
    controls: elt.controls,
    cross_origin: elt.crossOrigin,
    current_src: elt.currentSrc,
    current_time: elt.currentTime,
    default_muted: elt.defaultMuted,
    default_playback_rate: elt.defaultPlaybackRate,
    duration: elt.duration,
    ended: elt.ended,
    loop: elt.loop,
    muted: elt.muted,
    network_state: elt.networkState,
    paused: elt.paused,
    playback_rate: elt.playbackRate,
    preload: elt.preload,
    ready_state: elt.readyState,
    seeking: elt.seeking,
    src: elt.src,
    volume: elt.volume,
    preserves_pitch: elt.preservesPitch,
  };
}

export function extractHTMLAudioElement(elt: HTMLAudioElement) {
  return {
    ...extractHTMLMediaElement(elt),
    // No additional properties for audio elements
  };
}

export function extractHTMLButtonElement(elt: HTMLButtonElement) {
  return {
    ...extractHTMLElementBase(elt),
    disabled: elt.disabled,
    name: elt.name,
    type: elt.type,
    value: elt.value,
    form_action: elt.formAction,
    form_enctype: elt.formEnctype,
    form_method: elt.formMethod,
    form_no_validate: elt.formNoValidate,
    form_target: elt.formTarget,
    popover_target_action: elt.popoverTargetAction,
  };
}

export function extractHTMLDataElement(elt: HTMLDataElement) {
  return {
    ...extractHTMLElementBase(elt),
    value: elt.value,
  };
}

export function extractHTMLEmbedElement(elt: HTMLEmbedElement) {
  return {
    ...extractHTMLElementBase(elt),
    height: elt.height,
    src: elt.src,
    type: elt.type,
    width: elt.width,
    align: elt.align,
    name: elt.name,
  };
}

export function extractHTMLFieldSetElement(elt: HTMLFieldSetElement) {
  return {
    ...extractHTMLElementBase(elt),
    disabled: elt.disabled,
    name: elt.name,
    type: elt.type,
    validation_message: elt.validationMessage,
    will_validate: elt.willValidate,
  };
}

export function extractHTMLFormElement(elt: HTMLFormElement) {
  return {
    ...extractHTMLElementBase(elt),
    accept_charset: elt.acceptCharset,
    action: elt.action,
    autocomplete: elt.autocomplete,
    encoding: elt.encoding,
    enctype: elt.enctype,
    length: elt.length,
    method: elt.method,
    name: elt.name,
    no_validate: elt.noValidate,
    target: elt.target,
    rel: elt.rel,
  };
}

export function extractHTMLIFrameElement(elt: HTMLIFrameElement) {
  return {
    ...extractHTMLElementBase(elt),
    allow: elt.allow,
    allow_fullscreen: elt.allowFullscreen,
    height: elt.height,
    name: elt.name,
    referrer_policy: elt.referrerPolicy,
    src: elt.src,
    srcdoc: elt.srcdoc,
    width: elt.width,
    align: elt.align,
    frame_border: elt.frameBorder,
    long_desc: elt.longDesc,
    margin_height: elt.marginHeight,
    margin_width: elt.marginWidth,
    scrolling: elt.scrolling,
    sandbox: elt.sandbox,
  };
}

export function extractHTMLImageElement(elt: HTMLImageElement) {
  return {
    ...extractHTMLElementBase(elt),
    alt: elt.alt,
    cross_origin: elt.crossOrigin,
    decoding: elt.decoding,
    height: elt.height,
    is_map: elt.isMap,
    loading: elt.loading,
    natural_height: elt.naturalHeight,
    natural_width: elt.naturalWidth,
    referrer_policy: elt.referrerPolicy,
    sizes: elt.sizes,
    src: elt.src,
    srcset: elt.srcset,
    use_map: elt.useMap,
    width: elt.width,
    align: elt.align,
    border: elt.border,
    complete: elt.complete,
    hspace: elt.hspace,
    long_desc: elt.longDesc,
    lowsrc: elt.lowsrc,
    name: elt.name,
    vspace: elt.vspace,
    x: elt.x,
    y: elt.y,
    fetch_priority: elt.fetchPriority,
  };
}

export function extractHTMLInputElement(elt: HTMLInputElement) {
  return {
    ...extractHTMLElementBase(elt),
    accept: elt.accept,
    alt: elt.alt,
    autocomplete: elt.autocomplete,
    checked: elt.checked,
    default_checked: elt.defaultChecked,
    default_value: elt.defaultValue,
    dir_name: elt.dirName,
    disabled: elt.disabled,
    height: elt.height,
    indeterminate: elt.indeterminate,
    max: elt.max,
    max_length: elt.maxLength,
    min: elt.min,
    min_length: elt.minLength,
    multiple: elt.multiple,
    name: elt.name,
    pattern: elt.pattern,
    placeholder: elt.placeholder,
    read_only: elt.readOnly,
    required: elt.required,
    selection_direction: elt.selectionDirection,
    selection_end: elt.selectionEnd,
    selection_start: elt.selectionStart,
    size: elt.size,
    src: elt.src,
    step: elt.step,
    type: elt.type,
    value: elt.value,
    value_as_number: elt.valueAsNumber,
    width: elt.width,
    align: elt.align,
    capture: elt.capture,
    form_action: elt.formAction,
    form_enctype: elt.formEnctype,
    form_method: elt.formMethod,
    form_no_validate: elt.formNoValidate,
    form_target: elt.formTarget,
    use_map: elt.useMap,
    validation_message: elt.validationMessage,
    will_validate: elt.willValidate,
    popover_target_action: elt.popoverTargetAction,
  };
}

export function extractHTMLLabelElement(elt: HTMLLabelElement) {
  return {
    ...extractHTMLElementBase(elt),
    html_for: elt.htmlFor,
  };
}

export function extractHTMLLiElement(elt: HTMLLIElement) {
  return {
    ...extractHTMLElementBase(elt),
    value: elt.value,
    type: elt.type,
  };
}

export function extractHTMLLinkElement(elt: HTMLLinkElement) {
  return {
    ...extractHTMLElementBase(elt),
    as: elt.as,
    cross_origin: elt.crossOrigin,
    disabled: elt.disabled,
    fetch_priority: elt.fetchPriority,
    href: elt.href,
    href_lang: elt.hreflang,
    image_sizes: elt.imageSizes,
    image_srcset: elt.imageSrcset,
    integrity: elt.integrity,
    media: elt.media,
    referrer_policy: elt.referrerPolicy,
    rel: elt.rel,
    type: elt.type,
    charset: elt.charset,
    rev: elt.rev,
    target: elt.target,
    sizes: elt.sizes,
  };
}

export function extractHTMLMapElement(elt: HTMLMapElement) {
  return {
    ...extractHTMLElementBase(elt),
    name: elt.name,
  };
}

export function extractHTMLMeterElement(elt: HTMLMeterElement) {
  return {
    ...extractHTMLElementBase(elt),
    high: elt.high,
    low: elt.low,
    max: elt.max,
    min: elt.min,
    optimum: elt.optimum,
    value: elt.value,
  };
}

export function extractHTMLModElement(elt: HTMLModElement) {
  return {
    ...extractHTMLElementBase(elt),
    cite: elt.cite,
    dateTime: elt.dateTime,
  };
}

export function extractHTMLOListElement(elt: HTMLOListElement) {
  return {
    ...extractHTMLElementBase(elt),
    reversed: elt.reversed,
    start: elt.start,
    type: elt.type,
    compact: elt.compact,
  };
}

export function extractHTMLObjectElement(elt: HTMLObjectElement) {
  return {
    ...extractHTMLElementBase(elt),
    data: elt.data,
    // disabled: elt.disabled,
    height: elt.height,
    name: elt.name,
    type: elt.type,
    use_map: elt.useMap,
    width: elt.width,
    validation_message: elt.validationMessage,
    will_validate: elt.willValidate,
    align: elt.align,
    archive: elt.archive,
    border: elt.border,
    code: elt.code,
    code_base: elt.codeBase,
    code_type: elt.codeType,
    declare: elt.declare,
    hspace: elt.hspace,
    standby: elt.standby,
    vspace: elt.vspace,
  };
}

export function extractHTMLOptGroupElement(elt: HTMLOptGroupElement) {
  return {
    ...extractHTMLElementBase(elt),
    disabled: elt.disabled,
    label: elt.label,
  };
}

export function extractHTMLOptionElement(elt: HTMLOptionElement) {
  return {
    ...extractHTMLElementBase(elt),
    default_selected: elt.defaultSelected,
    disabled: elt.disabled,
    index: elt.index,
    label: elt.label,
    selected: elt.selected,
    text: elt.text,
    value: elt.value,
  };
}

export function extractHTMLOutputElement(elt: HTMLOutputElement) {
  return {
    ...extractHTMLElementBase(elt),
    default_value: elt.defaultValue,
    name: elt.name,
    type: elt.type,
    value: elt.value,
    html_for: elt.htmlFor,
    validation_message: elt.validationMessage,
    will_validate: elt.willValidate,
  };
}

export function extractHTMLProgressElement(elt: HTMLProgressElement) {
  return {
    ...extractHTMLElementBase(elt),
    max: elt.max,
    position: elt.position,
    value: elt.value,
  };
}

export function extractHTMLQuoteElement(elt: HTMLQuoteElement) {
  return {
    ...extractHTMLElementBase(elt),
    cite: elt.cite,
  };
}

export function extractHTMLCiteElement(elt: HTMLElement) {
  return {
    ...extractHTMLElementBase(elt),
  };
}

export function extractHTMLScriptElement(elt: HTMLScriptElement) {
  return {
    ...extractHTMLElementBase(elt),
    async_: elt.async,
    cross_origin: elt.crossOrigin,
    defer: elt.defer,
    fetch_priority: elt.fetchPriority,
    integrity: elt.integrity,
    no_module: elt.noModule,
    referrer_policy: elt.referrerPolicy,
    src: elt.src,
    text: elt.text,
    type: elt.type,
    charset: elt.charset,
    event: (elt as any).event,
    html_for: (elt as any).htmlFor,
  };
}

export function extractHTMLSelectElement(elt: HTMLSelectElement) {
  return {
    ...extractHTMLElementBase(elt),
    autocomplete: elt.autocomplete,
    disabled: elt.disabled,
    length: elt.length,
    multiple: elt.multiple,
    name: elt.name,
    required: elt.required,
    selected_index: elt.selectedIndex,
    size: elt.size,
    type: elt.type,
    value: elt.value,
    validation_message: elt.validationMessage,
    will_validate: elt.willValidate,
  };
}

export function extractHTMLSlotElement(elt: HTMLSlotElement) {
  return {
    ...extractHTMLElementBase(elt),
    name: elt.name,
  };
}

export function extractHTMLSourceElement(elt: HTMLSourceElement) {
  return {
    ...extractHTMLElementBase(elt),
    height: elt.height,
    media: elt.media,
    sizes: elt.sizes,
    src: elt.src,
    srcset: elt.srcset,
    type: elt.type,
    width: elt.width,
  };
}

export function extractHTMLTableCaptionElement(elt: HTMLTableCaptionElement) {
  return {
    ...extractHTMLElementBase(elt),
    align: elt.align,
  };
}

export function extractHTMLTableCellElement(elt: HTMLTableCellElement) {
  return {
    ...extractHTMLElementBase(elt),
    abbr: elt.abbr,
    cell_index: elt.cellIndex,
    col_span: elt.colSpan,
    headers: elt.headers,
    row_span: elt.rowSpan,
    scope: elt.scope,
    align: elt.align,
    axis: elt.axis,
    bg_color: elt.bgColor,
    ch: elt.ch,
    ch_off: elt.chOff,
    height: elt.height,
    no_wrap: elt.noWrap,
    v_align: elt.vAlign,
    width: elt.width,
  };
}

export function extractHTMLTableColElement(elt: HTMLTableColElement) {
  return {
    ...extractHTMLElementBase(elt),
    span: elt.span,
    align: elt.align,
    ch: elt.ch,
    ch_off: elt.chOff,
    v_align: elt.vAlign,
    width: elt.width,
  };
}

export function extractHTMLTableElement(elt: HTMLTableElement) {
  return {
    ...extractHTMLElementBase(elt),
    // caption: elt.caption ? extractHTMLTableCaptionElement(elt.caption) : null,
    align: elt.align,
    bg_color: elt.bgColor,
    border: elt.border,
    cell_padding: elt.cellPadding,
    cell_spacing: elt.cellSpacing,
    frame: elt.frame,
    rules: elt.rules,
    summary: elt.summary,
    width: elt.width,
  };
}

export function extractHTMLTableRowElement(elt: HTMLTableRowElement) {
  return {
    ...extractHTMLElementBase(elt),
    row_index: elt.rowIndex,
    section_row_index: elt.sectionRowIndex,
    align: elt.align,
    bg_color: elt.bgColor,
    ch: elt.ch,
    ch_off: elt.chOff,
    v_align: elt.vAlign,
  };
}

export function extractHTMLTableSectionElement(elt: HTMLTableSectionElement) {
  return {
    ...extractHTMLElementBase(elt),
    align: elt.align,
    ch: elt.ch,
    ch_off: elt.chOff,
    v_align: elt.vAlign,
  };
}

export function extractHTMLTemplateElement(elt: HTMLTemplateElement) {
  return {
    ...extractHTMLElementBase(elt),
  };
}

export function extractHTMLTextAreaElement(elt: HTMLTextAreaElement) {
  return {
    ...extractHTMLElementBase(elt),
    autocomplete: elt.autocomplete,
    cols: elt.cols,
    default_value: elt.defaultValue,
    dir_name: elt.dirName,
    disabled: elt.disabled,
    max_length: elt.maxLength,
    min_length: elt.minLength,
    name: elt.name,
    placeholder: elt.placeholder,
    read_only: elt.readOnly,
    required: elt.required,
    rows: elt.rows,
    selection_direction: elt.selectionDirection,
    selection_end: elt.selectionEnd,
    selection_start: elt.selectionStart,
    value: elt.value,
    wrap: elt.wrap,
    text_length: elt.textLength,
    validation_message: elt.validationMessage,
    will_validate: elt.willValidate,
  };
}

export function extractHTMLTimeElement(elt: HTMLTimeElement) {
  return {
    ...extractHTMLElementBase(elt),
    datetime: elt.dateTime,
  };
}

export function extractHTMLTrackElement(elt: HTMLTrackElement) {
  return {
    ...extractHTMLElementBase(elt),
    default: elt.default,
    kind: elt.kind,
    label: elt.label,
    ready_state: elt.readyState,
    src: elt.src,
    srclang: elt.srclang,
  };
}

export function extractHTMLVideoElement(elt: HTMLVideoElement) {
  return {
    ...extractHTMLMediaElement(elt),
    height: elt.height,
    poster: elt.poster,
    video_height: elt.videoHeight,
    video_width: elt.videoWidth,
    width: elt.width,
    plays_inline: elt.playsInline,
  };
}

export function extractHTMLBRElement(elt: HTMLBRElement) {
  return {
    ...extractHTMLElementBase(elt),
    clear: elt.clear,
  };
}

export function extractHTMLBaseElement(elt: HTMLBaseElement) {
  return {
    ...extractHTMLElementBase(elt),
    href: elt.href,
    target: elt.target,
  };
}

export function extractHTMLBodyElement(elt: HTMLBodyElement) {
  return {
    ...extractHTMLElementBase(elt),
    a_link: elt.aLink,
    background: elt.background,
    bg_color: elt.bgColor,
    link: elt.link,
    text: elt.text,
    v_link: elt.vLink,
  };
}

export function extractHTMLDListElement(elt: HTMLDListElement) {
  return {
    ...extractHTMLElementBase(elt),
    compact: elt.compact,
  };
}

export function extractHTMLDetailsElement(elt: HTMLDetailsElement) {
  return {
    ...extractHTMLElementBase(elt),
    open: elt.open,
  };
}

export function extractHTMLDialogElement(elt: HTMLDialogElement) {
  return {
    ...extractHTMLElementBase(elt),
    open: elt.open,
    return_value: elt.returnValue,
  };
}

export function extractHTMLDivElement(elt: HTMLDivElement) {
  return {
    ...extractHTMLElementBase(elt),
    align: elt.align,
  };
}

export function extractHTMLHeadElement(elt: HTMLHeadElement) {
  return {
    ...extractHTMLElementBase(elt),
  };
}

export function extractHTMLHeadingElement(elt: HTMLHeadingElement) {
  return {
    ...extractHTMLElementBase(elt),
    align: elt.align,
  };
}

export function extractHTMLHRElement(elt: HTMLHRElement) {
  return {
    ...extractHTMLElementBase(elt),
    align: elt.align,
    color: elt.color,
    no_shade: elt.noShade,
    size: elt.size,
    width: elt.width,
  };
}

export function extractHTMLHtmlElement(elt: HTMLHtmlElement) {
  return {
    ...extractHTMLElementBase(elt),
    version: elt.version,
  };
}

export function extractHTMLMenuElement(elt: HTMLMenuElement) {
  return {
    ...extractHTMLElementBase(elt),
  };
}

export function extractHTMLMetaElement(elt: HTMLMetaElement) {
  return {
    ...extractHTMLElementBase(elt),
    content: elt.content,
    http_equiv: elt.httpEquiv,
    name: elt.name,
    scheme: elt.scheme,
  };
}

export function extractHTMLParagraphElement(elt: HTMLParagraphElement) {
  return {
    ...extractHTMLElementBase(elt),
    align: elt.align,
  };
}

export function extractHTMLPictureElement(elt: HTMLPictureElement) {
  return {
    ...extractHTMLElementBase(elt),
  };
}

export function extractHTMLPreElement(elt: HTMLPreElement) {
  return {
    ...extractHTMLElementBase(elt),
    width: elt.width,
  };
}

export function extractHTMLSpanElement(elt: HTMLSpanElement) {
  return {
    ...extractHTMLElementBase(elt),
  };
}

export function extractHTMLStyleElement(elt: HTMLStyleElement) {
  return {
    ...extractHTMLElementBase(elt),
    media: elt.media,
    type: elt.type,
    disabled: elt.disabled,
  };
}

export function extractHTMLTitleElement(elt: HTMLTitleElement) {
  return {
    ...extractHTMLElementBase(elt),
    text: elt.text,
  };
}

export function extractHTMLUListElement(elt: HTMLUListElement) {
  return {
    ...extractHTMLElementBase(elt),
    compact: elt.compact,
    type: elt.type,
  };
}

export function extractHTMLElement(elt: HTMLElement): object {
  const tagName = elt.tagName.toUpperCase();

  switch (tagName) {
    case "A":
      return extractHTMLAnchorElement(elt as HTMLAnchorElement);
    case "AREA":
      return extractHTMLAreaElement(elt as HTMLAreaElement);
    case "AUDIO":
      return extractHTMLAudioElement(elt as HTMLAudioElement);
    case "BASE":
      return extractHTMLBaseElement(elt as HTMLBaseElement);
    case "BLOCKQUOTE":
    case "Q":
      return extractHTMLQuoteElement(elt as HTMLQuoteElement);
    case "BODY":
      return extractHTMLBodyElement(elt as HTMLBodyElement);
    case "BR":
      return extractHTMLBRElement(elt as HTMLBRElement);
    case "BUTTON":
      return extractHTMLButtonElement(elt as HTMLButtonElement);
    case "CANVAS": // Placeholder - no specific function yet
      return extractHTMLElementBase(elt);
    case "CAPTION":
      return extractHTMLTableCaptionElement(elt as HTMLTableCaptionElement);
    case "CITE":
      return extractHTMLCiteElement(elt); // Uses base HTMLElement
    case "COL":
    case "COLGROUP":
      return extractHTMLTableColElement(elt as HTMLTableColElement);
    case "DATA":
      return extractHTMLDataElement(elt as HTMLDataElement);
    case "DETAILS":
      return extractHTMLDetailsElement(elt as HTMLDetailsElement);
    case "DIALOG":
      return extractHTMLDialogElement(elt as HTMLDialogElement);
    case "DIV":
      return extractHTMLDivElement(elt as HTMLDivElement);
    case "DL":
      return extractHTMLDListElement(elt as HTMLDListElement);
    case "EMBED":
      return extractHTMLEmbedElement(elt as HTMLEmbedElement);
    case "FIELDSET":
      return extractHTMLFieldSetElement(elt as HTMLFieldSetElement);
    case "FORM":
      return extractHTMLFormElement(elt as HTMLFormElement);
    case "H1":
    case "H2":
    case "H3":
    case "H4":
    case "H5":
    case "H6":
      return extractHTMLHeadingElement(elt as HTMLHeadingElement);
    case "HEAD":
      return extractHTMLHeadElement(elt as HTMLHeadElement);
    case "HR":
      return extractHTMLHRElement(elt as HTMLHRElement);
    case "HTML":
      return extractHTMLHtmlElement(elt as HTMLHtmlElement);
    case "IFRAME":
      return extractHTMLIFrameElement(elt as HTMLIFrameElement);
    case "IMG":
      return extractHTMLImageElement(elt as HTMLImageElement);
    case "INPUT":
      return extractHTMLInputElement(elt as HTMLInputElement);
    case "LABEL":
      return extractHTMLLabelElement(elt as HTMLLabelElement);
    case "LI":
      return extractHTMLLiElement(elt as HTMLLIElement);
    case "LINK":
      return extractHTMLLinkElement(elt as HTMLLinkElement);
    case "MAP":
      return extractHTMLMapElement(elt as HTMLMapElement);
    case "MENU":
      return extractHTMLMenuElement(elt as HTMLMenuElement);
    case "META":
      return extractHTMLMetaElement(elt as HTMLMetaElement);
    case "METER":
      return extractHTMLMeterElement(elt as HTMLMeterElement);
    case "INS":
    case "DEL":
      return extractHTMLModElement(elt as HTMLModElement);
    case "OBJECT":
      return extractHTMLObjectElement(elt as HTMLObjectElement);
    case "OL":
      return extractHTMLOListElement(elt as HTMLOListElement);
    case "OPTGROUP":
      return extractHTMLOptGroupElement(elt as HTMLOptGroupElement);
    case "OPTION":
      return extractHTMLOptionElement(elt as HTMLOptionElement);
    case "OUTPUT":
      return extractHTMLOutputElement(elt as HTMLOutputElement);
    case "P":
      return extractHTMLParagraphElement(elt as HTMLParagraphElement);
    case "PICTURE":
      return extractHTMLPictureElement(elt as HTMLPictureElement);
    case "PRE":
      return extractHTMLPreElement(elt as HTMLPreElement);
    case "PROGRESS":
      return extractHTMLProgressElement(elt as HTMLProgressElement);
    case "SCRIPT":
      return extractHTMLScriptElement(elt as HTMLScriptElement);
    case "SELECT":
      return extractHTMLSelectElement(elt as HTMLSelectElement);
    case "SLOT":
      return extractHTMLSlotElement(elt as HTMLSlotElement);
    case "SOURCE":
      return extractHTMLSourceElement(elt as HTMLSourceElement);
    case "SPAN":
      return extractHTMLSpanElement(elt as HTMLSpanElement);
    case "STYLE":
      return extractHTMLStyleElement(elt as HTMLStyleElement);
    case "TABLE":
      return extractHTMLTableElement(elt as HTMLTableElement);
    case "TBODY":
    case "THEAD":
    case "TFOOT":
      return extractHTMLTableSectionElement(elt as HTMLTableSectionElement);
    case "TD":
    case "TH":
      return extractHTMLTableCellElement(elt as HTMLTableCellElement);
    case "TEMPLATE":
      return extractHTMLTemplateElement(elt as HTMLTemplateElement);
    case "TEXTAREA":
      return extractHTMLTextAreaElement(elt as HTMLTextAreaElement);
    case "TIME":
      return extractHTMLTimeElement(elt as HTMLTimeElement);
    case "TITLE":
      return extractHTMLTitleElement(elt as HTMLTitleElement);
    case "TR":
      return extractHTMLTableRowElement(elt as HTMLTableRowElement);
    case "TRACK":
      return extractHTMLTrackElement(elt as HTMLTrackElement);
    case "UL":
      return extractHTMLUListElement(elt as HTMLUListElement);
    case "VIDEO":
      return extractHTMLVideoElement(elt as HTMLVideoElement);
    // Add other tag names as needed
    default:
      throw new Error(
        `Unexpected HTML element tag: ${elt.tagName} (update .web/custom/serialize.ts)`
      );
  }
}

export function extractSyntheticEvent(evt: React.SyntheticEvent) {
  return {
    // Very slow right now, to investigate
    // nativeEvent: cleanForSerialization(evt.nativeEvent),
    // use extractHTMLElement in every place where a HTMLElement or generic TElement type is used
    target: extractHTMLElement(evt.target as HTMLElement), // I think this is true for all or purposes
    // currentTarget is often not available in Reflex event handlers
    bubbles: evt.bubbles,
    cancelable: evt.cancelable,
    default_prevented: evt.defaultPrevented,
    event_phase: evt.eventPhase,
    is_trusted: evt.isTrusted,
    timestamp: evt.timeStamp,
    type: evt.type,
  };
}

export function extractUIEvent(evt: React.UIEvent) {
  return { ...extractSyntheticEvent(evt), detail: evt.detail };
}

export function extractMouseEvent(evt: React.MouseEvent) {
  return {
    ...extractUIEvent(evt),

    alt_key: evt.altKey,
    button: evt.button,
    buttons: evt.buttons,
    client_x: evt.clientX,
    client_y: evt.clientY,
    ctrl_key: evt.ctrlKey,
    meta_key: evt.metaKey,
    movement_x: evt.movementX,
    movement_y: evt.movementY,
    page_x: evt.pageX,
    page_y: evt.pageY,
    related_target: evt.relatedTarget
      ? extractHTMLElement(evt.relatedTarget as HTMLElement)
      : null,
    screen_x: evt.screenX,
    screen_y: evt.screenY,
    shift_key: evt.shiftKey,
  };
}

export function extractClipboardEvent(evt: React.ClipboardEvent) {
  return {
    ...extractSyntheticEvent(evt),
    clipboard_data: extractDataTransfer(evt.clipboardData),
  };
}

export function extractCompositionEvent(evt: React.CompositionEvent) {
  return {
    ...extractSyntheticEvent(evt),
    data: evt.data,
  };
}

export function extractDragEvent(evt: React.DragEvent) {
  return {
    ...extractMouseEvent(evt),
    data_transfer: extractDataTransfer(evt.dataTransfer),
  };
}

export function extractPointerEvent(evt: React.PointerEvent) {
  return {
    ...extractMouseEvent(evt),
    pointer_id: evt.pointerId,
    pressure: evt.pressure,
    tangential_pressure: evt.tangentialPressure,
    tilt_x: evt.tiltX,
    tilt_y: evt.tiltY,
    twist: evt.twist,
    width: evt.width,
    height: evt.height,
    pointer_type: evt.pointerType,
    is_primary: evt.isPrimary,
  };
}

export function extractFocusEvent(evt: React.FocusEvent) {
  return {
    ...extractSyntheticEvent(evt),
    // target: extractHTMLElement(evt.target as HTMLElement),
    related_target: evt.relatedTarget
      ? extractHTMLElement(evt.relatedTarget as HTMLElement)
      : null,
  };
}

export function extractFormEvent(evt: React.FormEvent) {
  return extractSyntheticEvent(evt);
}

export function extractInvalidEvent(evt: React.InvalidEvent) {
  return extractSyntheticEvent(evt);
}

export function extractChangeEvent(evt: React.ChangeEvent) {
  return extractFormEvent(evt);
}

export function extractKeyboardEvent(evt: React.KeyboardEvent) {
  return {
    ...extractUIEvent(evt),
    alt_key: evt.altKey,
    ctrl_key: evt.ctrlKey,
    code: evt.code,
    key: evt.key,
    locale: evt.locale,
    location: evt.location,
    meta_key: evt.metaKey,
    repeat: evt.repeat,
    shift_key: evt.shiftKey,
  };
}

export function extractTouchEvent(evt: React.TouchEvent) {
  return {
    ...extractUIEvent(evt),
    alt_key: evt.altKey,
    changed_touches: Array.from(evt.changedTouches).map((touch) => ({
      target: extractHTMLElement(touch.target as HTMLElement),
      identifier: touch.identifier,
      screen_x: touch.screenX,
      screen_y: touch.screenY,
      client_x: touch.clientX,
      client_y: touch.clientY,
      page_x: touch.pageX,
      page_y: touch.pageY,
    })),
    ctrl_key: evt.ctrlKey,
    meta_key: evt.metaKey,
    shift_key: evt.shiftKey,
    target_touches: Array.from(evt.targetTouches).map((touch) => ({
      target: extractHTMLElement(touch.target as HTMLElement),
      identifier: touch.identifier,
      screen_x: touch.screenX,
      screen_y: touch.screenY,
      client_x: touch.clientX,
      client_y: touch.clientY,
      page_x: touch.pageX,
      page_y: touch.pageY,
    })),
    touches: Array.from(evt.touches).map((touch) => ({
      target: extractHTMLElement(touch.target as HTMLElement),
      identifier: touch.identifier,
      screen_x: touch.screenX,
      screen_y: touch.screenY,
      client_x: touch.clientX,
      client_y: touch.clientY,
      page_x: touch.pageX,
      page_y: touch.pageY,
    })),
  };
}

export function extractWheelEvent(evt: React.WheelEvent) {
  return {
    ...extractMouseEvent(evt),
    delta_mode: evt.deltaMode,
    delta_x: evt.deltaX,
    delta_y: evt.deltaY,
    delta_z: evt.deltaZ,
  };
}

export function extractAnimationEvent(evt: React.AnimationEvent) {
  return {
    ...extractSyntheticEvent(evt),
    animation_name: evt.animationName,
    elapsed_time: evt.elapsedTime,
    pseudo_element: evt.pseudoElement,
  };
}

export function extractToggleEvent(evt: React.ToggleEvent) {
  return {
    ...extractSyntheticEvent(evt),
    old_state: evt.oldState,
    new_state: evt.newState,
  };
}

export function extractTransitionEvent(evt: React.TransitionEvent) {
  return {
    ...extractSyntheticEvent(evt),
    elapsed_time: evt.elapsedTime,
    property_name: evt.propertyName,
    pseudo_element: evt.pseudoElement,
  };
}

// Helper function to extract DataTransfer properties
function extractDataTransfer(dt: DataTransfer | null): object | null {
  if (!dt) {
    return null;
  }
  const items = [];
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i];
      items.push({
        kind: item.kind,
        type: item.type,
      });
    }
  }
  return {
    drop_effect: dt.dropEffect,
    effect_allowed: dt.effectAllowed,
    items: items,
    types: Array.from(dt.types || []),
  };
}

const eventExtractorMap: { [key: string]: (evt: any) => object } = {
  // Pointer Events
  pointerdown: extractPointerEvent,
  pointermove: extractPointerEvent,
  pointerup: extractPointerEvent,
  pointercancel: extractPointerEvent,
  gotpointercapture: extractPointerEvent,
  lostpointercapture: extractPointerEvent,
  pointerenter: extractPointerEvent,
  pointerleave: extractPointerEvent,
  pointerover: extractPointerEvent,
  pointerout: extractPointerEvent,

  // Mouse Events
  click: extractMouseEvent,
  contextmenu: extractMouseEvent,
  dblclick: extractMouseEvent,
  mousedown: extractMouseEvent,
  mouseenter: extractMouseEvent,
  mouseleave: extractMouseEvent,
  mousemove: extractMouseEvent,
  mouseout: extractMouseEvent,
  mouseover: extractMouseEvent,
  mouseup: extractMouseEvent,

  // Drag Events
  drag: extractDragEvent,
  dragend: extractDragEvent,
  dragenter: extractDragEvent,
  dragexit: extractDragEvent,
  dragleave: extractDragEvent,
  dragover: extractDragEvent,
  dragstart: extractDragEvent,
  drop: extractDragEvent,

  // Keyboard Events
  keydown: extractKeyboardEvent,
  keypress: extractKeyboardEvent,
  keyup: extractKeyboardEvent,

  // Focus Events
  focus: extractFocusEvent,
  blur: extractFocusEvent,

  // Form Events
  change: extractChangeEvent,
  input: extractChangeEvent, // often used with change
  invalid: extractInvalidEvent,
  reset: extractFormEvent,
  submit: extractFormEvent,

  // Clipboard Events
  copy: extractClipboardEvent,
  cut: extractClipboardEvent,
  paste: extractClipboardEvent,

  // Composition Events
  compositionend: extractCompositionEvent,
  compositionstart: extractCompositionEvent,
  compositionupdate: extractCompositionEvent,

  // Touch Events
  touchcancel: extractTouchEvent,
  touchend: extractTouchEvent,
  touchmove: extractTouchEvent,
  touchstart: extractTouchEvent,

  // UI Events
  scroll: extractUIEvent,

  // Wheel Events
  wheel: extractWheelEvent,

  // Animation Events
  animationstart: extractAnimationEvent,
  animationend: extractAnimationEvent,
  animationiteration: extractAnimationEvent,

  // Transition Events
  transitionend: extractTransitionEvent,

  // Toggle Events
  toggle: extractToggleEvent,
};

export function extractEvent(value: any): any {
  // Duck-typing for React's SyntheticEvent.
  // We check for properties that are unique to synthetic events.
  if (
    value &&
    typeof value === "object" &&
    "nativeEvent" in value &&
    typeof value.isDefaultPrevented === "function"
  ) {
    const evt = value as React.SyntheticEvent;
    // The `type` property is crucial for the lookup.
    if (typeof evt.type !== "string") {
      return value;
    }

    const extractor = eventExtractorMap[evt.type.toLowerCase()];
    if (extractor) {
      return extractor(evt);
    }

    // Fallback for unknown but event-like types
    console.warn(
      `No specific extractor for event type "${evt.type}". Using synthetic.`
    );
    return extractSyntheticEvent(evt);
  }

  // If it's not a duck-typed event, return it as is.
  return value;
}
