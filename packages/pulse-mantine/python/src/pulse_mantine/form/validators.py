import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import (
    Any,
    Callable,
    Mapping,
    Sequence,
    TypeAlias,
    Union,
)
from urllib.parse import urlparse

from dateutil import parser as date_parser
from pulse.form import UploadFile


class Validator(ABC):
    @abstractmethod
    def serialize(self) -> dict[str, Any]: ...

    # Server-side check: return error message or None
    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        return None


# --- helpers mirrored from client logic ---------------------------------------


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return len(value.strip()) == 0
    if isinstance(value, list):
        return len(value) == 0
    return False


def _get_value_at_path(source: Any, path: str) -> Any:
    if not path:
        return None
    cur = source
    for seg in str(path).split("."):
        if seg == "":
            continue
        if isinstance(cur, list) and seg.isdigit():
            idx = int(seg)
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def _coerce_number(value: Any) -> float | None:
    if (
        isinstance(value, (int, float))
        and value == value
        and value not in (float("inf"), float("-inf"))
    ):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            n = float(s)
        except Exception:
            return None
        return n
    return None


def _coerce_comparable(value: Any) -> float | None:
    if isinstance(value, datetime):
        return value.timestamp()
    n = _coerce_number(value)
    if n is not None:
        return n
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # try ISO first
        try:
            dt = datetime.fromisoformat(s)
            return dt.timestamp()
        except Exception:
            pass
        try:
            dt = date_parser.parse(s)
            return dt.timestamp()
        except Exception:
            pass
        return None
    return None


def _coerce_date(value: Any) -> float | None:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s)
            return dt.timestamp()
        except Exception:
            pass
        try:
            dt = date_parser.parse(s)
            return dt.timestamp()
        except Exception:
            pass
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _to_upload_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, UploadFile):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, UploadFile)]
    return []


