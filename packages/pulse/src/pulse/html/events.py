"""
Generic DOM event type definitions without framework/runtime dependencies.

This module defines the shape of browser events and a generic mapping of
DOM event handler names to their corresponding event payload types using
TypedDict. It intentionally does not include any runtime helpers.
"""

from typing import (
    Generic,
    Literal,
    Optional,
    TypedDict,
    TypeVar,
)

from pulse.helpers import EventHandler
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
    onCopy: EventHandler[ClipboardEvent[TElement]]
    onCopyCapture: EventHandler[ClipboardEvent[TElement]]
    onCut: EventHandler[ClipboardEvent[TElement]]
    onCutCapture: EventHandler[ClipboardEvent[TElement]]
    onPaste: EventHandler[ClipboardEvent[TElement]]
    onPasteCapture: EventHandler[ClipboardEvent[TElement]]

    # Composition Events
    onCompositionEnd: EventHandler[CompositionEvent[TElement]]
    onCompositionEndCapture: EventHandler[CompositionEvent[TElement]]
    onCompositionStart: EventHandler[CompositionEvent[TElement]]
    onCompositionStartCapture: EventHandler[CompositionEvent[TElement]]
    onCompositionUpdate: EventHandler[CompositionEvent[TElement]]
    onCompositionUpdateCapture: EventHandler[CompositionEvent[TElement]]

    # Focus Events
    onFocus: EventHandler[FocusEvent[TElement]]
    onFocusCapture: EventHandler[FocusEvent[TElement]]
    onBlur: EventHandler[FocusEvent[TElement]]
    onBlurCapture: EventHandler[FocusEvent[TElement]]

    # Form Events (default mapping)
    onChange: EventHandler[FormEvent[TElement]]
    onChangeCapture: EventHandler[FormEvent[TElement]]
    onBeforeInput: EventHandler[FormEvent[TElement]]
    onBeforeInputCapture: EventHandler[FormEvent[TElement]]
    onInput: EventHandler[FormEvent[TElement]]
    onInputCapture: EventHandler[FormEvent[TElement]]
    onReset: EventHandler[FormEvent[TElement]]
    onResetCapture: EventHandler[FormEvent[TElement]]
    onSubmit: EventHandler[FormEvent[TElement]]
    onSubmitCapture: EventHandler[FormEvent[TElement]]
    onInvalid: EventHandler[FormEvent[TElement]]
    onInvalidCapture: EventHandler[FormEvent[TElement]]

    # Image/Media-ish Events (using SyntheticEvent by default)
    onLoad: EventHandler[SyntheticEvent[TElement]]
    onLoadCapture: EventHandler[SyntheticEvent[TElement]]
    onError: EventHandler[SyntheticEvent[TElement]]
    onErrorCapture: EventHandler[SyntheticEvent[TElement]]

    # Keyboard Events
    onKeyDown: EventHandler[KeyboardEvent[TElement]]
    onKeyDownCapture: EventHandler[KeyboardEvent[TElement]]
    onKeyPress: EventHandler[KeyboardEvent[TElement]]
    onKeyPressCapture: EventHandler[KeyboardEvent[TElement]]
    onKeyUp: EventHandler[KeyboardEvent[TElement]]
    onKeyUpCapture: EventHandler[KeyboardEvent[TElement]]

    # Media Events (default SyntheticEvent payloads)
    onAbort: EventHandler[SyntheticEvent[TElement]]
    onAbortCapture: EventHandler[SyntheticEvent[TElement]]
    onCanPlay: EventHandler[SyntheticEvent[TElement]]
    onCanPlayCapture: EventHandler[SyntheticEvent[TElement]]
    onCanPlayThrough: EventHandler[SyntheticEvent[TElement]]
    onCanPlayThroughCapture: EventHandler[SyntheticEvent[TElement]]
    onDurationChange: EventHandler[SyntheticEvent[TElement]]
    onDurationChangeCapture: EventHandler[SyntheticEvent[TElement]]
    onEmptied: EventHandler[SyntheticEvent[TElement]]
    onEmptiedCapture: EventHandler[SyntheticEvent[TElement]]
    onEncrypted: EventHandler[SyntheticEvent[TElement]]
    onEncryptedCapture: EventHandler[SyntheticEvent[TElement]]
    onEnded: EventHandler[SyntheticEvent[TElement]]
    onEndedCapture: EventHandler[SyntheticEvent[TElement]]
    onLoadedData: EventHandler[SyntheticEvent[TElement]]
    onLoadedDataCapture: EventHandler[SyntheticEvent[TElement]]
    onLoadedMetadata: EventHandler[SyntheticEvent[TElement]]
    onLoadedMetadataCapture: EventHandler[SyntheticEvent[TElement]]
    onLoadStart: EventHandler[SyntheticEvent[TElement]]
    onLoadStartCapture: EventHandler[SyntheticEvent[TElement]]
    onPause: EventHandler[SyntheticEvent[TElement]]
    onPauseCapture: EventHandler[SyntheticEvent[TElement]]
    onPlay: EventHandler[SyntheticEvent[TElement]]
    onPlayCapture: EventHandler[SyntheticEvent[TElement]]
    onPlaying: EventHandler[SyntheticEvent[TElement]]
    onPlayingCapture: EventHandler[SyntheticEvent[TElement]]
    onProgress: EventHandler[SyntheticEvent[TElement]]
    onProgressCapture: EventHandler[SyntheticEvent[TElement]]
    onRateChange: EventHandler[SyntheticEvent[TElement]]
    onRateChangeCapture: EventHandler[SyntheticEvent[TElement]]
    onResize: EventHandler[SyntheticEvent[TElement]]
    onResizeCapture: EventHandler[SyntheticEvent[TElement]]
    onSeeked: EventHandler[SyntheticEvent[TElement]]
    onSeekedCapture: EventHandler[SyntheticEvent[TElement]]
    onSeeking: EventHandler[SyntheticEvent[TElement]]
    onSeekingCapture: EventHandler[SyntheticEvent[TElement]]
    onStalled: EventHandler[SyntheticEvent[TElement]]
    onStalledCapture: EventHandler[SyntheticEvent[TElement]]
    onSuspend: EventHandler[SyntheticEvent[TElement]]
    onSuspendCapture: EventHandler[SyntheticEvent[TElement]]
    onTimeUpdate: EventHandler[SyntheticEvent[TElement]]
    onTimeUpdateCapture: EventHandler[SyntheticEvent[TElement]]
    onVolumeChange: EventHandler[SyntheticEvent[TElement]]
    onVolumeChangeCapture: EventHandler[SyntheticEvent[TElement]]
    onWaiting: EventHandler[SyntheticEvent[TElement]]
    onWaitingCapture: EventHandler[SyntheticEvent[TElement]]

    # Mouse Events
    onAuxClick: EventHandler[MouseEvent[TElement]]
    onAuxClickCapture: EventHandler[MouseEvent[TElement]]
    onClick: EventHandler[MouseEvent[TElement]]
    onClickCapture: EventHandler[MouseEvent[TElement]]
    onContextMenu: EventHandler[MouseEvent[TElement]]
    onContextMenuCapture: EventHandler[MouseEvent[TElement]]
    onDoubleClick: EventHandler[MouseEvent[TElement]]
    onDoubleClickCapture: EventHandler[MouseEvent[TElement]]
    onDrag: EventHandler[DragEvent[TElement]]
    onDragCapture: EventHandler[DragEvent[TElement]]
    onDragEnd: EventHandler[DragEvent[TElement]]
    onDragEndCapture: EventHandler[DragEvent[TElement]]
    onDragEnter: EventHandler[DragEvent[TElement]]
    onDragEnterCapture: EventHandler[DragEvent[TElement]]
    onDragExit: EventHandler[DragEvent[TElement]]
    onDragExitCapture: EventHandler[DragEvent[TElement]]
    onDragLeave: EventHandler[DragEvent[TElement]]
    onDragLeaveCapture: EventHandler[DragEvent[TElement]]
    onDragOver: EventHandler[DragEvent[TElement]]
    onDragOverCapture: EventHandler[DragEvent[TElement]]
    onDragStart: EventHandler[DragEvent[TElement]]
    onDragStartCapture: EventHandler[DragEvent[TElement]]
    onDrop: EventHandler[DragEvent[TElement]]
    onDropCapture: EventHandler[DragEvent[TElement]]
    onMouseDown: EventHandler[MouseEvent[TElement]]
    onMouseDownCapture: EventHandler[MouseEvent[TElement]]
    onMouseEnter: EventHandler[MouseEvent[TElement]]
    onMouseLeave: EventHandler[MouseEvent[TElement]]
    onMouseMove: EventHandler[MouseEvent[TElement]]
    onMouseMoveCapture: EventHandler[MouseEvent[TElement]]
    onMouseOut: EventHandler[MouseEvent[TElement]]
    onMouseOutCapture: EventHandler[MouseEvent[TElement]]
    onMouseOver: EventHandler[MouseEvent[TElement]]
    onMouseOverCapture: EventHandler[MouseEvent[TElement]]
    onMouseUp: EventHandler[MouseEvent[TElement]]
    onMouseUpCapture: EventHandler[MouseEvent[TElement]]

    # Selection Events
    onSelect: EventHandler[SyntheticEvent[TElement]]
    onSelectCapture: EventHandler[SyntheticEvent[TElement]]

    # Touch Events
    onTouchCancel: EventHandler[TouchEvent[TElement]]
    onTouchCancelCapture: EventHandler[TouchEvent[TElement]]
    onTouchEnd: EventHandler[TouchEvent[TElement]]
    onTouchEndCapture: EventHandler[TouchEvent[TElement]]
    onTouchMove: EventHandler[TouchEvent[TElement]]
    onTouchMoveCapture: EventHandler[TouchEvent[TElement]]
    onTouchStart: EventHandler[TouchEvent[TElement]]
    onTouchStartCapture: EventHandler[TouchEvent[TElement]]

    # Pointer Events
    onPointerDown: EventHandler[PointerEvent[TElement]]
    onPointerDownCapture: EventHandler[PointerEvent[TElement]]
    onPointerMove: EventHandler[PointerEvent[TElement]]
    onPointerMoveCapture: EventHandler[PointerEvent[TElement]]
    onPointerUp: EventHandler[PointerEvent[TElement]]
    onPointerUpCapture: EventHandler[PointerEvent[TElement]]
    onPointerCancel: EventHandler[PointerEvent[TElement]]
    onPointerCancelCapture: EventHandler[PointerEvent[TElement]]
    onPointerEnter: EventHandler[PointerEvent[TElement]]
    onPointerLeave: EventHandler[PointerEvent[TElement]]
    onPointerOver: EventHandler[PointerEvent[TElement]]
    onPointerOverCapture: EventHandler[PointerEvent[TElement]]
    onPointerOut: EventHandler[PointerEvent[TElement]]
    onPointerOutCapture: EventHandler[PointerEvent[TElement]]
    onGotPointerCapture: EventHandler[PointerEvent[TElement]]
    onGotPointerCaptureCapture: EventHandler[PointerEvent[TElement]]
    onLostPointerCapture: EventHandler[PointerEvent[TElement]]
    onLostPointerCaptureCapture: EventHandler[PointerEvent[TElement]]

    # UI Events
    onScroll: EventHandler[UIEvent[TElement]]
    onScrollCapture: EventHandler[UIEvent[TElement]]
    onScrollEnd: EventHandler[UIEvent[TElement]]
    onScrollEndCapture: EventHandler[UIEvent[TElement]]

    # Wheel Events
    onWheel: EventHandler[WheelEvent[TElement]]
    onWheelCapture: EventHandler[WheelEvent[TElement]]

    # Animation Events
    onAnimationStart: EventHandler[AnimationEvent[TElement]]
    onAnimationStartCapture: EventHandler[AnimationEvent[TElement]]
    onAnimationEnd: EventHandler[AnimationEvent[TElement]]
    onAnimationEndCapture: EventHandler[AnimationEvent[TElement]]
    onAnimationIteration: EventHandler[AnimationEvent[TElement]]
    onAnimationIterationCapture: EventHandler[AnimationEvent[TElement]]

    # Toggle Events
    onToggle: EventHandler[ToggleEvent[TElement]]
    onBeforeToggle: EventHandler[ToggleEvent[TElement]]

    # Transition Events
    onTransitionCancel: EventHandler[TransitionEvent[TElement]]
    onTransitionCancelCapture: EventHandler[TransitionEvent[TElement]]
    onTransitionEnd: EventHandler[TransitionEvent[TElement]]
    onTransitionEndCapture: EventHandler[TransitionEvent[TElement]]
    onTransitionRun: EventHandler[TransitionEvent[TElement]]
    onTransitionRunCapture: EventHandler[TransitionEvent[TElement]]
    onTransitionStart: EventHandler[TransitionEvent[TElement]]
    onTransitionStartCapture: EventHandler[TransitionEvent[TElement]]

class FormControlDOMEvents(DOMEvents[TElement], total=False):
    """Specialized DOMEvents where on_change is a ChangeEvent.

    Use this for inputs, textareas, and selects.
    """

    onChange: EventHandler[ChangeEvent[TElement]]

class InputDOMEvents(FormControlDOMEvents[HTMLInputElement], total=False):
    pass

class TextAreaDOMEvents(FormControlDOMEvents[HTMLTextAreaElement], total=False):
    pass

class SelectDOMEvents(FormControlDOMEvents[HTMLSelectElement], total=False):
    pass

class DialogDOMEvents(DOMEvents[HTMLDialogElement], total=False):
    onCancel: EventHandler[SyntheticEvent[HTMLDialogElement]]
    onClose: EventHandler[SyntheticEvent[HTMLDialogElement]]
