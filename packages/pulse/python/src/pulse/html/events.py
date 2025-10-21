"""
Generic DOM event type definitions without framework/runtime dependencies.

This module defines the shape of browser events and a generic mapping of
DOM event handler names to their corresponding event payload types using
TypedDict. It intentionally does not include any runtime helpers.
"""

from typing import (
	Generic,
	Literal,
	TypedDict,
	TypeVar,
)

from pulse.html.elements import (
	HTMLDialogElement,
	HTMLElement,
	HTMLInputElement,
	HTMLSelectElement,
	HTMLTextAreaElement,
)
from pulse.types.event_handler import EventHandler1

# Generic TypeVar for the element target
TElement = TypeVar("TElement", bound=HTMLElement)


class DataTransferItem(TypedDict):
	kind: str
	type: str


class DataTransfer(TypedDict):
	dropEffect: Literal["none", "copy", "link", "move"]
	effectAllowed: Literal[
		"none",
		"copy",
		"copyLink",
		"copyMove",
		"link",
		"linkMove",
		"move",
		"all",
		"uninitialized",
	]
	# files: Any  # FileList equivalent
	items: list[DataTransferItem]  # DataTransferItemList
	types: list[str]


class Touch(TypedDict):
	target: HTMLElement
	identifier: int
	screenX: float
	screenY: float
	clientX: float
	clientY: float
	pageX: float
	pageY: float


# Base SyntheticEvent using TypedDict and Generic
class SyntheticEvent(TypedDict, Generic[TElement]):
	# nativeEvent: Any # Omitted
	# current_target: TElement  # element on which the event listener is registered
	target: HTMLElement  # target of the event (may be a child)
	bubbles: bool
	cancelable: bool
	defaultPrevented: bool
	eventPhase: int
	isTrusted: bool
	# preventDefault(): void;
	# isDefaultPrevented(): boolean;
	# stopPropagation(): void;
	# isPropagationStopped(): boolean;
	# persist(): void;
	timestamp: int
	type: str


class UIEvent(SyntheticEvent[TElement]):
	detail: int
	# view: Any # AbstractView - Omitted


class MouseEvent(UIEvent[TElement]):
	altKey: bool
	button: int
	buttons: int
	clientX: float
	clientY: float
	ctrlKey: bool
	# getModifierState(key: ModifierKey): boolean
	metaKey: bool
	movementX: float
	movementY: float
	pageX: float
	pageY: float
	relatedTarget: HTMLElement | None
	screenX: float
	screenY: float
	shiftKey: bool


class ClipboardEvent(SyntheticEvent[TElement]):
	clipboardData: DataTransfer


class CompositionEvent(SyntheticEvent[TElement]):
	data: str


class DragEvent(MouseEvent[TElement]):
	dataTransfer: DataTransfer


class PointerEvent(MouseEvent[TElement]):
	pointerId: int
	pressure: float
	tangentialPressure: float
	tiltX: float
	tiltY: float
	twist: float
	width: float
	height: float
	pointerType: Literal["mouse", "pen", "touch"]
	isPrimary: bool


class FocusEvent(SyntheticEvent[TElement]):
	target: TElement
	relatedTarget: HTMLElement | None


class FormEvent(SyntheticEvent[TElement]):
	# No specific fields added here
	pass


class InvalidEvent(SyntheticEvent[TElement]):
	target: TElement


class ChangeEvent(SyntheticEvent[TElement]):
	target: TElement


ModifierKey = Literal[
	"Alt",
	"AltGraph",
	"CapsLock",
	"Control",
	"Fn",
	"FnLock",
	"Hyper",
	"Meta",
	"NumLock",
	"ScrollLock",
	"Shift",
	"Super",
	"Symbol",
	"SymbolLock",
]


class KeyboardEvent(UIEvent[TElement]):
	altKey: bool
	# char_code: int  # deprecated
	ctrlKey: bool
	code: str
	# getModifierState(key: ModifierKey): boolean
	key: str
	# key_code: int  # deprecated
	locale: str
	location: int
	metaKey: bool
	repeat: bool
	shiftKey: bool
	# which: int  # deprecated


class TouchEvent(UIEvent[TElement]):
	altKey: bool
	changedTouches: list[Touch]  # TouchList
	ctrlKey: bool
	# getModifierState(key: ModifierKey): boolean
	metaKey: bool
	shiftKey: bool
	targetTouches: list[Touch]  # TouchList
	touches: list[Touch]  # TouchList


class WheelEvent(MouseEvent[TElement]):
	deltaMode: int
	deltaX: float
	deltaY: float
	deltaZ: float


class AnimationEvent(SyntheticEvent[TElement]):
	animationName: str
	elapsedTime: float
	pseudoElement: str


