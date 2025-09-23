from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Unpack,
    Union,
    TypeAlias,
    cast,
)
import pulse as ps


FormMode = Literal["controlled", "uncontrolled"]


class FormProps(ps.HTMLFormProps, total=False):
    validate: "Validation"
    initialValues: dict[str, Any]
    initialErrors: dict[str, Any]
    initialDirty: dict[str, bool]
    initialTouched: dict[str, bool]
    # Mantine useForm options
    mode: FormMode
    validateInputOnBlur: Union[bool, list[str]]
    validateInputOnChange: Union[bool, list[str]]
    clearInputErrorOnChange: bool
    # Form behavior
    onSubmitPreventDefault: bool
    debounceMs: int


class FormPropsInternal(FormProps, total=False):
    messages: list[dict[str, Any]]
    validate: "SerializedValidation"  # pyright: ignore[reportIncompatibleVariableOverride]
    # Server validation
    onServerValidation: Callable[[Any, dict[str, Any], str], str | None]


@ps.react_component("Form", "pulse-mantine")
def FormRoot(
    *children: ps.Child, key: Optional[str] = None, **props: Unpack[FormPropsInternal]
): ...


class Validator:
    def to_serializable(self) -> dict[str, Any]:
        raise NotImplementedError


class IsNotEmpty(Validator):
    def __init__(self, error: Any | None = None) -> None:
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        return {"$kind": "isNotEmpty", "error": self.error}


class IsEmail(Validator):
    def __init__(self, error: Any | None = None) -> None:
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        return {"$kind": "isEmail", "error": self.error}


class Matches(Validator):
    def __init__(
        self, pattern: str, *, flags: str | None = None, error: Any | None = None
    ) -> None:
        self.pattern = pattern
        self.flags = flags
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        return {
            "$kind": "matches",
            "pattern": self.pattern,
            "flags": self.flags,
            "error": self.error,
        }


class IsInRange(Validator):
    def __init__(
        self,
        *,
        min: float | None = None,
        max: float | None = None,
        error: Any | None = None,
    ) -> None:
        self.min = min
        self.max = max
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "isInRange", "error": self.error}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return payload


class HasLength(Validator):
    def __init__(
        self,
        *,
        min: int | None = None,
        max: int | None = None,
        exact: int | None = None,
        error: Any | None = None,
    ) -> None:
        self.min = min
        self.max = max
        self.exact = exact
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "hasLength", "error": self.error}
        if self.exact is not None:
            payload["exact"] = self.exact
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return payload


class MatchesField(Validator):
    def __init__(self, field: str, error: Any | None = None) -> None:
        self.field = field
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        return {"$kind": "matchesField", "field": self.field, "error": self.error}


class IsJSONString(Validator):
    def __init__(self, error: Any | None = None) -> None:
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        return {"$kind": "isJSONString", "error": self.error}


class IsNotEmptyHTML(Validator):
    def __init__(self, error: Any | None = None) -> None:
        self.error = error

    def to_serializable(self) -> dict[str, Any]:
        return {"$kind": "isNotEmptyHTML", "error": self.error}


class ServerValidation(Validator):
    def __init__(
        self,
        fn: Callable[[Any, dict[str, Any], str], str | None],
        debounce_ms: float | None = None,
    ) -> None:
        self.fn = fn
        self.debounce_ms = debounce_ms

    def to_serializable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "server"}
        if self.debounce_ms is not None:
            payload["debounceMs"] = self.debounce_ms
        return payload


ValidationNode: TypeAlias = Union[
    Validator, Sequence[Validator], Mapping[str, "ValidationNode"]
]
Validation: TypeAlias = Mapping[str, ValidationNode]

SerializedValidationNode = Union[
    dict[str, str], list[dict[str, str]], "dict[str, SerializedValidation]"
]

