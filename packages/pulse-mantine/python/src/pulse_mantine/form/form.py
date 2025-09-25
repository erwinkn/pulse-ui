from asyncio import Future
from datetime import datetime
from typing import (
    Any,
    Generic,
    Literal,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
    Union,
    Unpack,
)
from uuid import uuid4

import pulse as ps
import json
from pulse.serializer_v3 import deserialize
from pulse.helpers import call_flexible, create_future_on_loop

from .internal import FormInternal, FormMode
from .validators import (
    ServerValidation,
    Validation,
    Validator,
    serialize_validation,
)

FieldValue = str | int | float | bool | datetime | ps.UploadFile
FormValues = Mapping[str, Union[FieldValue, Sequence[FieldValue], "FormValues"]]

TForm = TypeVar("TForm", bound=FormValues)


class MantineFormProps(ps.HTMLFormProps, Generic[TForm], total=False):
    mode: FormMode
    validate: "Validation"
    initialValues: dict[str, Any]
    initialErrors: dict[str, Any]
    initialDirty: dict[str, bool]
    initialTouched: dict[str, bool]
    validateInputOnBlur: Union[bool, list[str]]
    validateInputOnChange: Union[bool, list[str]]
    clearInputErrorOnChange: bool
    cascadeUpdates: bool
    debounceMs: int
    touchTrigger: Literal["change", "focus"]
    """touchTrigger option allows customizing events that change touched state.

    Options:
        change (default): Field is touched when value changes or has been focused
        focus: Field is touched only when it has been focused
    """
    onSubmit: ps.EventHandler1[TForm]  # pyright: ignore[reportIncompatibleVariableOverride]
    onReset: ps.EventHandler1[ps.FormEvent[ps.HTMLFormElement]]


class MantineForm(ps.State, Generic[TForm]):
    messages: list[dict[str, Any]]

    def __init__(
        self,
        mode: FormMode | None = None,
        validate: "Validation | None" = None,
        initialValues: dict[str, Any] | None = None,
        initialErrors: dict[str, Any] | None = None,
        initialDirty: dict[str, bool] | None = None,
        initialTouched: dict[str, bool] | None = None,
        validateInputOnBlur: Union[bool, list[str]] | None = None,
        validateInputOnChange: Union[bool, list[str]] | None = None,
        clearInputErrorOnChange: bool | None = None,
        debounceMs: int | None = None,
        touchTrigger: Literal["change", "focus"] | None = None,
    ):
        self.messages = []
        print("MantinForm instantiation, self.messages is ReactiveList:", isinstance(self.messages, ps.ReactiveList))

        self._form = ps.ManualForm(on_submit=self._handle_form_data)
        self._futures: dict[str, Future] = {}

        self._validation = validate
        self._mantine_props = {
            "validate": serialize_validation(validate) if validate else None,
            "initialValues": initialValues,
            "initialErrors": initialErrors,
            "initialDirty": initialDirty,
            "initialTouched": initialTouched,
            "validateInputOnBlur": validateInputOnBlur,
            "validateInputOnChange": validateInputOnChange,
            "clearInputErrorOnChange": clearInputErrorOnChange,
            "debounceMs": debounceMs,
            "touchTrigger": touchTrigger,
        }
        # Filter out None values
        self._mantine_props = {
            k: v for k, v in self._mantine_props.items() if v is not None
        }

        _check_for_reserved_keys(initialValues)
        _check_for_reserved_keys(initialErrors)
        _check_for_reserved_keys(initialDirty)
        _check_for_reserved_keys(initialTouched)

    async def _handle_form_data(self, data: ps.FormData):
        # Expect one JSON-serialized entry under "__data__" with v3 serializer
        # and remaining entries are files keyed by their dot/bracket paths.
        raw = data.get("__data__")
        base: dict[str, Any] = {}
        if isinstance(raw, str) and raw:
            try:
                payload = json.loads(raw)
                base = deserialize(payload)
            except Exception:
                base = {}

        # Merge file entries back into the nested structure
        files: dict[str, Any] = {k: v for k, v in data.items() if k != "__data__"}
        result = _merge_files_into_structure(base, files)

        # Forward to user onSubmit if provided
        if self._on_submit is not None:
            await call_flexible(self._on_submit, result)  # pyright: ignore[reportArgumentType]
        else:
            print("Received form data (reshaped):", result)

    # Mount the React component, wiring messages and passing through props
    def render(
        self,
        *children: ps.Child,
        key: Optional[str] = None,
        onSubmit: ps.EventHandler1[TForm] | None = None,
        **props: Unpack[ps.HTMLFormProps],  # pyright: ignore[reportGeneralTypeIssues]
    ):
        self._on_submit = onSubmit
        merged = {**props, **self._mantine_props, **self._form.props()}
        print("Rendering form")

        return FormInternal(
            *children,
            key=key,
            messages=self.messages,
            onServerValidation=self._on_server_validation,
            onGetFormValues=self._on_get_form_values,
            **merged,
        )

    # Append a message helper
    def _append(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)

    # Public API mapping to Mantine useForm actions
    async def get_form_values(self):
        request_id = uuid4().hex
        fut = create_future_on_loop()
        self._futures[request_id] = fut
        self.messages.append({"type": "getFormValues", "id": request_id})
        print("Sending message getFormValues")
        return await fut

    def _on_get_form_values(self, request_id: str, values: dict[str, Any]):
        fut = self._futures.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(values)

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
        schema = self._validation
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
        if isinstance(node, dict):
            node = node.get("formRootRule")
        if isinstance(node, list):
            specs = [s for s in node if isinstance(s, Validator)]
        if isinstance(node, Validator):
            specs = [node]

        # Invoke server validators, stop on first error
        for spec in specs:
            if isinstance(spec, ServerValidation):
                fn = spec.fn
                try:
                    res = fn(value, values, path)
                    if isinstance(res, str) and res:
                        self.set_field_error(path, res)
                        return
                except Exception:
                    # Do not crash validation on server errors; surface generic error
                    self.set_field_error(path, "Validation failed")
                    return
        self.clear_errors(path)


