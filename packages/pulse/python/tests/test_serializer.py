import datetime as dt

import pytest
from pulse.serializer import deserialize, serialize


def test_primitives_roundtrip_v3():
	data = [1, "a", True, None, 3.5]
	payload = serialize(data)
	parsed = deserialize(payload)
	assert parsed == data


def test_handles_sets_v3():
	source = {1, 2, "three"}
	payload = serialize(source)
	parsed = deserialize(payload)

	assert isinstance(parsed, set)
	assert parsed == source


def test_nested_special_values_and_shared_refs_v3():
	when = dt.datetime(2024, 2, 2, tzinfo=dt.UTC)
	shared_set = {when}
	data = {"s": shared_set, "also": shared_set, "arr": [shared_set, when]}

	payload = serialize(data)
	parsed = deserialize(payload)

	assert isinstance(parsed["s"], set)
	items = list(parsed["s"])
	assert len(items) == 1
	assert isinstance(items[0], dt.datetime)

	assert parsed["also"] is parsed["s"]
	assert parsed["arr"][0] is parsed["s"]
	assert parsed["arr"][1] is items[0]


def test_cycles_with_special_types_v3():
	when = dt.datetime(2024, 3, 3, tzinfo=dt.UTC)
	root: dict[str, object] = {"when": when}
	root["self"] = root

	payload = serialize(root)
	parsed = deserialize(payload)

	assert parsed["self"] is parsed
	assert isinstance(parsed["when"], dt.datetime)
	assert parsed["when"].timestamp() == pytest.approx(when.timestamp(), rel=1e-9)


def test_multiple_special_types_v3():
	d1 = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
	d2 = dt.datetime(2030, 1, 1, tzinfo=dt.UTC)
	data = {
		"list": [{d1}, {"deep": [{d2, d1}]}],
		"single": d2,
	}

	payload = serialize(data)
	parsed = deserialize(payload)

	assert isinstance(parsed["list"][0], set)
	first_set_items = list(parsed["list"][0])
	assert all(isinstance(item, dt.datetime) for item in first_set_items)

	assert isinstance(parsed["list"][1]["deep"][0], set)
	deep_items = list(parsed["list"][1]["deep"][0])
	assert all(isinstance(item, dt.datetime) for item in deep_items)
	assert isinstance(parsed["single"], dt.datetime)


def test_arrays_and_objects_v3():
	data = {"a": 1, "b": [2, 3, {"c": "x"}]}
	payload = serialize(data)
	parsed = deserialize(payload)
	assert parsed == data


def test_preserves_cycles_and_shared_refs_v3():
	shared = {"v": 42}
	root: dict[str, object] = {"left": {"shared": shared}, "right": {"shared": shared}}
	root["self"] = root

	payload = serialize(root)
	parsed = deserialize(payload)

	assert parsed["left"]["shared"] is parsed["right"]["shared"]
	assert parsed["self"] is parsed
	assert parsed["left"]["shared"]["v"] == 42


def test_dates_and_shared_references_v3():
	when = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
	data = {"when": when, "same": when}
	payload = serialize(data)
	parsed = deserialize(payload)

	assert isinstance(parsed["when"], dt.datetime)
	assert parsed["when"].timestamp() == pytest.approx(when.timestamp(), rel=1e-9)
	assert parsed["when"] is parsed["same"]


def test_date_roundtrip_v4():
	day = dt.date(2024, 1, 2)
	data = {"day": day}
	payload = serialize(data)
	parsed = deserialize(payload)

	assert isinstance(parsed["day"], dt.date)
	assert parsed["day"] == day


def test_unsupported_values_raise_v3():
	with pytest.raises(TypeError):
		serialize({"x": lambda: None})


class TestNaNAndInfinity:
	"""Test handling of NaN and Infinity during serialization."""

	def test_nan_converted_to_none(self):
		"""NaN floats should be converted to None during serialization."""
		data = {"value": float("nan")}
		payload = serialize(data)
		parsed = deserialize(payload)
		assert parsed == {"value": None}

	def test_nan_in_nested_structure(self):
		"""NaN in nested dicts/lists should be converted to None."""
		data = {"nested": {"value": float("nan")}, "list": [1.0, float("nan"), 3.0]}
		payload = serialize(data)
		parsed = deserialize(payload)
		assert parsed == {"nested": {"value": None}, "list": [1.0, None, 3.0]}

	def test_infinity_raises(self):
		"""Positive infinity should raise ValueError."""
		with pytest.raises(ValueError, match="Infinity is not valid JSON"):
			serialize({"value": float("inf")})

	def test_negative_infinity_raises(self):
		"""Negative infinity should raise ValueError."""
		with pytest.raises(ValueError, match="Infinity is not valid JSON"):
			serialize({"value": float("-inf")})

	def test_valid_floats_pass_through(self):
		"""Regular floats should serialize normally."""
		data = {"pi": 3.14159, "values": [1.0, 2.5, -0.5]}
		payload = serialize(data)
		parsed = deserialize(payload)
		assert parsed == data
