/* === IMPORTANT === */

import { extractHTMLElement } from "./elements";
import { createExtractor } from "./extractor";

// Reusable computed mappers (helps bundlers/minifiers share references)
const mapTarget = (e: { target: EventTarget | null }) =>
	extractHTMLElement(e.target as HTMLElement);
const mapRelated = (e: { relatedTarget: EventTarget | null }) =>
	e.relatedTarget ? extractHTMLElement(e.relatedTarget as HTMLElement) : null;

function makeExtractor<K extends readonly any[]>(
	keys: K,
	computed?: Record<string, (evt: any) => any>,
) {
	return createExtractor<any>()(
		keys as any,
		{
			target: mapTarget,
			...(computed || {}),
		} as any,
	);
}

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

const UI_KEYS = [...SYNTHETIC_KEYS, "detail"] as const satisfies readonly (keyof React.UIEvent)[];

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

const syntheticExtractor = makeExtractor(SYNTHETIC_KEYS);

const uiExtractor = makeExtractor(UI_KEYS);

const mouseExtractor = makeExtractor(MOUSE_KEYS, { relatedTarget: mapRelated });

const clipboardExtractor = makeExtractor(SYNTHETIC_KEYS, {
	clipboardData: (e) => extractDataTransfer(e.clipboardData),
});

const compositionExtractor = makeExtractor([...SYNTHETIC_KEYS, "data"] as const);

const dragExtractor = makeExtractor(MOUSE_KEYS, {
	relatedTarget: mapRelated,
	dataTransfer: (e) => extractDataTransfer(e.dataTransfer),
});

const pointerExtractor = makeExtractor(POINTER_KEYS, {
	relatedTarget: mapRelated,
});

const focusExtractor = makeExtractor(SYNTHETIC_KEYS, {
	relatedTarget: mapRelated,
});

const formExtractor = makeExtractor(SYNTHETIC_KEYS);

const invalidExtractor = makeExtractor(SYNTHETIC_KEYS);

const changeExtractor = makeExtractor(SYNTHETIC_KEYS);

const keyboardExtractor = makeExtractor([
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
] as const);

const touchExtractor = makeExtractor(
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
		changedTouches: (e) => mapTouchList(e.changedTouches),
		targetTouches: (e) => mapTouchList(e.targetTouches),
		touches: (e) => mapTouchList(e.touches),
	},
);

const wheelExtractor = makeExtractor(
	[...MOUSE_KEYS, "deltaMode", "deltaX", "deltaY", "deltaZ"] as const,
	{
		relatedTarget: mapRelated,
	},
);

const animationExtractor = makeExtractor([
	...SYNTHETIC_KEYS,
	"animationName",
	"elapsedTime",
	"pseudoElement",
] as const);

const toggleExtractor = makeExtractor([...SYNTHETIC_KEYS, "oldState", "newState"] as const);

const transitionExtractor = makeExtractor([
	...SYNTHETIC_KEYS,
	"elapsedTime",
	"propertyName",
	"pseudoElement",
] as const);

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

const eventExtractorMap: { [key: string]: (evt: any) => object } = {};

function add(map: Record<string, any>, names: readonly string[], fn: any) {
	for (const n of names) map[n] = fn;
}

add(
	eventExtractorMap,
	[
		"pointerdown",
		"pointermove",
		"pointerup",
		"pointercancel",
		"gotpointercapture",
		"lostpointercapture",
		"pointerenter",
		"pointerleave",
		"pointerover",
		"pointerout",
	],
	pointerExtractor,
);

add(
	eventExtractorMap,
	[
		"click",
		"contextmenu",
		"dblclick",
		"mousedown",
		"mouseenter",
		"mouseleave",
		"mousemove",
		"mouseout",
		"mouseover",
		"mouseup",
	],
	mouseExtractor,
);

add(
	eventExtractorMap,
	["drag", "dragend", "dragenter", "dragexit", "dragleave", "dragover", "dragstart", "drop"],
	dragExtractor,
);

add(eventExtractorMap, ["keydown", "keypress", "keyup"], keyboardExtractor);
add(eventExtractorMap, ["focus", "blur"], focusExtractor);
add(eventExtractorMap, ["change", "input"], changeExtractor);
add(eventExtractorMap, ["invalid"], invalidExtractor);
add(eventExtractorMap, ["reset", "submit"], formExtractor);
add(eventExtractorMap, ["copy", "cut", "paste"], clipboardExtractor);
add(
	eventExtractorMap,
	["compositionend", "compositionstart", "compositionupdate"],
	compositionExtractor,
);
add(eventExtractorMap, ["touchcancel", "touchend", "touchmove", "touchstart"], touchExtractor);
add(eventExtractorMap, ["scroll"], uiExtractor);
add(eventExtractorMap, ["wheel"], wheelExtractor);
add(
	eventExtractorMap,
	["animationstart", "animationend", "animationiteration"],
	animationExtractor,
);
add(eventExtractorMap, ["transitionend"], transitionExtractor);
add(eventExtractorMap, ["toggle"], toggleExtractor);

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