# Also ensure user data objects do not contain reserved keys
def _check_for_reserved_keys(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"$kind", "formRootRule"}:
                raise ValueError(
                    "'$kind' and 'formRootRule' are reserved keys and cannot appear in user data"
                )
            _check_for_reserved_keys(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            _check_for_reserved_keys(v, f"{path}[{idx}]")


def _merge_files_into_structure(base: Any, files: dict[str, Any]) -> Any:
    result = _deep_copy(base)

    # Expand lists of files into multiple insert operations
    def iter_entries():
        for path, value in files.items():
            if isinstance(value, list):
                for item in value:
                    yield (path, item)
            else:
                yield (path, value)

    for path, value in iter_entries():
        segments = _tokenize_path(path)
        _set_deep(result, segments, value)
    return result


def _deep_copy(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deep_copy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_copy(v) for v in obj]
    return obj


def _tokenize_path(path: str) -> list[str]:
    # Convert bracket notation to dots: a[0].b -> a.0.b
    out: list[str] = []
    buf = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == "[":
            if buf:
                out.append(buf)
                buf = ""
            j = i + 1
            num = ""
            while j < len(path) and path[j] != "]":
                num += path[j]
                j += 1
            if num:
                out.append(num)
            i = j + 1
            if i < len(path) and path[i] == ".":
                i += 1
            continue
        elif ch == ".":
            if buf:
                out.append(buf)
                buf = ""
        else:
            buf += ch
        i += 1
    if buf:
        out.append(buf)
    return [seg for seg in out if seg]


def _ensure_container(parent: Any, key: str | int, next_is_index: bool):
    if isinstance(key, int):
        # Parent must be a list
        if not isinstance(parent, list):
            return []
        # Ensure capacity
        while len(parent) <= key:
            parent.append(None)
        child = parent[key]
        if child is None:
            parent[key] = [] if next_is_index else {}
            child = parent[key]
        return child
    else:
        if not isinstance(parent, dict):
            return {}
        child = parent.get(key)
        if child is None:
            parent[key] = [] if next_is_index else {}
            child = parent[key]
        return child


def _set_deep(root: Any, segments: list[str], value: Any) -> None:
    # Walk creating containers as needed; set or append at leaf
    cur = root
    for idx, raw_seg in enumerate(segments):
        is_last = idx == len(segments) - 1
        is_index = raw_seg.isdigit()
        seg: int | str = int(raw_seg) if is_index else raw_seg
        if is_last:
            if isinstance(seg, int):
                if not isinstance(cur, list):
                    return
                while len(cur) <= seg:
                    cur.append(None)
                existing = cur[seg]
                if existing is None:
                    cur[seg] = value
                else:
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        cur[seg] = [existing, value]
            else:
                if not isinstance(cur, dict):
                    return
                existing = cur.get(seg)
                if existing is None:
                    cur[seg] = value
                else:
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        cur[seg] = [existing, value]
        else:
            next_is_index = segments[idx + 1].isdigit()
            child = _ensure_container(cur, seg, next_is_index)
            # Attach child back to parent in case container was created
            if isinstance(seg, int):
                if not isinstance(cur, list):
                    return
                while len(cur) <= seg:
                    cur.append(None)
                cur[seg] = child
            else:
                if not isinstance(cur, dict):
                    return
                cur[seg] = child
            cur = child
