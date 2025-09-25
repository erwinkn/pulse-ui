from abc import ABC, abstractmethod
from typing import (
    Any,
    Callable,
    Mapping,
    Sequence,
    Union,
    TypeAlias,
)


class Validator(ABC):
    @abstractmethod
    def serialize(self) -> dict[str, Any]: ...


class IsNotEmpty(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isNotEmpty", "error": self.error}


class IsEmail(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isEmail", "error": self.error}


class Matches(Validator):
    def __init__(
        self, pattern: str, *, flags: str | None = None, error: str | None = None
    ) -> None:
        self.pattern = pattern
        self.flags = flags
        self.error = error

    def serialize(self) -> dict[str, Any]:
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
        error: str | None = None,
    ) -> None:
        self.min = min
        self.max = max
        self.error = error

    def serialize(self) -> dict[str, Any]:
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
        error: str | None = None,
    ) -> None:
        self.min = min
        self.max = max
        self.exact = exact
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "hasLength", "error": self.error}
        if self.exact is not None:
            payload["exact"] = self.exact
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return payload


class MatchesField(Validator):
    def __init__(self, field: str, error: str | None = None) -> None:
        self.field = field
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "matchesField", "field": self.field, "error": self.error}


class IsJSONString(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isJSONString", "error": self.error}


class IsNotEmptyHTML(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isNotEmptyHTML", "error": self.error}


class IsUrl(Validator):
    def __init__(
        self,
        *,
        protocols: Sequence[str] | None = None,
        require_protocol: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.protocols = list(protocols) if protocols is not None else None
        self.require_protocol = require_protocol
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "isUrl", "error": self.error}
        if self.protocols is not None:
            payload["protocols"] = self.protocols
        if self.require_protocol is not None:
            payload["requireProtocol"] = self.require_protocol
        return payload


class IsUUID(Validator):
    def __init__(self, version: int | None = None, error: str | None = None) -> None:
        self.version = version
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "isUUID", "error": self.error}
        if self.version is not None:
            payload["version"] = self.version
        return payload


class IsULID(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isULID", "error": self.error}


class IsNumber(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isNumber", "error": self.error}


class IsInteger(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isInteger", "error": self.error}


class IsDate(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isDate", "error": self.error}


class IsISODate(Validator):
    def __init__(
        self, *, with_time: bool | None = None, error: str | None = None
    ) -> None:
        self.with_time = with_time
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "isISODate", "error": self.error}
        if self.with_time is not None:
            payload["withTime"] = self.with_time
        return payload


class IsBefore(Validator):
    def __init__(
        self,
        field: str | None = None,
        *,
        value: Any | None = None,
        inclusive: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.field = field
        self.value = value
        self.inclusive = inclusive
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "isBefore", "error": self.error}
        if self.field is not None:
            payload["field"] = self.field
        if self.value is not None:
            payload["value"] = self.value
        if self.inclusive is not None:
            payload["inclusive"] = self.inclusive
        return payload


class IsAfter(Validator):
    def __init__(
        self,
        field: str | None = None,
        *,
        value: Any | None = None,
        inclusive: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.field = field
        self.value = value
        self.inclusive = inclusive
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "isAfter", "error": self.error}
        if self.field is not None:
            payload["field"] = self.field
        if self.value is not None:
            payload["value"] = self.value
        if self.inclusive is not None:
            payload["inclusive"] = self.inclusive
        return payload


class MinItems(Validator):
    def __init__(self, count: int, error: str | None = None) -> None:
        self.count = count
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "minItems", "count": self.count, "error": self.error}


class MaxItems(Validator):
    def __init__(self, count: int, error: str | None = None) -> None:
        self.count = count
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "maxItems", "count": self.count, "error": self.error}


class IsArrayNotEmpty(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isArrayNotEmpty", "error": self.error}


class AllowedFileTypes(Validator):
    def __init__(
        self,
        *,
        mime_types: Sequence[str] | None = None,
        extensions: Sequence[str] | None = None,
        error: str | None = None,
    ) -> None:
        self.mime_types = list(mime_types) if mime_types is not None else None
        self.extensions = list(extensions) if extensions is not None else None
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "allowedFileTypes", "error": self.error}
        if self.mime_types is not None:
            payload["mimeTypes"] = self.mime_types
        if self.extensions is not None:
            payload["extensions"] = self.extensions
        return payload


class MaxFileSize(Validator):
    def __init__(self, bytes: int, error: str | None = None) -> None:
        self.bytes = bytes
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "maxFileSize", "bytes": self.bytes, "error": self.error}


class RequiredWhen(Validator):
    def __init__(
        self,
        field: str,
        *,
        equals: Any | None = None,
        not_equals: Any | None = None,
        in_values: Sequence[Any] | None = None,
        not_in_values: Sequence[Any] | None = None,
        truthy: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.field = field
        self.equals = equals
        self.not_equals = not_equals
        self.in_values = list(in_values) if in_values is not None else None
        self.not_in_values = list(not_in_values) if not_in_values is not None else None
        self.truthy = truthy
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "$kind": "requiredWhen",
            "field": self.field,
            "error": self.error,
        }
        if self.equals is not None:
            payload["equals"] = self.equals
        if self.not_equals is not None:
            payload["notEquals"] = self.not_equals
        if self.in_values is not None:
            payload["in"] = self.in_values
        if self.not_in_values is not None:
            payload["notIn"] = self.not_in_values
        if self.truthy is not None:
            payload["truthy"] = self.truthy
        return payload


class RequiredUnless(Validator):
    def __init__(
        self,
        field: str,
        *,
        equals: Any | None = None,
        not_equals: Any | None = None,
        in_values: Sequence[Any] | None = None,
        not_in_values: Sequence[Any] | None = None,
        truthy: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.field = field
        self.equals = equals
        self.not_equals = not_equals
        self.in_values = list(in_values) if in_values is not None else None
        self.not_in_values = list(not_in_values) if not_in_values is not None else None
        self.truthy = truthy
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "$kind": "requiredUnless",
            "field": self.field,
            "error": self.error,
        }
        if self.equals is not None:
            payload["equals"] = self.equals
        if self.not_equals is not None:
            payload["notEquals"] = self.not_equals
        if self.in_values is not None:
            payload["in"] = self.in_values
        if self.not_in_values is not None:
            payload["notIn"] = self.not_in_values
        if self.truthy is not None:
            payload["truthy"] = self.truthy
        return payload


class StartsWith(Validator):
    def __init__(
        self,
        value: str,
        *,
        case_sensitive: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.value = value
        self.case_sensitive = case_sensitive
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "$kind": "startsWith",
            "value": self.value,
            "error": self.error,
        }
        if self.case_sensitive is not None:
            payload["caseSensitive"] = self.case_sensitive
        return payload


class EndsWith(Validator):
    def __init__(
        self,
        value: str,
        *,
        case_sensitive: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.value = value
        self.case_sensitive = case_sensitive
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "$kind": "endsWith",
            "value": self.value,
            "error": self.error,
        }
        if self.case_sensitive is not None:
            payload["caseSensitive"] = self.case_sensitive
        return payload


class ServerValidation(Validator):
    def __init__(
        self,
        fn: Callable[[Any, dict[str, Any], str], str | None],
        debounce_ms: float | None = None,
    ) -> None:
        self.fn = fn
        self.debounce_ms = debounce_ms

    def serialize(self) -> dict[str, Any]:
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


def serialize_validation_node(node: ValidationNode) -> SerializedValidationNode:
    # Convert classes to serializable dicts using $kind and drop server fn
    if isinstance(node, Validator):
        return node.serialize()
    if isinstance(node, Sequence):
        out_list: list[dict[str, str]] = []
        for spec in node:
            if isinstance(spec, Validator):
                out_list.append(spec.serialize())
        return out_list
    if isinstance(node, Mapping):
        out: dict[str, Any] = {}
        for k, v in node.items():
            check_for_reserved_key(k, v)
            out[str(k)] = serialize_validation_node(v)
        return out
    raise ValueError(f"Unsupported validation node: {node}")


def serialize_validation(validation: Validation) -> SerializedValidation:
    return {k: serialize_validation_node(v) for k, v in validation.items()}


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