class ToggleEvent(SyntheticEvent[TElement]):
	oldState: Literal["closed", "open"]
	newState: Literal["closed", "open"]


class TransitionEvent(SyntheticEvent[TElement]):
	elapsedTime: float
	propertyName: str
	pseudoElement: str


class DOMEvents(TypedDict, Generic[TElement], total=False):
	# Clipboard Events
	onCopy: EventHandler1[ClipboardEvent[TElement]]
	onCopyCapture: EventHandler1[ClipboardEvent[TElement]]
	onCut: EventHandler1[ClipboardEvent[TElement]]
	onCutCapture: EventHandler1[ClipboardEvent[TElement]]
	onPaste: EventHandler1[ClipboardEvent[TElement]]
	onPasteCapture: EventHandler1[ClipboardEvent[TElement]]

	# Composition Events
	onCompositionEnd: EventHandler1[CompositionEvent[TElement]]
	onCompositionEndCapture: EventHandler1[CompositionEvent[TElement]]
	onCompositionStart: EventHandler1[CompositionEvent[TElement]]
	onCompositionStartCapture: EventHandler1[CompositionEvent[TElement]]
	onCompositionUpdate: EventHandler1[CompositionEvent[TElement]]
	onCompositionUpdateCapture: EventHandler1[CompositionEvent[TElement]]

	# Focus Events
	onFocus: EventHandler1[FocusEvent[TElement]]
	onFocusCapture: EventHandler1[FocusEvent[TElement]]
	onBlur: EventHandler1[FocusEvent[TElement]]
	onBlurCapture: EventHandler1[FocusEvent[TElement]]

	# Form Events (default mapping)
	onChange: EventHandler1[FormEvent[TElement]]
	onChangeCapture: EventHandler1[FormEvent[TElement]]
	onBeforeInput: EventHandler1[FormEvent[TElement]]
	onBeforeInputCapture: EventHandler1[FormEvent[TElement]]
	onInput: EventHandler1[FormEvent[TElement]]
	onInputCapture: EventHandler1[FormEvent[TElement]]
	onReset: EventHandler1[FormEvent[TElement]]
	onResetCapture: EventHandler1[FormEvent[TElement]]
	onSubmit: EventHandler1[FormEvent[TElement]]
	onSubmitCapture: EventHandler1[FormEvent[TElement]]
	onInvalid: EventHandler1[FormEvent[TElement]]
	onInvalidCapture: EventHandler1[FormEvent[TElement]]

	# Image/Media-ish Events (using SyntheticEvent by default)
	onLoad: EventHandler1[SyntheticEvent[TElement]]
	onLoadCapture: EventHandler1[SyntheticEvent[TElement]]
	onError: EventHandler1[SyntheticEvent[TElement]]
	onErrorCapture: EventHandler1[SyntheticEvent[TElement]]

	# Keyboard Events
	onKeyDown: EventHandler1[KeyboardEvent[TElement]]
	onKeyDownCapture: EventHandler1[KeyboardEvent[TElement]]
	onKeyPress: EventHandler1[KeyboardEvent[TElement]]
	onKeyPressCapture: EventHandler1[KeyboardEvent[TElement]]
	onKeyUp: EventHandler1[KeyboardEvent[TElement]]
	onKeyUpCapture: EventHandler1[KeyboardEvent[TElement]]

	# Media Events (default SyntheticEvent payloads)
	onAbort: EventHandler1[SyntheticEvent[TElement]]
	onAbortCapture: EventHandler1[SyntheticEvent[TElement]]
	onCanPlay: EventHandler1[SyntheticEvent[TElement]]
	onCanPlayCapture: EventHandler1[SyntheticEvent[TElement]]
	onCanPlayThrough: EventHandler1[SyntheticEvent[TElement]]
	onCanPlayThroughCapture: EventHandler1[SyntheticEvent[TElement]]
	onDurationChange: EventHandler1[SyntheticEvent[TElement]]
	onDurationChangeCapture: EventHandler1[SyntheticEvent[TElement]]
	onEmptied: EventHandler1[SyntheticEvent[TElement]]
	onEmptiedCapture: EventHandler1[SyntheticEvent[TElement]]
	onEncrypted: EventHandler1[SyntheticEvent[TElement]]
	onEncryptedCapture: EventHandler1[SyntheticEvent[TElement]]
	onEnded: EventHandler1[SyntheticEvent[TElement]]
	onEndedCapture: EventHandler1[SyntheticEvent[TElement]]
	onLoadedData: EventHandler1[SyntheticEvent[TElement]]
	onLoadedDataCapture: EventHandler1[SyntheticEvent[TElement]]
	onLoadedMetadata: EventHandler1[SyntheticEvent[TElement]]
	onLoadedMetadataCapture: EventHandler1[SyntheticEvent[TElement]]
	onLoadStart: EventHandler1[SyntheticEvent[TElement]]
	onLoadStartCapture: EventHandler1[SyntheticEvent[TElement]]
	onPause: EventHandler1[SyntheticEvent[TElement]]
	onPauseCapture: EventHandler1[SyntheticEvent[TElement]]
	onPlay: EventHandler1[SyntheticEvent[TElement]]
	onPlayCapture: EventHandler1[SyntheticEvent[TElement]]
	onPlaying: EventHandler1[SyntheticEvent[TElement]]
	onPlayingCapture: EventHandler1[SyntheticEvent[TElement]]
	onProgress: EventHandler1[SyntheticEvent[TElement]]
	onProgressCapture: EventHandler1[SyntheticEvent[TElement]]
	onRateChange: EventHandler1[SyntheticEvent[TElement]]
	onRateChangeCapture: EventHandler1[SyntheticEvent[TElement]]
	onResize: EventHandler1[SyntheticEvent[TElement]]
	onResizeCapture: EventHandler1[SyntheticEvent[TElement]]
	onSeeked: EventHandler1[SyntheticEvent[TElement]]
	onSeekedCapture: EventHandler1[SyntheticEvent[TElement]]
	onSeeking: EventHandler1[SyntheticEvent[TElement]]
	onSeekingCapture: EventHandler1[SyntheticEvent[TElement]]
	onStalled: EventHandler1[SyntheticEvent[TElement]]
	onStalledCapture: EventHandler1[SyntheticEvent[TElement]]
	onSuspend: EventHandler1[SyntheticEvent[TElement]]
	onSuspendCapture: EventHandler1[SyntheticEvent[TElement]]
	onTimeUpdate: EventHandler1[SyntheticEvent[TElement]]
	onTimeUpdateCapture: EventHandler1[SyntheticEvent[TElement]]
	onVolumeChange: EventHandler1[SyntheticEvent[TElement]]
	onVolumeChangeCapture: EventHandler1[SyntheticEvent[TElement]]
	onWaiting: EventHandler1[SyntheticEvent[TElement]]
	onWaitingCapture: EventHandler1[SyntheticEvent[TElement]]

	# Mouse Events
	onAuxClick: EventHandler1[MouseEvent[TElement]]
	onAuxClickCapture: EventHandler1[MouseEvent[TElement]]
	onClick: EventHandler1[MouseEvent[TElement]]
	onClickCapture: EventHandler1[MouseEvent[TElement]]
	onContextMenu: EventHandler1[MouseEvent[TElement]]
	onContextMenuCapture: EventHandler1[MouseEvent[TElement]]
	onDoubleClick: EventHandler1[MouseEvent[TElement]]
	onDoubleClickCapture: EventHandler1[MouseEvent[TElement]]
	onDrag: EventHandler1[DragEvent[TElement]]
	onDragCapture: EventHandler1[DragEvent[TElement]]
	onDragEnd: EventHandler1[DragEvent[TElement]]
	onDragEndCapture: EventHandler1[DragEvent[TElement]]
	onDragEnter: EventHandler1[DragEvent[TElement]]
	onDragEnterCapture: EventHandler1[DragEvent[TElement]]
	onDragExit: EventHandler1[DragEvent[TElement]]
	onDragExitCapture: EventHandler1[DragEvent[TElement]]
	onDragLeave: EventHandler1[DragEvent[TElement]]
	onDragLeaveCapture: EventHandler1[DragEvent[TElement]]
	onDragOver: EventHandler1[DragEvent[TElement]]
	onDragOverCapture: EventHandler1[DragEvent[TElement]]
	onDragStart: EventHandler1[DragEvent[TElement]]
	onDragStartCapture: EventHandler1[DragEvent[TElement]]
	onDrop: EventHandler1[DragEvent[TElement]]
	onDropCapture: EventHandler1[DragEvent[TElement]]
	onMouseDown: EventHandler1[MouseEvent[TElement]]
	onMouseDownCapture: EventHandler1[MouseEvent[TElement]]
	onMouseEnter: EventHandler1[MouseEvent[TElement]]
	onMouseLeave: EventHandler1[MouseEvent[TElement]]
	onMouseMove: EventHandler1[MouseEvent[TElement]]
	onMouseMoveCapture: EventHandler1[MouseEvent[TElement]]
	onMouseOut: EventHandler1[MouseEvent[TElement]]
	onMouseOutCapture: EventHandler1[MouseEvent[TElement]]
	onMouseOver: EventHandler1[MouseEvent[TElement]]
	onMouseOverCapture: EventHandler1[MouseEvent[TElement]]
	onMouseUp: EventHandler1[MouseEvent[TElement]]
	onMouseUpCapture: EventHandler1[MouseEvent[TElement]]

	# Selection Events
	onSelect: EventHandler1[SyntheticEvent[TElement]]
	onSelectCapture: EventHandler1[SyntheticEvent[TElement]]

	# Touch Events
	onTouchCancel: EventHandler1[TouchEvent[TElement]]
	onTouchCancelCapture: EventHandler1[TouchEvent[TElement]]
	onTouchEnd: EventHandler1[TouchEvent[TElement]]
	onTouchEndCapture: EventHandler1[TouchEvent[TElement]]
	onTouchMove: EventHandler1[TouchEvent[TElement]]
	onTouchMoveCapture: EventHandler1[TouchEvent[TElement]]
	onTouchStart: EventHandler1[TouchEvent[TElement]]
	onTouchStartCapture: EventHandler1[TouchEvent[TElement]]

	# Pointer Events
	onPointerDown: EventHandler1[PointerEvent[TElement]]
	onPointerDownCapture: EventHandler1[PointerEvent[TElement]]
	onPointerMove: EventHandler1[PointerEvent[TElement]]
	onPointerMoveCapture: EventHandler1[PointerEvent[TElement]]
	onPointerUp: EventHandler1[PointerEvent[TElement]]
	onPointerUpCapture: EventHandler1[PointerEvent[TElement]]
	onPointerCancel: EventHandler1[PointerEvent[TElement]]
	onPointerCancelCapture: EventHandler1[PointerEvent[TElement]]
	onPointerEnter: EventHandler1[PointerEvent[TElement]]
	onPointerLeave: EventHandler1[PointerEvent[TElement]]
	onPointerOver: EventHandler1[PointerEvent[TElement]]
	onPointerOverCapture: EventHandler1[PointerEvent[TElement]]
	onPointerOut: EventHandler1[PointerEvent[TElement]]
	onPointerOutCapture: EventHandler1[PointerEvent[TElement]]
	onGotPointerCapture: EventHandler1[PointerEvent[TElement]]
	onGotPointerCaptureCapture: EventHandler1[PointerEvent[TElement]]
	onLostPointerCapture: EventHandler1[PointerEvent[TElement]]
	onLostPointerCaptureCapture: EventHandler1[PointerEvent[TElement]]

	# UI Events
	onScroll: EventHandler1[UIEvent[TElement]]
	onScrollCapture: EventHandler1[UIEvent[TElement]]
	onScrollEnd: EventHandler1[UIEvent[TElement]]
	onScrollEndCapture: EventHandler1[UIEvent[TElement]]

	# Wheel Events
	onWheel: EventHandler1[WheelEvent[TElement]]
	onWheelCapture: EventHandler1[WheelEvent[TElement]]

	# Animation Events
	onAnimationStart: EventHandler1[AnimationEvent[TElement]]
	onAnimationStartCapture: EventHandler1[AnimationEvent[TElement]]
	onAnimationEnd: EventHandler1[AnimationEvent[TElement]]
	onAnimationEndCapture: EventHandler1[AnimationEvent[TElement]]
	onAnimationIteration: EventHandler1[AnimationEvent[TElement]]
	onAnimationIterationCapture: EventHandler1[AnimationEvent[TElement]]

	# Toggle Events
	onToggle: EventHandler1[ToggleEvent[TElement]]
	onBeforeToggle: EventHandler1[ToggleEvent[TElement]]

	# Transition Events
	onTransitionCancel: EventHandler1[TransitionEvent[TElement]]
	onTransitionCancelCapture: EventHandler1[TransitionEvent[TElement]]
	onTransitionEnd: EventHandler1[TransitionEvent[TElement]]
	onTransitionEndCapture: EventHandler1[TransitionEvent[TElement]]
	onTransitionRun: EventHandler1[TransitionEvent[TElement]]
	onTransitionRunCapture: EventHandler1[TransitionEvent[TElement]]
	onTransitionStart: EventHandler1[TransitionEvent[TElement]]
	onTransitionStartCapture: EventHandler1[TransitionEvent[TElement]]


class FormControlDOMEvents(DOMEvents[TElement], total=False):
	"""Specialized DOMEvents where on_change is a ChangeEvent.

	Use this for inputs, textareas, and selects.
	"""

	onChange: EventHandler1[ChangeEvent[TElement]]  # pyright: ignore[reportIncompatibleVariableOverride]


class InputDOMEvents(FormControlDOMEvents[HTMLInputElement], total=False):
	pass


class TextAreaDOMEvents(FormControlDOMEvents[HTMLTextAreaElement], total=False):
	pass


class SelectDOMEvents(FormControlDOMEvents[HTMLSelectElement], total=False):
	pass


class DialogDOMEvents(DOMEvents[HTMLDialogElement], total=False):
	onCancel: EventHandler1[SyntheticEvent[HTMLDialogElement]]
	onClose: EventHandler1[SyntheticEvent[HTMLDialogElement]]
