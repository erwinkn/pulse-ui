/* === IMPORTANT === */

import { extractHTMLElement } from "./elements";
import { createExtractor } from "./extractor";

const SYNTHETIC_KEYS = [
  "target",
  "bubbles",
  "cancelable",
  "defaultPrevented",
  "eventPhase",
  "isTrusted",
  "timeStamp",
  "type",
] as const satisfies readonly (keyof React.SyntheticEvent)[];

const UI_KEYS = [
  ...SYNTHETIC_KEYS,
  "detail",
] as const satisfies readonly (keyof React.UIEvent)[];

const MOUSE_KEYS = [
  ...UI_KEYS,
  "altKey",
  "button",
  "buttons",
  "clientX",
  "clientY",
  "ctrlKey",
  "metaKey",
  "movementX",
  "movementY",
  "pageX",
  "pageY",
  "screenX",
  "screenY",
  "shiftKey",
] as const satisfies readonly (keyof React.MouseEvent)[];

const POINTER_KEYS = [
  ...MOUSE_KEYS,
  "pointerId",
  "pressure",
  "tangentialPressure",
  "tiltX",
  "tiltY",
  "twist",
  "width",
  "height",
  "pointerType",
  "isPrimary",
] as const satisfies readonly (keyof React.PointerEvent)[];

const syntheticExtractor = createExtractor<React.SyntheticEvent>()(
  SYNTHETIC_KEYS,
  {
    target: (e) => extractHTMLElement(e.target as HTMLElement),
  }
);

const uiExtractor = createExtractor<React.UIEvent>()(UI_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
});

const mouseExtractor = createExtractor<React.MouseEvent>()(MOUSE_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
  relatedTarget: (e) =>
    e.relatedTarget ? extractHTMLElement(e.relatedTarget as HTMLElement) : null,
});

const clipboardExtractor = createExtractor<React.ClipboardEvent>()(
  SYNTHETIC_KEYS,
  {
    target: (e) => extractHTMLElement(e.target as HTMLElement),
    clipboardData: (e) => extractDataTransfer(e.clipboardData),
  }
);

const compositionExtractor = createExtractor<React.CompositionEvent>()(
  [...SYNTHETIC_KEYS, "data"] as const,
  { target: (e) => extractHTMLElement(e.target as HTMLElement) }
);

const dragExtractor = createExtractor<React.DragEvent>()(MOUSE_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
  relatedTarget: (e) =>
    e.relatedTarget ? extractHTMLElement(e.relatedTarget as HTMLElement) : null,
  dataTransfer: (e) => extractDataTransfer(e.dataTransfer),
});

const pointerExtractor = createExtractor<React.PointerEvent>()(POINTER_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
  relatedTarget: (e) =>
    e.relatedTarget ? extractHTMLElement(e.relatedTarget as HTMLElement) : null,
});

const focusExtractor = createExtractor<React.FocusEvent>()(SYNTHETIC_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
  relatedTarget: (e) =>
    e.relatedTarget ? extractHTMLElement(e.relatedTarget as HTMLElement) : null,
});

const formExtractor = createExtractor<React.FormEvent>()(SYNTHETIC_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
});

const invalidExtractor = createExtractor<React.InvalidEvent>()(SYNTHETIC_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
});

const changeExtractor = createExtractor<React.ChangeEvent>()(SYNTHETIC_KEYS, {
  target: (e) => extractHTMLElement(e.target as HTMLElement),
});

const keyboardExtractor = createExtractor<React.KeyboardEvent>()(
  [
    ...UI_KEYS,
    "altKey",
    "ctrlKey",
    "code",
    "key",
    "locale",
    "location",
    "metaKey",
    "repeat",
    "shiftKey",
  ] as const,
  { target: (e) => extractHTMLElement(e.target as HTMLElement) }
);

const touchExtractor = createExtractor<React.TouchEvent>()(
  [
    ...UI_KEYS,
    "altKey",
    "ctrlKey",
    "metaKey",
    "shiftKey",
    "changedTouches",
    "targetTouches",
    "touches",
  ] as const,
  {
    target: (e) => extractHTMLElement(e.target as HTMLElement),
    changedTouches: (e) => mapTouchList(e.changedTouches),
    targetTouches: (e) => mapTouchList(e.targetTouches),
    touches: (e) => mapTouchList(e.touches),
  }
);

