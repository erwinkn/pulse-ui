import datetime
from typing import Any, Callable, Dict

import pytest

from pulse.serializer_v2 import Extension, serialize, deserialize


class DateExt(Extension[datetime.datetime]):
    @staticmethod
    def check(value: Any) -> bool:
        return isinstance(value, datetime.datetime)

    @staticmethod
    def encode(value, encode) -> dict[str, Any]:
        # store a small tagged structure using child indices
        return {
            "t": encode("date"),
            "ts": encode(int(value.timestamp() * 1000)),
        }

    @staticmethod
    def decode(entry, decode) -> datetime.datetime:
        t = decode(entry["t"])  # "date"
        if t != "date":
            raise ValueError("invalid date payload")
        ts = decode(entry["ts"])  # milliseconds
        return datetime.datetime.fromtimestamp(ts / 1000.0, tz=datetime.timezone.utc)


def test_primitives_v2():
    exts: list[Any] = []
    ser = serialize([1, "a", True, 3.5], exts)
    out = deserialize(ser, exts)
    assert out == [1, "a", True, 3.5]


def test_objects_and_arrays_v2():
    exts: list[Any] = []
    data = {"a": 1, "b": [2, 3, {"c": "x"}]}
    ser = serialize(data, exts)
    out = deserialize(ser, exts)
    assert out == data


def test_cycles_and_shared_refs_v2():
    exts: list[Any] = []
    shared: Dict[str, Any] = {"v": 42}
    root: Dict[str, Any] = {"left": {"shared": shared}, "right": {"shared": shared}}
    root["self"] = root

    ser = serialize(root, exts)
    out = deserialize(ser, exts)

    assert out["left"]["shared"] is out["right"]["shared"]
    assert out["self"] is out
    assert out["left"]["shared"]["v"] == 42


def test_date_extension_v2():
    d = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    exts = [DateExt]
    data = {"when": d, "same": d}
    ser = serialize(data, exts)
    out = deserialize(ser, exts)

    assert isinstance(out["when"], datetime.datetime)
    assert out["when"].timestamp() == pytest.approx(d.timestamp(), rel=1e-6)
    assert out["when"] is out["same"]


def test_multiple_extensions_v2():
    class SetExt:
        @staticmethod
        def check(value: Any) -> bool:
            return isinstance(value, set)

        @staticmethod
        def encode(value: set, encode) -> Dict[str, Any]:
            # store tag and items as indices
            return {"t": encode("set"), "items": encode(list(value))}

        @staticmethod
        def decode(entry: Dict[str, Any], decode) -> set:
            t = decode(entry["t"])  # "set"
            if t != "set":
                raise ValueError("invalid set payload")
            items = decode(entry["items"])  # list already decoded
            return set(items)

    d1 = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    d2 = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
    exts = [DateExt, SetExt]
    data = {"list": [set([d1]), {"deep": [set([d2, d1])]}], "single": d2}
    ser = serialize(data, exts)
    out = deserialize(ser, exts)
    print(out)

    assert isinstance(out["list"][0], set)
    first = list(out["list"][0])
    assert isinstance(first[0], datetime.datetime)
    deep = list(out["list"][1]["deep"][0])
    assert isinstance(deep[0], datetime.datetime)
    assert isinstance(deep[1], datetime.datetime)
    assert isinstance(out["single"], datetime.datetime)
