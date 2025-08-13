"""
Generic DOM event type definitions without framework/runtime dependencies.

This module defines the shape of browser events and a generic mapping of
DOM event handler names to their corresponding event payload types using
TypedDict. It intentionally does not include any runtime helpers.
"""

from typing import Generic, Literal, Optional, TypeVar, TypedDict

from pulse.types.elements import (
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
    drop_effect: Literal["none", "copy", "link", "move"]
    effect_allowed: Literal[
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
    screen_x: float
    screen_y: float
    client_x: float
    client_y: float
    page_x: float
    page_y: float


# Base SyntheticEvent using TypedDict and Generic
class SyntheticEvent(TypedDict, Generic[TElement]):
    # nativeEvent: Any # Omitted
    # current_target: TElement  # element on which the event listener is registered
    target: HTMLElement  # target of the event (may be a child)
    bubbles: bool
    cancelable: bool
    default_prevented: bool
    event_phase: int
    is_trusted: bool
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
    alt_key: bool
    button: int
    buttons: int
    client_x: float
    client_y: float
    ctrl_key: bool
    # getModifierState(key: ModifierKey): boolean
    meta_key: bool
    movement_x: float
    movement_y: float
    page_x: float
    page_y: float
    related_target: Optional[HTMLElement]
    screen_x: float
    screen_y: float
    shift_key: bool


class ClipboardEvent(SyntheticEvent[TElement]):
    clipboard_data: DataTransfer


class CompositionEvent(SyntheticEvent[TElement]):
    data: str


class DragEvent(MouseEvent[TElement]):
    data_transfer: DataTransfer


class PointerEvent(MouseEvent[TElement]):
    pointer_id: int
    pressure: float
    tangential_pressure: float
    tilt_x: float
    tilt_y: float
    twist: float
    width: float
    height: float
    pointer_type: Literal["mouse", "pen", "touch"]
    is_primary: bool


class FocusEvent(SyntheticEvent[TElement]):
    target: TElement
    related_target: Optional[HTMLElement]


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
    alt_key: bool
    # char_code: int  # deprecated
    ctrl_key: bool
    code: str
    # getModifierState(key: ModifierKey): boolean
    key: str
    # key_code: int  # deprecated
    locale: str
    location: int
    meta_key: bool
    repeat: bool
    shift_key: bool
    # which: int  # deprecated


class TouchEvent(UIEvent[TElement]):
    alt_key: bool
    changed_touches: list[Touch]  # TouchList
    ctrl_key: bool
    # getModifierState(key: ModifierKey): boolean
    meta_key: bool
    shift_key: bool
    target_touches: list[Touch]  # TouchList
    touches: list[Touch]  # TouchList


class WheelEvent(MouseEvent[TElement]):
    delta_mode: int
    delta_x: float
    delta_y: float
    delta_z: float


class AnimationEvent(SyntheticEvent[TElement]):
    animation_name: str
    elapsed_time: float
    pseudo_element: str


class ToggleEvent(SyntheticEvent[TElement]):
    old_state: Literal["closed", "open"]
    new_state: Literal["closed", "open"]


class TransitionEvent(SyntheticEvent[TElement]):
    elapsed_time: float
    property_name: str
    pseudo_element: str


class DOMEvents(TypedDict, Generic[TElement], total=False):
    # Clipboard Events
    on_copy: ClipboardEvent[TElement]
    on_copy_capture: ClipboardEvent[TElement]
    on_cut: ClipboardEvent[TElement]
    on_cut_capture: ClipboardEvent[TElement]
    on_paste: ClipboardEvent[TElement]
    on_paste_capture: ClipboardEvent[TElement]

    # Composition Events
    on_composition_end: CompositionEvent[TElement]
    on_composition_end_capture: CompositionEvent[TElement]
    on_composition_start: CompositionEvent[TElement]
    on_composition_start_capture: CompositionEvent[TElement]
    on_composition_update: CompositionEvent[TElement]
    on_composition_update_capture: CompositionEvent[TElement]

    # Focus Events
    on_focus: FocusEvent[TElement]
    on_focus_capture: FocusEvent[TElement]
    on_blur: FocusEvent[TElement]
    on_blur_capture: FocusEvent[TElement]

    # Form Events (default mapping)
    on_change: FormEvent[TElement]
    on_change_capture: FormEvent[TElement]
    on_before_input: FormEvent[TElement]
    on_before_input_capture: FormEvent[TElement]
    on_input: FormEvent[TElement]
    on_input_capture: FormEvent[TElement]
    on_reset: FormEvent[TElement]
    on_reset_capture: FormEvent[TElement]
    on_submit: FormEvent[TElement]
    on_submit_capture: FormEvent[TElement]
    on_invalid: FormEvent[TElement]
    on_invalid_capture: FormEvent[TElement]

    # Image/Media-ish Events (using SyntheticEvent by default)
    on_load: SyntheticEvent[TElement]
    on_load_capture: SyntheticEvent[TElement]
    on_error: SyntheticEvent[TElement]
    on_error_capture: SyntheticEvent[TElement]

    # Keyboard Events
    on_key_down: KeyboardEvent[TElement]
    on_key_down_capture: KeyboardEvent[TElement]
    on_key_press: KeyboardEvent[TElement]
    on_key_press_capture: KeyboardEvent[TElement]
    on_key_up: KeyboardEvent[TElement]
    on_key_up_capture: KeyboardEvent[TElement]

    # Media Events (default SyntheticEvent payloads)
    on_abort: SyntheticEvent[TElement]
    on_abort_capture: SyntheticEvent[TElement]
    on_can_play: SyntheticEvent[TElement]
    on_can_play_capture: SyntheticEvent[TElement]
    on_can_play_through: SyntheticEvent[TElement]
    on_can_play_through_capture: SyntheticEvent[TElement]
    on_duration_change: SyntheticEvent[TElement]
    on_duration_change_capture: SyntheticEvent[TElement]
    on_emptied: SyntheticEvent[TElement]
    on_emptied_capture: SyntheticEvent[TElement]
    on_encrypted: SyntheticEvent[TElement]
    on_encrypted_capture: SyntheticEvent[TElement]
    on_ended: SyntheticEvent[TElement]
    on_ended_capture: SyntheticEvent[TElement]
    on_loaded_data: SyntheticEvent[TElement]
    on_loaded_data_capture: SyntheticEvent[TElement]
    on_loaded_metadata: SyntheticEvent[TElement]
    on_loaded_metadata_capture: SyntheticEvent[TElement]
    on_load_start: SyntheticEvent[TElement]
    on_load_start_capture: SyntheticEvent[TElement]
    on_pause: SyntheticEvent[TElement]
    on_pause_capture: SyntheticEvent[TElement]
    on_play: SyntheticEvent[TElement]
    on_play_capture: SyntheticEvent[TElement]
    on_playing: SyntheticEvent[TElement]
    on_playing_capture: SyntheticEvent[TElement]
    on_progress: SyntheticEvent[TElement]
    on_progress_capture: SyntheticEvent[TElement]
    on_rate_change: SyntheticEvent[TElement]
    on_rate_change_capture: SyntheticEvent[TElement]
    on_resize: SyntheticEvent[TElement]
    on_resize_capture: SyntheticEvent[TElement]
    on_seeked: SyntheticEvent[TElement]
    on_seeked_capture: SyntheticEvent[TElement]
    on_seeking: SyntheticEvent[TElement]
    on_seeking_capture: SyntheticEvent[TElement]
    on_stalled: SyntheticEvent[TElement]
    on_stalled_capture: SyntheticEvent[TElement]
    on_suspend: SyntheticEvent[TElement]
    on_suspend_capture: SyntheticEvent[TElement]
    on_time_update: SyntheticEvent[TElement]
    on_time_update_capture: SyntheticEvent[TElement]
    on_volume_change: SyntheticEvent[TElement]
    on_volume_change_capture: SyntheticEvent[TElement]
    on_waiting: SyntheticEvent[TElement]
    on_waiting_capture: SyntheticEvent[TElement]

    # Mouse Events
    on_aux_click: MouseEvent[TElement]
    on_aux_click_capture: MouseEvent[TElement]
    on_click: MouseEvent[TElement]
    on_click_capture: MouseEvent[TElement]
    on_context_menu: MouseEvent[TElement]
    on_context_menu_capture: MouseEvent[TElement]
    on_double_click: MouseEvent[TElement]
    on_double_click_capture: MouseEvent[TElement]
    on_drag: DragEvent[TElement]
    on_drag_capture: DragEvent[TElement]
    on_drag_end: DragEvent[TElement]
    on_drag_end_capture: DragEvent[TElement]
    on_drag_enter: DragEvent[TElement]
    on_drag_enter_capture: DragEvent[TElement]
    on_drag_exit: DragEvent[TElement]
    on_drag_exit_capture: DragEvent[TElement]
    on_drag_leave: DragEvent[TElement]
    on_drag_leave_capture: DragEvent[TElement]
    on_drag_over: DragEvent[TElement]
    on_drag_over_capture: DragEvent[TElement]
    on_drag_start: DragEvent[TElement]
    on_drag_start_capture: DragEvent[TElement]
    on_drop: DragEvent[TElement]
    on_drop_capture: DragEvent[TElement]
    on_mouse_down: MouseEvent[TElement]
    on_mouse_down_capture: MouseEvent[TElement]
    on_mouse_enter: MouseEvent[TElement]
    on_mouse_leave: MouseEvent[TElement]
    on_mouse_move: MouseEvent[TElement]
    on_mouse_move_capture: MouseEvent[TElement]
    on_mouse_out: MouseEvent[TElement]
    on_mouse_out_capture: MouseEvent[TElement]
    on_mouse_over: MouseEvent[TElement]
    on_mouse_over_capture: MouseEvent[TElement]
    on_mouse_up: MouseEvent[TElement]
    on_mouse_up_capture: MouseEvent[TElement]

    # Selection Events
    on_select: SyntheticEvent[TElement]
    on_select_capture: SyntheticEvent[TElement]

    # Touch Events
    on_touch_cancel: TouchEvent[TElement]
    on_touch_cancel_capture: TouchEvent[TElement]
    on_touch_end: TouchEvent[TElement]
    on_touch_end_capture: TouchEvent[TElement]
    on_touch_move: TouchEvent[TElement]
    on_touch_move_capture: TouchEvent[TElement]
    on_touch_start: TouchEvent[TElement]
    on_touch_start_capture: TouchEvent[TElement]

    # Pointer Events
    on_pointer_down: PointerEvent[TElement]
    on_pointer_down_capture: PointerEvent[TElement]
    on_pointer_move: PointerEvent[TElement]
    on_pointer_move_capture: PointerEvent[TElement]
    on_pointer_up: PointerEvent[TElement]
    on_pointer_up_capture: PointerEvent[TElement]
    on_pointer_cancel: PointerEvent[TElement]
    on_pointer_cancel_capture: PointerEvent[TElement]
    on_pointer_enter: PointerEvent[TElement]
    on_pointer_leave: PointerEvent[TElement]
    on_pointer_over: PointerEvent[TElement]
    on_pointer_over_capture: PointerEvent[TElement]
    on_pointer_out: PointerEvent[TElement]
    on_pointer_out_capture: PointerEvent[TElement]
    on_got_pointer_capture: PointerEvent[TElement]
    on_got_pointer_capture_capture: PointerEvent[TElement]
    on_lost_pointer_capture: PointerEvent[TElement]
    on_lost_pointer_capture_capture: PointerEvent[TElement]

    # UI Events
    on_scroll: UIEvent[TElement]
    on_scroll_capture: UIEvent[TElement]
    on_scroll_end: UIEvent[TElement]
    on_scroll_end_capture: UIEvent[TElement]

    # Wheel Events
    on_wheel: WheelEvent[TElement]
    on_wheel_capture: WheelEvent[TElement]

    # Animation Events
    on_animation_start: AnimationEvent[TElement]
    on_animation_start_capture: AnimationEvent[TElement]
    on_animation_end: AnimationEvent[TElement]
    on_animation_end_capture: AnimationEvent[TElement]
    on_animation_iteration: AnimationEvent[TElement]
    on_animation_iteration_capture: AnimationEvent[TElement]

    # Toggle Events
    on_toggle: ToggleEvent[TElement]
    on_before_toggle: ToggleEvent[TElement]

    # Transition Events
    on_transition_cancel: TransitionEvent[TElement]
    on_transition_cancel_capture: TransitionEvent[TElement]
    on_transition_end: TransitionEvent[TElement]
    on_transition_end_capture: TransitionEvent[TElement]
    on_transition_run: TransitionEvent[TElement]
    on_transition_run_capture: TransitionEvent[TElement]
    on_transition_start: TransitionEvent[TElement]
    on_transition_start_capture: TransitionEvent[TElement]


class FormControlDOMEvents(DOMEvents[TElement], total=False):
    """Specialized DOMEvents where on_change is a ChangeEvent.

    Use this for inputs, textareas, and selects.
    """

    on_change: ChangeEvent[TElement]


class InputDOMEvents(FormControlDOMEvents[HTMLInputElement], total=False):
    pass


class TextAreaDOMEvents(FormControlDOMEvents[HTMLTextAreaElement], total=False):
    pass


class SelectDOMEvents(FormControlDOMEvents[HTMLSelectElement], total=False):
    pass


class DialogDOMEvents(DOMEvents[HTMLDialogElement], total=False):
    on_cancel: SyntheticEvent[HTMLDialogElement]
    on_close: SyntheticEvent[HTMLDialogElement]
