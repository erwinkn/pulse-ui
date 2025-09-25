from typing import (
    Any,
    Literal,
    Optional,
    Required,
    Union,
    Unpack,
)

import pulse as ps
from pulse_mantine.form.validators import SerializedValidation


FormMode = Literal["controlled", "uncontrolled"]


class FormInternalProps(ps.HTMLFormProps, total=False):
    initialValues: dict[str, Any]
    initialErrors: dict[str, Any]
    initialDirty: dict[str, bool]
    initialTouched: dict[str, bool]

    mode: FormMode
    validate: "SerializedValidation"
    validateInputOnBlur: Union[bool, list[str]]
    validateInputOnChange: Union[bool, list[str]]
    clearInputErrorOnChange: bool
    debounceMs: int
    action: Required[str]  # pyright: ignore[reportGeneralTypeIssues]

    # Server validation
    onSubmit: ps.EventHandler1[ps.FormEvent[ps.HTMLFormElement]]
    onServerValidation: ps.EventHandler3[Any, dict[str, Any], str]
    onReset: ps.EventHandler1[ps.FormEvent[ps.HTMLFormElement]]
    onGetFormValues: ps.EventHandler2[str, dict[str, Any]]
    messages: list[dict[str, Any]]


@ps.react_component("Form", "pulse-mantine")
def FormInternal(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[FormInternalProps]
): ...