const wheelExtractor = createExtractor<React.WheelEvent>()(
  [...MOUSE_KEYS, "deltaMode", "deltaX", "deltaY", "deltaZ"] as const,
  {
    target: (e) => extractHTMLElement(e.target as HTMLElement),
    relatedTarget: (e) =>
      e.relatedTarget
        ? extractHTMLElement(e.relatedTarget as HTMLElement)
        : null,
  }
);

const animationExtractor = createExtractor<React.AnimationEvent>()(
  [...SYNTHETIC_KEYS, "animationName", "elapsedTime", "pseudoElement"] as const,
  { target: (e) => extractHTMLElement(e.target as HTMLElement) }
);

const toggleExtractor = createExtractor<React.ToggleEvent>()(
  [...SYNTHETIC_KEYS, "oldState", "newState"] as const,
  { target: (e) => extractHTMLElement(e.target as HTMLElement) }
);

const transitionExtractor = createExtractor<React.TransitionEvent>()(
  [...SYNTHETIC_KEYS, "elapsedTime", "propertyName", "pseudoElement"] as const,
  { target: (e) => extractHTMLElement(e.target as HTMLElement) }
);

function mapTouchList(list: any): any[] {
  return Array.from(list as ArrayLike<any>).map((touch: any) => ({
    target: extractHTMLElement(touch.target as HTMLElement),
    identifier: touch.identifier,
    screenX: touch.screenX,
    screenY: touch.screenY,
    clientX: touch.clientX,
    clientY: touch.clientY,
    pageX: touch.pageX,
    pageY: touch.pageY,
  }));
}

// Helper function to extract DataTransfer properties
function extractDataTransfer(dt: DataTransfer | null): object | null {
  if (!dt) {
    return null;
  }
  const items = [];
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i]!;
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
  pointerdown: pointerExtractor,
  pointermove: pointerExtractor,
  pointerup: pointerExtractor,
  pointercancel: pointerExtractor,
  gotpointercapture: pointerExtractor,
  lostpointercapture: pointerExtractor,
  pointerenter: pointerExtractor,
  pointerleave: pointerExtractor,
  pointerover: pointerExtractor,
  pointerout: pointerExtractor,

  // Mouse Events
  click: mouseExtractor,
  contextmenu: mouseExtractor,
  dblclick: mouseExtractor,
  mousedown: mouseExtractor,
  mouseenter: mouseExtractor,
  mouseleave: mouseExtractor,
  mousemove: mouseExtractor,
  mouseout: mouseExtractor,
  mouseover: mouseExtractor,
  mouseup: mouseExtractor,

  // Drag Events
  drag: dragExtractor,
  dragend: dragExtractor,
  dragenter: dragExtractor,
  dragexit: dragExtractor,
  dragleave: dragExtractor,
  dragover: dragExtractor,
  dragstart: dragExtractor,
  drop: dragExtractor,

  // Keyboard Events
  keydown: keyboardExtractor,
  keypress: keyboardExtractor,
  keyup: keyboardExtractor,

  // Focus Events
  focus: focusExtractor,
  blur: focusExtractor,

  // Form Events
  change: changeExtractor,
  input: changeExtractor, // often used with change
  invalid: invalidExtractor,
  reset: formExtractor,
  submit: formExtractor,

  // Clipboard Events
  copy: clipboardExtractor,
  cut: clipboardExtractor,
  paste: clipboardExtractor,

  // Composition Events
  compositionend: compositionExtractor,
  compositionstart: compositionExtractor,
  compositionupdate: compositionExtractor,

  // Touch Events
  touchcancel: touchExtractor,
  touchend: touchExtractor,
  touchmove: touchExtractor,
  touchstart: touchExtractor,

  // UI Events
  scroll: uiExtractor,

  // Wheel Events
  wheel: wheelExtractor,

  // Animation Events
  animationstart: animationExtractor,
  animationend: animationExtractor,
  animationiteration: animationExtractor,

  // Transition Events
  transitionend: transitionExtractor,

  // Toggle Events
  toggle: toggleExtractor,
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

    // Fallback for unknown event types: minimal synthetic extractor
    return syntheticExtractor(evt);
  }

  // If it's not a duck-typed event, return it as is.
  return value;
}
