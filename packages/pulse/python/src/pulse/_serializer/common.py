import datetime as dt
import json
import math
import re
from typing import Any, Literal, cast

MAX_SAFE_INTEGER = 2**53 - 1
MAX_PROJECTION_STEPS = 64
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")

type PathSegment = str | int | tuple[str, int]
type Operation = Literal["serialize", "deserialize"]


# Returns (terminal, sort_key, js_key, python_key). Set members must stay
# distinct under BOTH runtimes' equality: JS SameValueZero (js_key) and Python
# __eq__/__hash__ (python_key, where True == 1 == 1.0 collapse). A payload
# whose members collide under either relation would silently lose data in one
# runtime, so both keys must be injective over the set.
def describe_set_value(
	value: object,
	path: list[PathSegment],
	operation: Operation,
) -> tuple[object, tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]:
	value_type = type(value)
	if value is None or (value_type is float and math.isnan(cast(float, value))):
		return None, (0, ""), ("null",), ("null",)
	if value_type is bool:
		number = int(cast(bool, value))
		return value, (1, number), ("bool", value), ("bool-number", number)
	if value_type is int:
		number = cast(int, value)
		validate_safe_integer(number, path, operation)
		return (
			value,
			(2, number),
			("number", float(number)),
			("bool-number", float(number)),
		)
	if value_type is float:
		number = cast(float, value)
		validate_finite(number, path, operation)
		number = 0.0 if number == 0 else number
		return number, (2, number), ("number", number), ("bool-number", number)
	if value_type is str:
		text = cast(str, value)
		if not text.isascii():
			validate_portable_string(text, path, operation)
		return value, (3, text), ("string", text), ("string", text)
	if value_type is dt.date or value_type is dt.datetime:
		wire = temporal_to_wire(value, path)
		return (
			value,
			(4, wire),
			("datetime-object", id(value)),
			("datetime", wire),
		)
	if operation == "serialize":
		raise TypeError(
			f"Cannot serialize {format_path(path)}: set values must project to "
			+ "null, booleans, strings, finite numbers, dates, or datetimes."
		)
	raise ValueError(
		f"Cannot deserialize {format_path(path)}: set values must be "
		+ "null, booleans, strings, finite numbers, or datetimes."
	)


def validate_safe_integer(
	value: int, path: list[PathSegment], operation: Operation
) -> None:
	if abs(value) > MAX_SAFE_INTEGER:
		raise ValueError(
			f"Cannot {operation} {format_path(path)}: integer {value} is outside the "
			+ "JavaScript safe integer range."
		)


def validate_finite(
	value: float, path: list[PathSegment], operation: Operation
) -> None:
	if not math.isfinite(value):
		raise ValueError(
			f"Cannot {operation} {format_path(path)}: numbers must be finite."
		)


def validate_portable_string(
	value: str, path: list[PathSegment], operation: Operation
) -> None:
	if value.isascii():
		return
	if SURROGATE_RE.search(value) is not None:
		raise ValueError(
			f"Cannot {operation} {format_path(path)}: surrogate code points are not portable JSON."
		)


def temporal_to_wire(value: object, path: list[PathSegment]) -> str:
	if type(value) is dt.date:
		value = dt.datetime.combine(value, dt.time(), dt.UTC)
	return datetime_to_wire(cast(dt.datetime, value), path)


def datetime_to_wire(value: dt.datetime, path: list[PathSegment]) -> str:
	if dt.datetime.utcoffset(value) is None:
		raise ValueError(
			f"Cannot serialize {format_path(path)}: datetime must be timezone-aware."
		)
	try:
		normalized = dt.datetime.astimezone(value, dt.UTC)
	except (OverflowError, ValueError) as exc:
		raise ValueError(
			f"Cannot serialize {format_path(path)}: datetime year must be within 0001-9999."
		) from exc
	if normalized.microsecond % 1000 != 0:
		raise ValueError(
			f"Cannot serialize {format_path(path)}: datetime must use millisecond precision."
		)
	return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def datetime_from_wire(value: str, path: list[PathSegment]) -> dt.datetime:
	if not DATETIME_RE.fullmatch(value):
		raise ValueError(f"Invalid datetime literal at {format_path(path)}: {value!r}")
	try:
		return dt.datetime.fromisoformat(value[:-1] + "+00:00")
	except ValueError as exc:
		raise ValueError(
			f"Invalid datetime literal at {format_path(path)}: {value!r}"
		) from exc


def decode_identity_id(value: object, path: list[PathSegment]) -> int:
	if type(value) not in {int, float}:
		raise ValueError(f"Invalid identity id at {format_path(path)}: {value!r}")
	if type(value) is float and (not math.isfinite(value) or not value.is_integer()):
		raise ValueError(f"Invalid identity id at {format_path(path)}: {value!r}")
	identity = int(cast(int | float, value))
	validate_safe_integer(identity, path, "deserialize")
	if identity < 0:
		raise ValueError(f"Invalid identity id at {format_path(path)}: {value!r}")
	return identity


# JS objects (and therefore JSON.parse in the browser) iterate array-index
# keys first, in ascending numeric order. Python must emulate that or the two
# runtimes materialize the same record with different key order.
def js_object_key_order(keys: list[str]) -> list[str]:
	indices: list[tuple[int, str]] = []
	others: list[str] = []
	for key in keys:
		if is_js_array_index(key):
			indices.append((int(key), key))
		else:
			others.append(key)
	indices.sort(key=lambda item: item[0])
	return [key for _, key in indices] + others


def is_js_array_index(key: str) -> bool:
	return key == "0" or bool(
		key
		and key.isascii()
		and "1" <= key[0] <= "9"
		and key.isdigit()
		and not key.startswith("0")
		and (len(key) < 10 or (len(key) == 10 and key <= "4294967294"))
	)


def format_child_path(path: list[PathSegment], segment: PathSegment) -> str:
	path.append(segment)
	formatted = format_path(path)
	path.pop()
	return formatted


def format_path(path: list[PathSegment]) -> str:
	result = "$"
	for segment in path:
		if isinstance(segment, int):
			result += f"[{segment}]"
		elif isinstance(segment, tuple):
			result += f"<set:{segment[1]}>"
		elif segment.isidentifier():
			result += f".{segment}"
		else:
			result += f"[{json.dumps(segment)}]"
	return result
