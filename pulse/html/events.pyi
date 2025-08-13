"""
Generic DOM event type definitions without framework/runtime dependencies.

This module defines the shape of browser events and a generic mapping of
DOM event handler names to their corresponding event payload types using
TypedDict. It intentionally does not include any runtime helpers.
"""

from typing import Generic, Literal, Optional, TypeVar, TypedDict

from pulse.html.elements import (
    HTMLDialogElement,
    HTMLElement,
    HTMLInputElement,
    HTMLSelectElement,
    HTMLTextAreaElement,
)


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
    relatedTarget: Optional[HTMLElement]
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
    relatedTarget: Optional[HTMLElement]


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
    onCopy: ClipboardEvent[TElement]
    onCopyCapture: ClipboardEvent[TElement]
    onCut: ClipboardEvent[TElement]
    onCutCapture: ClipboardEvent[TElement]
    onPaste: ClipboardEvent[TElement]
    onPasteCapture: ClipboardEvent[TElement]

    # Composition Events
    onCompositionEnd: CompositionEvent[TElement]
    onCompositionEndCapture: CompositionEvent[TElement]
    onCompositionStart: CompositionEvent[TElement]
    onCompositionStartCapture: CompositionEvent[TElement]
    onCompositionUpdate: CompositionEvent[TElement]
    onCompositionUpdateCapture: CompositionEvent[TElement]

    # Focus Events
    onFocus: FocusEvent[TElement]
    onFocusCapture: FocusEvent[TElement]
    onBlur: FocusEvent[TElement]
    onBlurCapture: FocusEvent[TElement]

    # Form Events (default mapping)
    onChange: FormEvent[TElement]
    onChangeCapture: FormEvent[TElement]
    onBeforeInput: FormEvent[TElement]
    onBeforeInputCapture: FormEvent[TElement]
    onInput: FormEvent[TElement]
    onInputCapture: FormEvent[TElement]
    onReset: FormEvent[TElement]
    onResetCapture: FormEvent[TElement]
    onSubmit: FormEvent[TElement]
    onSubmitCapture: FormEvent[TElement]
    onInvalid: FormEvent[TElement]
    onInvalidCapture: FormEvent[TElement]

    # Image/Media-ish Events (using SyntheticEvent by default)
    onLoad: SyntheticEvent[TElement]
    onLoadCapture: SyntheticEvent[TElement]
    onError: SyntheticEvent[TElement]
    onErrorCapture: SyntheticEvent[TElement]

    # Keyboard Events
    onKeyDown: KeyboardEvent[TElement]
    onKeyDownCapture: KeyboardEvent[TElement]
    onKeyPress: KeyboardEvent[TElement]
    onKeyPressCapture: KeyboardEvent[TElement]
    onKeyUp: KeyboardEvent[TElement]
    onKeyUpCapture: KeyboardEvent[TElement]

    # Media Events (default SyntheticEvent payloads)
    onAbort: SyntheticEvent[TElement]
    onAbortCapture: SyntheticEvent[TElement]
    onCanPlay: SyntheticEvent[TElement]
    onCanPlayCapture: SyntheticEvent[TElement]
    onCanPlayThrough: SyntheticEvent[TElement]
    onCanPlayThroughCapture: SyntheticEvent[TElement]
    onDurationChange: SyntheticEvent[TElement]
    onDurationChangeCapture: SyntheticEvent[TElement]
    onEmptied: SyntheticEvent[TElement]
    onEmptiedCapture: SyntheticEvent[TElement]
    onEncrypted: SyntheticEvent[TElement]
    onEncryptedCapture: SyntheticEvent[TElement]
    onEnded: SyntheticEvent[TElement]
    onEndedCapture: SyntheticEvent[TElement]
    onLoadedData: SyntheticEvent[TElement]
    onLoadedDataCapture: SyntheticEvent[TElement]
    onLoadedMetadata: SyntheticEvent[TElement]
    onLoadedMetadataCapture: SyntheticEvent[TElement]
    onLoadStart: SyntheticEvent[TElement]
    onLoadStartCapture: SyntheticEvent[TElement]
    onPause: SyntheticEvent[TElement]
    onPauseCapture: SyntheticEvent[TElement]
    onPlay: SyntheticEvent[TElement]
    onPlayCapture: SyntheticEvent[TElement]
    onPlaying: SyntheticEvent[TElement]
    onPlayingCapture: SyntheticEvent[TElement]
    onProgress: SyntheticEvent[TElement]
    onProgressCapture: SyntheticEvent[TElement]
    onRateChange: SyntheticEvent[TElement]
    onRateChangeCapture: SyntheticEvent[TElement]
    onResize: SyntheticEvent[TElement]
    onResizeCapture: SyntheticEvent[TElement]
    onSeeked: SyntheticEvent[TElement]
    onSeekedCapture: SyntheticEvent[TElement]
    onSeeking: SyntheticEvent[TElement]
    onSeekingCapture: SyntheticEvent[TElement]
    onStalled: SyntheticEvent[TElement]
    onStalledCapture: SyntheticEvent[TElement]
    onSuspend: SyntheticEvent[TElement]
    onSuspendCapture: SyntheticEvent[TElement]
    onTimeUpdate: SyntheticEvent[TElement]
    onTimeUpdateCapture: SyntheticEvent[TElement]
    onVolumeChange: SyntheticEvent[TElement]
    onVolumeChangeCapture: SyntheticEvent[TElement]
    onWaiting: SyntheticEvent[TElement]
    onWaitingCapture: SyntheticEvent[TElement]

    # Mouse Events
    onAuxClick: MouseEvent[TElement]
    onAuxClickCapture: MouseEvent[TElement]
    onClick: MouseEvent[TElement]
    onClickCapture: MouseEvent[TElement]
    onContextMenu: MouseEvent[TElement]
    onContextMenuCapture: MouseEvent[TElement]
    onDoubleClick: MouseEvent[TElement]
    onDoubleClickCapture: MouseEvent[TElement]
    onDrag: DragEvent[TElement]
    onDragCapture: DragEvent[TElement]
    onDragEnd: DragEvent[TElement]
    onDragEndCapture: DragEvent[TElement]
    onDragEnter: DragEvent[TElement]
    onDragEnterCapture: DragEvent[TElement]
    onDragExit: DragEvent[TElement]
    onDragExitCapture: DragEvent[TElement]
    onDragLeave: DragEvent[TElement]
    onDragLeaveCapture: DragEvent[TElement]
    onDragOver: DragEvent[TElement]
    onDragOverCapture: DragEvent[TElement]
    onDragStart: DragEvent[TElement]
    onDragStartCapture: DragEvent[TElement]
    onDrop: DragEvent[TElement]
    onDropCapture: DragEvent[TElement]
    onMouseDown: MouseEvent[TElement]
    onMouseDownCapture: MouseEvent[TElement]
    onMouseEnter: MouseEvent[TElement]
    onMouseLeave: MouseEvent[TElement]
    onMouseMove: MouseEvent[TElement]
    onMouseMoveCapture: MouseEvent[TElement]
    onMouseOut: MouseEvent[TElement]
    onMouseOutCapture: MouseEvent[TElement]
    onMouseOver: MouseEvent[TElement]
    onMouseOverCapture: MouseEvent[TElement]
    onMouseUp: MouseEvent[TElement]
    onMouseUpCapture: MouseEvent[TElement]

    # Selection Events
    onSelect: SyntheticEvent[TElement]
    onSelectCapture: SyntheticEvent[TElement]

    # Touch Events
    onTouchCancel: TouchEvent[TElement]
    onTouchCancelCapture: TouchEvent[TElement]
    onTouchEnd: TouchEvent[TElement]
    onTouchEndCapture: TouchEvent[TElement]
    onTouchMove: TouchEvent[TElement]
    onTouchMoveCapture: TouchEvent[TElement]
    onTouchStart: TouchEvent[TElement]
    onTouchStartCapture: TouchEvent[TElement]

    # Pointer Events
    onPointerDown: PointerEvent[TElement]
    onPointerDownCapture: PointerEvent[TElement]
    onPointerMove: PointerEvent[TElement]
    onPointerMoveCapture: PointerEvent[TElement]
    onPointerUp: PointerEvent[TElement]
    onPointerUpCapture: PointerEvent[TElement]
    onPointerCancel: PointerEvent[TElement]
    onPointerCancelCapture: PointerEvent[TElement]
    onPointerEnter: PointerEvent[TElement]
    onPointerLeave: PointerEvent[TElement]
    onPointerOver: PointerEvent[TElement]
    onPointerOverCapture: PointerEvent[TElement]
    onPointerOut: PointerEvent[TElement]
    onPointerOutCapture: PointerEvent[TElement]
    onGotPointerCapture: PointerEvent[TElement]
    onGotPointerCaptureCapture: PointerEvent[TElement]
    onLostPointerCapture: PointerEvent[TElement]
    onLostPointerCaptureCapture: PointerEvent[TElement]

    # UI Events
    onScroll: UIEvent[TElement]
    onScrollCapture: UIEvent[TElement]
    onScrollEnd: UIEvent[TElement]
    onScrollEndCapture: UIEvent[TElement]

    # Wheel Events
    onWheel: WheelEvent[TElement]
    onWheelCapture: WheelEvent[TElement]

    # Animation Events
    onAnimationStart: AnimationEvent[TElement]
    onAnimationStartCapture: AnimationEvent[TElement]
    onAnimationEnd: AnimationEvent[TElement]
    onAnimationEndCapture: AnimationEvent[TElement]
    onAnimationIteration: AnimationEvent[TElement]
    onAnimationIterationCapture: AnimationEvent[TElement]

    # Toggle Events
    onToggle: ToggleEvent[TElement]
    onBeforeToggle: ToggleEvent[TElement]

    # Transition Events
    onTransitionCancel: TransitionEvent[TElement]
    onTransitionCancelCapture: TransitionEvent[TElement]
    onTransitionEnd: TransitionEvent[TElement]
    onTransitionEndCapture: TransitionEvent[TElement]
    onTransitionRun: TransitionEvent[TElement]
    onTransitionRunCapture: TransitionEvent[TElement]
    onTransitionStart: TransitionEvent[TElement]
    onTransitionStartCapture: TransitionEvent[TElement]


class FormControlDOMEvents(DOMEvents[TElement], total=False):
    """Specialized DOMEvents where on_change is a ChangeEvent.

    Use this for inputs, textareas, and selects.
    """

    onChange: ChangeEvent[TElement]


class InputDOMEvents(FormControlDOMEvents[HTMLInputElement], total=False):
    pass


class TextAreaDOMEvents(FormControlDOMEvents[HTMLTextAreaElement], total=False):
    pass


class SelectDOMEvents(FormControlDOMEvents[HTMLSelectElement], total=False):
    pass


class DialogDOMEvents(DOMEvents[HTMLDialogElement], total=False):
    onCancel: SyntheticEvent[HTMLDialogElement]
    onClose: SyntheticEvent[HTMLDialogElement]
