from __future__ import annotations

from io import BytesIO
import types
from datetime import datetime, timezone

import pulse as ps
import pytest

from pulse_mantine.form.validators import (
    AllowedFileTypes,
    EndsWith,
    HasLength,
    IsAfter,
    IsArrayNotEmpty,
    IsBefore,
    IsDate,
    IsEmail,
    IsInRange,
    IsInteger,
    IsISODate,
    IsJSONString,
    IsNotEmpty,
    IsNotEmptyHTML,
    IsNumber,
    IsULID,
    IsUrl,
    IsUUID,
    Matches,
    MatchesField,
    MaxFileSize,
    MaxItems,
    MinItems,
    RequiredUnless,
    RequiredWhen,
    ServerValidation,
    StartsWith,
)
from starlette.datastructures import Headers, UploadFile


class DummyUpload:
    def __init__(self, filename: str, content_type: str, size: int) -> None:
        self.filename = filename
        self.content_type = content_type
        self.size = size


def run(spec, value, values=None, path="field"):
    values = values or {"field": value}
    return spec.check(value, values, path)


def test_is_not_empty():
    spec = IsNotEmpty("err")
    assert run(spec, "") == "err"
    assert run(spec, " ") == "err"
    assert run(spec, []) == "err"
    assert run(spec, "x") is None


def test_is_email():
    spec = IsEmail("e")
    assert run(spec, "not-an-email") == "e"
    assert run(spec, "a@b.c") is None


def test_matches():
    spec = Matches(r"^[a-z]+$", error="e")
    assert run(spec, "ABC") == "e"
    assert run(spec, "abc") is None
    speci = Matches(r"^[a-z]+$", flags="i", error="e")
    assert run(speci, "ABC") is None


def test_is_in_range():
    spec = IsInRange(min=1, max=10, error="e")
    assert run(spec, 0) == "e"
    assert run(spec, 11) == "e"
    assert run(spec, 5) is None


def test_has_length():
    assert run(HasLength(min=2, error="e"), "a") == "e"
    assert run(HasLength(max=2, error="e"), "abc") == "e"
    assert run(HasLength(exact=2, error="e"), "ab") is None


def test_matches_field():
    values = {"a": "x", "b": "y"}
    spec = MatchesField("a", "e")
    assert spec.check(values["b"], values, "b") == "e"
    values2 = {"a": "x", "b": "x"}
    assert spec.check(values2["b"], values2, "b") is None


def test_is_json_string():
    spec = IsJSONString("e")
    assert run(spec, "not json") == "e"
    assert run(spec, '{"a":1}') is None


def test_is_not_empty_html():
    spec = IsNotEmptyHTML("e")
    assert run(spec, "<p>  </p>") == "e"
    assert run(spec, "<p>hi</p>") is None


def test_is_url():
    assert run(IsUrl(error="e"), "example.com") is None
    assert run(IsUrl(require_protocol=True, error="e"), "example.com") == "e"
    assert run(IsUrl(protocols=["https"], error="e"), "http://example.com") == "e"
    assert run(IsUrl(protocols=["http", "https"], error="e"), "https://x") is None


def test_is_uuid():
    assert run(IsUUID(error="e"), "not-uuid") == "e"
    assert (
        run(IsUUID(version=4, error="e"), "8c1d0b04-7f9b-4f75-9d3c-6b0b8ee7c7c1")
        is None
    )


def test_is_ulid():
    assert run(IsULID("e"), "not-ulid") == "e"
    assert run(IsULID("e"), "01HAF8ZJ2R9T5S8Q2YKD3B4N5M") is None


def test_is_number_and_integer():
    assert run(IsNumber("e"), "x") == "e"
    assert run(IsNumber("e"), "1.5") is None
    assert run(IsInteger("e"), "1.5") == "e"
    assert run(IsInteger("e"), "2") is None


def test_is_date_and_iso_date():
    assert run(IsDate("e"), "not-a-date") == "e"
    assert run(IsDate("e"), datetime.now(timezone.utc)) is None
    assert run(IsISODate(with_time=False, error="e"), "2024-01-01") is None
    assert run(IsISODate(with_time=True, error="e"), "2024-01-01T10:20:30Z") is None
    assert run(IsISODate(with_time=False, error="e"), "2024-01-01T10:20:30Z") == "e"


def test_is_before_after():
    values = {"start": "2024-01-01", "end": "2024-01-02"}
    assert (
        IsBefore("end", inclusive=True, error="e").check(
            values["start"], values, "start"
        )
        is None
    )
    assert (
        IsAfter("start", inclusive=True, error="e").check(values["end"], values, "end")
        is None
    )
    assert IsBefore("start", error="e").check(values["end"], values, "end") == "e"
    assert IsAfter("end", error="e").check(values["start"], values, "start") == "e"


def test_min_max_items_array_not_empty():
    assert run(MinItems(1, "e"), []) == "e"
    assert run(MinItems(1, "e"), [1]) is None
    assert run(MaxItems(1, "e"), [1, 2]) == "e"
    assert run(IsArrayNotEmpty("e"), [1]) is None


def test_allowed_file_types_and_max_file_size():
    f1 = UploadFile(
        file=BytesIO(b"dummy content"),
        filename="a.png",
        headers=Headers({"content-type": "image/png"}),
        size=1024,
    )
    f2 = UploadFile(
        file=BytesIO(b"dummy content"),
        filename="a.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
        size=10 * 1024 * 1024,
    )
    assert run(AllowedFileTypes(mime_types=["image/*"], error="e"), [f1]) is None
    assert run(AllowedFileTypes(extensions=["png"], error="e"), [f1]) is None
    assert run(AllowedFileTypes(extensions=["jpg"], error="e"), [f1]) == "e"
    assert run(MaxFileSize(5 * 1024 * 1024, "e"), [f2]) == "e"


def test_required_when_and_unless():
    vals = {"flag": True, "x": ""}
    assert (
        RequiredWhen("flag", truthy=True, error="e").check(vals["x"], vals, "x") == "e"
    )
    vals2 = {"flag": False, "x": ""}
    assert (
        RequiredUnless("flag", truthy=True, error="e").check(vals2["x"], vals2, "x")
        == "e"
    )


def test_starts_ends_with():
    assert run(StartsWith("AA", error="e"), "AABB") is None
    assert run(StartsWith("AA", case_sensitive=False, error="e"), "aabb") is None
    assert run(EndsWith("BB", error="e"), "AABB") is None
    assert run(EndsWith("BB", case_sensitive=False, error="e"), "aabb") is None
    assert run(StartsWith("AA", error="e"), "XXBB") == "e"
    assert run(EndsWith("BB", error="e"), "AAXX") == "e"


def test_server_validation():
    spec = ServerValidation(lambda v, vs, p: "err" if str(v) == "bad" else None)
    assert run(spec, "bad") == "err"
    assert run(spec, "ok") is None
