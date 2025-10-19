from typing import (
	Any,
	Literal,
	Required,
	Unpack,
)

import pulse as ps

from pulse_mantine.form.validators import SerializedValidation

FormMode = Literal["controlled", "uncontrolled"]


class FormInternalProps(ps.HTMLFormProps, total=False):
	channelId: Required[str]  # pyright: ignore[reportGeneralTypeIssues]
	initialValues: dict[str, Any]
	initialErrors: dict[str, Any]
	initialDirty: dict[str, bool]
	initialTouched: dict[str, bool]

	mode: FormMode
	validate: "SerializedValidation"
	validateInputOnBlur: bool | list[str]
	validateInputOnChange: bool | list[str]
	clearInputErrorOnChange: bool
	debounceMs: int
	syncMode: Literal["none", "onBlur", "onChange"]
	syncDebounceMs: int
	action: Required[str]  # pyright: ignore[reportGeneralTypeIssues]

	# Server validation
	onSubmit: ps.EventHandler1[ps.FormEvent[ps.HTMLFormElement]]
	onServerValidation: ps.EventHandler3[Any, dict[str, Any], str]
	onReset: ps.EventHandler1[ps.FormEvent[ps.HTMLFormElement]]


@ps.react_component("Form", "pulse-mantine")
def FormInternal(
	*children: ps.Child, key: str | None = None, **props: Unpack[FormInternalProps]
): ...