SerializedValidation = dict[str, SerializedValidationNode]


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
    _validator_schema: Optional[Validation] = None

    # Mount the React component, wiring messages and passing through props
    def Component(
        self, *children: ps.Child, key: Optional[str] = None, **props: Unpack[FormProps]
    ):
        # Capture user-provided schema with callables for server validators
        schema = props.pop("validate", None)
        internal_props = cast(dict[str, Any], props)
        if isinstance(schema, dict):
            self._validator_schema = schema  # keep original with callables
            internal_props["validate"] = {
                k: serialize_validation(v) for k, v in schema.items()
            }

        for key_name in (
            "initialValues",
            "initialErrors",
            "initialDirty",
            "initialTouched",
        ):
            val = props.get(key_name)
            if isinstance(val, (dict, list)):
                ensure_no_reserved_in_user_data(val)

        return FormRoot(
            *children,
            key=key,
            messages=self.messages,
            onServerValidation=self._on_server_validation,
            **internal_props,
        )

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

    # Internal: route server validation to the correct user-specified callable
    def _on_server_validation(
        self, value: Any, values: dict[str, Any], path: str
    ) -> None:
        schema = self._validator_schema
        if not isinstance(schema, dict):
            return

        # Traverse schema by path segments, skipping numeric indices
        node: Any = schema
        for seg in str(path).split("."):
            if isinstance(node, dict):
                # Skip numeric segments (list indices)
                if seg.isdigit():
                    continue
                nxt = node.get(seg)
                if nxt is None:
                    # Try root-level rule fallback
                    nxt = node.get("formRootRule")
                node = nxt
            else:
                break

        # Node can be a spec, a list of specs, or nested dict
        specs: list[Validator] = []
        if isinstance(node, list):
            specs = [s for s in node if isinstance(s, Validator)]
        elif isinstance(node, Validator):
            specs = [node]
        elif isinstance(node, dict):
            rr = node.get("formRootRule") if isinstance(node, dict) else None
            if isinstance(rr, list):
                specs = [s for s in rr if isinstance(s, Validator)]
            elif isinstance(rr, Validator):
                specs = [rr]

        # Invoke first server validator with a callable
        for spec in specs:
            if isinstance(spec, ServerValidation):
                fn = spec.fn
                try:
                    res = fn(value, values, path)
                    if isinstance(res, str) and res:
                        self.set_field_error(path, res)
                    else:
                        self.clear_errors(path)
                except Exception:
                    # Do not crash validation on server errors; surface generic error
                    self.set_field_error(path, "Validation failed")
                break


# Also ensure user data objects do not contain reserved keys
def ensure_no_reserved_in_user_data(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"$kind", "formRootRule"}:
                raise ValueError(
                    "'$kind' and 'formRootRule' are reserved keys and cannot appear in user data"
                )
            ensure_no_reserved_in_user_data(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            ensure_no_reserved_in_user_data(v, f"{path}[{idx}]")


def serialize_validation(node: ValidationNode) -> SerializedValidationNode:
    # Convert classes to serializable dicts using $kind and drop server fn
    if isinstance(node, Validator):
        return node.to_serializable()
    if isinstance(node, Sequence):
        out_list: list[dict[str, str]] = []
        for spec in node:
            if isinstance(spec, Validator):
                out_list.append(spec.to_serializable())
        return out_list
    if isinstance(node, Mapping):
        out: dict[str, Any] = {}
        for k, v in node.items():
            check_for_reserved_key(k, v)
            out[str(k)] = serialize_validation(v)
        return out
    raise ValueError(f"Unsupported validation node: {node}")


# Reserved keys guard and serialization to client schema with "$kind"
def check_for_reserved_key(k: str, v: ValidationNode) -> None:
    if k == "$kind":
        raise ValueError(
            "'$kind' is a reserved key and cannot be used in the user's data structure"
        )
    if k == "formRootRule":
        # It must be a spec or list of specs
        if not (
            isinstance(v, Validator)
            or (isinstance(v, list) and all(isinstance(i, Validator) for i in v))
        ):
            raise ValueError(
                "'formRootRule' is a reserved key and cannot be used as a field name"
            )
