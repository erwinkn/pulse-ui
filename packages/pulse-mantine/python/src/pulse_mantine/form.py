from typing import Any, Literal, Optional, TypedDict, Unpack
import pulse as ps


FormValidationMode = Literal["submit", "blur", "change"]


class FormProps(TypedDict, total=False):
    validate: Any
    initialValues: dict[str, Any]
    initialErrors: dict[str, Any]
    initialDirty: dict[str, bool]
    initialTouched: dict[str, bool]
    messages: list[dict[str, Any]]
    validationMode: FormValidationMode
    validationDebounce: int
    formProps: dict[str, Any]


@ps.react_component("Form", "pulse-mantine")
def FormRoot(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[FormProps]
): ...


class Form(ps.State):
    """Form controller that manages a message log consumed by the client Form.

    Usage inside a component:

        form = ps.states(Form)
        return form.mount(initialValues={...})[
            FormTextInput(name="email", label="Email"),
            ...
        ]

        # Later within event handlers
        form.set_field_value("email", "foo@bar.com")

    """

    messages: list[dict[str, Any]] = []

    # Mount the React component, wiring messages and passing through props
    def Component(self, *children: ps.Child, key: Optional[str] = None, **props):
        return FormRoot(*children, key=key, messages=self.messages, **props)

    # Append a message helper
    def _append(self, msg: dict[str, Any]) -> None:
        self.messages = [*self.messages, msg]

    # Public API mapping to Mantine useForm actions
    def set_values(self, values: dict[str, Any]):
        self._append({"type": "setValues", "values": values})

    def set_field_value(self, path: str, value: Any):
        self._append({"type": "setFieldValue", "path": path, "value": value})

    def insert_list_item(self, path: str, item: Any, index: Optional[int] = None):
        msg: dict[str, Any] = {"type": "insertListItem", "path": path, "item": item}
        if index is not None:
            msg["index"] = index
        self._append(msg)

    def remove_list_item(self, path: str, index: int):
        self._append({"type": "removeListItem", "path": path, "index": index})

    def reorder_list_item(self, path: str, frm: int, to: int):
        self._append({"type": "reorderListItem", "path": path, "from": frm, "to": to})

    def set_errors(self, errors: dict[str, Any]):
        self._append({"type": "setErrors", "errors": errors})

    def set_field_error(self, path: str, error: Any):
        self._append({"type": "setFieldError", "path": path, "error": error})

    def clear_errors(self, *paths: str):
        self._append({"type": "clearErrors", "paths": list(paths) if paths else None})

    def set_touched(self, touched: dict[str, bool]):
        self._append({"type": "setTouched", "touched": touched})

    def validate(self):
        self._append({"type": "validate"})

    def reset(self, initial_values: Optional[dict[str, Any]] = None):
        msg: dict[str, Any] = {"type": "reset"}
        if initial_values is not None:
            msg["initialValues"] = initial_values
        self._append(msg)