class IsNotEmpty(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isNotEmpty", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return self.error or "Required"
        return None


class IsEmail(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isEmail", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        s = str(value).strip()
        # simple RFC5322-ish
        pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        if not pattern.match(s):
            return self.error or "Invalid email"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        f = 0
        if self.flags:
            if "i" in self.flags:
                f |= re.IGNORECASE
            if "m" in self.flags:
                f |= re.MULTILINE
            if "s" in self.flags:
                f |= re.DOTALL
            if "x" in self.flags:
                f |= re.VERBOSE
        try:
            rx = re.compile(self.pattern, flags=f)
        except Exception:
            return self.error or "Invalid pattern"
        if not rx.search(str(value)):
            return self.error or "Does not match pattern"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        num = _coerce_number(value)
        if num is None:
            return self.error or "Must be in range"
        if self.min is not None and num < self.min:
            return self.error or f">= {self.min}"
        if self.max is not None and num > self.max:
            return self.error or f"<= {self.max}"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        s = str(value)
        n = len(s)
        if self.exact is not None:
            if n != self.exact:
                return self.error or f"Length must be {self.exact}"
            return None
        if self.min is not None and n < self.min:
            return self.error or f"Min {self.min} chars"
        if self.max is not None and n > self.max:
            return self.error or f"Max {self.max} chars"
        return None


class MatchesField(Validator):
    def __init__(self, field: str, error: str | None = None) -> None:
        self.field = field
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "matchesField", "field": self.field, "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:
        other = _get_value_at_path(values, self.field)
        if other is None:
            return None
        if value != other:
            return self.error or "Values do not match"
        return None


class IsJSONString(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isJSONString", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        try:
            json.loads(str(value))
            return None
        except Exception:
            return self.error or "Invalid JSON"


class IsNotEmptyHTML(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isNotEmptyHTML", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if value is None:
            return self.error or "Required"
        s = str(value)
        # strip tags
        stripped = re.sub(r"<[^>]*>", "", s)
        if len(stripped.strip()) == 0:
            return self.error or "Required"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        s = str(value).strip()
        parsed = urlparse(
            s if re.match(r"^[a-zA-Z][a-zA-Z\d+.-]*:", s) else f"https://{s}"
        )
        if self.require_protocol and not re.match(r"^[a-zA-Z][a-zA-Z\d+.-]*:", s):
            return self.error or "URL must include a protocol"
        if not parsed.netloc:
            return self.error or "Must be a valid URL"
        if self.protocols:
            allowed = [p.rstrip(":").lower() for p in self.protocols if p]
            if allowed:
                scheme = (parsed.scheme or "").lower()
                if scheme not in allowed:
                    return self.error or (
                        f"URL must use protocol{'s' if len(allowed) > 1 else ''}: {', '.join(allowed)}"
                    )
        return None


class IsUUID(Validator):
    def __init__(self, version: int | None = None, error: str | None = None) -> None:
        self.version = version
        self.error = error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"$kind": "isUUID", "error": self.error}
        if self.version is not None:
            payload["version"] = self.version
        return payload

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        s = str(value).strip()
        if self.version is not None:
            rx = re.compile(
                rf"^[0-9a-f]{{8}}-[0-9a-f]{{4}}-{self.version}[0-9a-f]{{3}}-[89ab][0-9a-f]{{3}}-[0-9a-f]{{12}}$",
                re.I,
            )
        else:
            rx = re.compile(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
            )
        if not rx.match(s):
            return self.error or (
                f"Must be a valid UUID v{self.version}"
                if self.version
                else "Must be a valid UUID"
            )
        return None


class IsULID(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isULID", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        s = str(value).strip().upper()
        if not re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", s):
            return self.error or "Must be a valid ULID"
        return None


class IsNumber(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isNumber", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        num = _coerce_number(value)
        if num is None:
            return self.error or "Must be a number"
        return None


class IsInteger(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isInteger", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        num = _coerce_number(value)
        if num is None or int(num) != num:
            return self.error or "Must be an integer"
        return None


class IsDate(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isDate", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        ts = _coerce_date(value)
        if ts is None:
            return self.error or "Must be a valid date"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        if isinstance(value, datetime):
            return None
        s = str(value).strip()
        date_rx = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        dt_rx = re.compile(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(Z|[+-]\d{2}:\d{2})?$"
        )
        ok = bool(dt_rx.match(s)) if self.with_time else bool(date_rx.match(s))
        if not ok:
            return self.error or (
                "Must be an ISO-8601 datetime"
                if self.with_time
                else "Must be an ISO-8601 date"
            )
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:
        other = (
            _get_value_at_path(values, self.field)
            if self.field is not None
            else self.value
        )
        left = _coerce_comparable(value)
        right = _coerce_comparable(other)
        if left is None or right is None:
            return None
        ok = left <= right if self.inclusive else left < right
        if not ok:
            return self.error or "Value must be before target"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:
        other = (
            _get_value_at_path(values, self.field)
            if self.field is not None
            else self.value
        )
        left = _coerce_comparable(value)
        right = _coerce_comparable(other)
        if left is None or right is None:
            return None
        ok = left >= right if self.inclusive else left > right
        if not ok:
            return self.error or "Value must be after target"
        return None


class MinItems(Validator):
    def __init__(self, count: int, error: str | None = None) -> None:
        self.count = count
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "minItems", "count": self.count, "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if value is None:
            length = 0
        elif isinstance(value, list):
            length = len(value)
        else:
            files = _to_upload_list(value)
            length = len(files)
        if length < self.count:
            if self.count == 1:
                return self.error or "Select at least one item"
            return self.error or f"Select at least {self.count} items"
        return None


class MaxItems(Validator):
    def __init__(self, count: int, error: str | None = None) -> None:
        self.count = count
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "maxItems", "count": self.count, "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        if isinstance(value, list):
            length = len(value)
        else:
            files = _to_upload_list(value)
            length = len(files)
        if length > self.count:
            return (
                self.error
                or f"Select no more than {self.count} item{'s' if self.count != 1 else ''}"
            )
        return None


class IsArrayNotEmpty(Validator):
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "isArrayNotEmpty", "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if isinstance(value, list) and len(value) > 0:
            return None
        files = _to_upload_list(value)
        if len(files) > 0:
            return None
        return self.error or "At least one item is required"


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        files = _to_upload_list(value)
        if not files:
            return None
        mime_rules = [m.lower() for m in (self.mime_types or []) if m]
        ext_rules = [e.lower().lstrip(".") for e in (self.extensions or []) if e]
        for f in files:
            mime = (getattr(f, "content_type", "") or "").lower()
            if mime_rules:
                ok = False
                for rule in mime_rules:
                    if rule.endswith("/*"):
                        prefix = rule[:-1]
                        if mime.startswith(prefix):
                            ok = True
                            break
                    elif mime == rule:
                        ok = True
                        break
                if not ok:
                    return self.error or "File type is not allowed"
            if ext_rules:
                name = getattr(f, "filename", "") or ""
                ext = name.split(".")[-1].lower() if "." in name else ""
                if ext not in ext_rules:
                    return self.error or "File extension is not allowed"
        return None


class MaxFileSize(Validator):
    def __init__(self, bytes: int, error: str | None = None) -> None:
        self.bytes = bytes
        self.error = error

    def serialize(self) -> dict[str, Any]:
        return {"$kind": "maxFileSize", "bytes": self.bytes, "error": self.error}

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        for f in _to_upload_list(value):
            try:
                if int(getattr(f, "size")) > int(self.bytes):
                    return self.error or "File is too large"
            except Exception:
                continue
        return None


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

    def _eval_condition(self, v: Any) -> bool:
        if self.equals is not None:
            if v != self.equals:
                return False
        if self.not_equals is not None:
            if v == self.not_equals:
                return False
        if self.in_values is not None:
            if v not in self.in_values:
                return False
        if self.not_in_values is not None:
            if v in self.not_in_values:
                return False
        if self.truthy is not None:
            if bool(v) != bool(self.truthy):
                return False
        elif (
            self.equals is None
            and self.not_equals is None
            and self.in_values is None
            and self.not_in_values is None
        ):
            if not bool(v):
                return False
        return True

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:
        other = _get_value_at_path(values, self.field)
        if not self._eval_condition(other):
            return None
        if _is_empty_value(value):
            return self.error or "This field is required"
        return None


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

    def _eval_condition(self, v: Any) -> bool:
        if self.equals is not None:
            if v != self.equals:
                return False
        if self.not_equals is not None:
            if v == self.not_equals:
                return False
        if self.in_values is not None:
            if v not in self.in_values:
                return False
        if self.not_in_values is not None:
            if v in self.not_in_values:
                return False
        if self.truthy is not None:
            if bool(v) != bool(self.truthy):
                return False
        elif (
            self.equals is None
            and self.not_equals is None
            and self.in_values is None
            and self.not_in_values is None
        ):
            if not bool(v):
                return False
        return True

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:
        other = _get_value_at_path(values, self.field)
        if self._eval_condition(other):
            return None
        if _is_empty_value(value):
            return self.error or "This field is required"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        subj = str(value)
        target = self.value
        if self.case_sensitive is False:
            if not subj.lower().startswith(target.lower()):
                return self.error or f"Must start with {target}"
        else:
            if not subj.startswith(target):
                return self.error or f"Must start with {target}"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:  # noqa: ARG002
        if _is_empty_value(value):
            return None
        subj = str(value)
        target = self.value
        if self.case_sensitive is False:
            if not subj.lower().endswith(target.lower()):
                return self.error or f"Must end with {target}"
        else:
            if not subj.endswith(target):
                return self.error or f"Must end with {target}"
        return None


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

    def check(self, value: Any, values: dict[str, Any], path: str) -> str | None:
        try:
            return self.fn(value, values, path) or None
        except Exception:
            return "Validation failed"


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
