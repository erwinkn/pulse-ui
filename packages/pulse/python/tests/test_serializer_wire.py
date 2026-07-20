import datetime as dt
import json
import math
from typing import Any, cast, override

import pytest
from pulse.serializer import WireMap, deserialize, serialize


def wire_boundary(value: object):
	return json.loads(json.dumps(serialize(value)))


def wire_roundtrip(value: object) -> Any:
	return deserialize(wire_boundary(value))


def compact_size(value: object) -> int:
	return len(json.dumps(value, separators=(",", ":")))


def test_returns_versioned_list_envelope():
	payload = serialize({"ok": True})

	assert payload == [5, {"ok": True}]
	assert isinstance(payload, list)


def test_plain_json_values_stay_plain():
	data = {"a": 1, "b": [True, None, "x"], "c": {"nested": 3.5}}

	assert serialize(data) == [5, data]
	assert wire_roundtrip(data) == data


def test_marker_shaped_source_arrays_are_escaped():
	data = ["$", {"nested": ["$", 1]}, 2]

	assert serialize(data) == [
		5,
		["$", "a", ["$", {"nested": ["$", "a", ["$", 1]]}, 2]],
	]
	assert wire_roundtrip(data) == data


def test_unsupported_values_do_not_run_source_equality():
	class EqualsDollar:
		equality_calls: int = 0

		@override
		def __eq__(self, other: object) -> bool:
			type(self).equality_calls += 1
			return other == "$"

	value = EqualsDollar()

	with pytest.raises(TypeError, match="unsupported value of type EqualsDollar"):
		serialize([value])
	assert EqualsDollar.equality_calls == 0


def test_scalar_subclasses_require_adapters_before_protocol_decisions():
	class Dollar(str):
		equality_calls: int = 0

		@override
		def __eq__(self, other: object) -> bool:
			type(self).equality_calls += 1
			return False

	value = Dollar("$")
	with pytest.raises(TypeError, match="unsupported value of type Dollar"):
		serialize([value])
	assert Dollar.equality_calls == 0


def test_date_and_datetime_use_one_timestamp_marker():
	value = {
		"day": dt.date(2024, 1, 2),
		"when": dt.datetime(2024, 1, 2, 3, 4, 5, 6000, tzinfo=dt.UTC),
	}

	assert serialize(value) == [
		5,
		{
			"day": ["$", "t", "2024-01-02T00:00:00.000Z"],
			"when": ["$", "t", "2024-01-02T03:04:05.006Z"],
		},
	]
	parsed = wire_roundtrip(value)
	assert parsed["day"] == dt.datetime(2024, 1, 2, tzinfo=dt.UTC)
	assert parsed["when"] == value["when"]


def test_datetime_normalizes_to_utc():
	value = dt.datetime(
		2024,
		1,
		2,
		3,
		4,
		5,
		6000,
		tzinfo=dt.timezone(dt.timedelta(hours=2)),
	)

	assert serialize(value) == [5, ["$", "t", "2024-01-02T01:04:05.006Z"]]


def test_wiremap_round_trips_and_reencodes_as_map():
	value = WireMap(
		[
			("second", 2),
			("first", dt.date(2024, 1, 2)),
		]
	)
	wire = [
		5,
		[
			"$",
			"m",
			[
				["second", 2],
				["first", ["$", "t", "2024-01-02T00:00:00.000Z"]],
			],
		],
	]

	assert serialize(value) == wire

	parsed = deserialize(wire_boundary(value))
	assert isinstance(parsed, WireMap)
	assert list(parsed.items()) == [
		("second", 2),
		("first", dt.datetime(2024, 1, 2, tzinfo=dt.UTC)),
	]
	assert serialize(parsed) == wire


def test_plain_dict_remains_a_record_after_json_boundary():
	value = {"__proto__": 0, "nested": {"ok": True}}

	assert serialize(value) == [5, value]
	assert wire_roundtrip(value) == value


def test_references_only_appear_for_repeated_objects():
	unique = {"left": {"x": 1}, "right": {"x": 1}}
	shared_child = {"x": 1}
	repeated = {"left": shared_child, "right": shared_child}

	assert serialize(unique) == [5, {"left": {"x": 1}, "right": {"x": 1}}]
	assert serialize(repeated) == [5, {"left": {"x": 1}, "right": ["$", 1]}]
	assert compact_size(serialize(unique)) == len(
		'[5,{"left":{"x":1},"right":{"x":1}}]'
	)
	assert compact_size(serialize(repeated)) == len(
		'[5,{"left":{"x":1},"right":["$",1]}]'
	)


def test_record_key_order_controls_implicit_identity_ids():
	shared: list[object] = []
	value = {"2": shared, "1": shared}

	wire = [5, {"1": [], "2": ["$", 1]}]
	assert serialize(value) == wire

	parsed = cast(dict[str, Any], deserialize(json.loads(json.dumps(wire))))
	assert parsed["1"] is parsed["2"]


def test_record_key_order_does_not_treat_unicode_digits_as_array_indices():
	shared: list[object] = []
	value = {"1٢": shared, "1": shared}

	assert serialize(value) == [5, {"1": [], "1٢": ["$", 1]}]


def test_cycles_round_trip_through_implicit_references():
	root: dict[str, object] = {}
	root["self"] = root
	root["items"] = [root]

	wire = [5, {"self": ["$", 0], "items": [["$", 0]]}]
	assert serialize(root) == wire

	parsed = cast(dict[str, Any], deserialize(wire_boundary(root)))
	assert parsed["self"] is parsed
	assert parsed["items"][0] is parsed


def test_repeated_datetime_identity_round_trips():
	when = dt.datetime(2024, 1, 2, 3, 4, 5, 6000, tzinfo=dt.UTC)
	value = {"first": when, "second": when}

	wire = [
		5,
		{
			"first": ["$", "t", "2024-01-02T03:04:05.006Z"],
			"second": ["$", 1],
		},
	]
	assert serialize(value) == wire

	parsed = cast(dict[str, Any], deserialize(wire_boundary(value)))
	assert parsed["first"] is parsed["second"]
	assert parsed["first"] == when


def test_set_uses_deterministic_canonical_order():
	value = {
		dt.datetime(2024, 1, 2, 3, 4, 5, 6000, tzinfo=dt.UTC),
		dt.date(2024, 1, 2),
		"😀",
		"\ue000",
		"b",
		10,
		2,
		1.5,
		-10,
		1,
		False,
		None,
	}

	wire = [
		5,
		[
			"$",
			"s",
			[
				None,
				False,
				-10,
				1,
				1.5,
				2,
				10,
				"b",
				"\ue000",
				"😀",
				["$", "t", "2024-01-02T00:00:00.000Z"],
				["$", "t", "2024-01-02T03:04:05.006Z"],
			],
		],
	]

	assert serialize(value) == wire

	parsed = wire_roundtrip(value)
	assert dt.datetime(2024, 1, 2, tzinfo=dt.UTC) in parsed
	assert dt.date(2024, 1, 2) not in parsed
	assert parsed - {dt.datetime(2024, 1, 2, tzinfo=dt.UTC)} == value - {
		dt.date(2024, 1, 2)
	}
	assert serialize(parsed) == wire


def test_set_rejects_container_entries_on_encode_and_decode():
	with pytest.raises(TypeError, match="set values must project"):
		serialize({(1, 2)})

	with pytest.raises(ValueError, match="set values must be"):
		deserialize([5, ["$", "s", [[1, 2]]]])


def test_complex_graph_round_trips_across_json_boundary():
	when = dt.datetime(2024, 1, 2, 3, 4, 5, 6000, tzinfo=dt.UTC)
	shared_map = WireMap([("when", when), ("day", dt.date(2024, 1, 2))])
	root: dict[str, object] = {"map": shared_map, "again": shared_map, "values": {when}}
	root["self"] = root

	parsed = wire_roundtrip(root)

	assert parsed["self"] is parsed
	assert parsed["map"] is parsed["again"]
	assert isinstance(parsed["map"], WireMap)
	assert parsed["map"]["when"] is next(iter(parsed["values"]))
	assert serialize(parsed) == serialize(root)


@pytest.mark.parametrize("value", [2**53, -(2**53), float("inf"), float("-inf")])
def test_rejects_invalid_numeric_values_on_encode(value: float | int):
	with pytest.raises(ValueError, match="Cannot serialize"):
		serialize({"value": value})


def test_normalizes_negative_zero_to_positive_zero():
	root = serialize(-0.0)
	assert root == [5, 0.0]
	assert math.copysign(1.0, cast(float, root[1])) > 0

	wire = serialize({-0.0})

	assert wire == [5, ["$", "s", [0.0]]]
	encoded_zero = cast(list[Any], cast(list[Any], wire[1])[2])[0]
	assert math.copysign(1.0, cast(float, encoded_zero)) > 0
	assert math.copysign(1.0, next(iter(cast(set[float], deserialize(wire))))) > 0


def test_big_floats_round_trip_through_the_float_marker():
	edge = float(2**53)
	wire = serialize({"big": 1e300, "edge": edge, "set": {1e300}})
	assert wire == [
		5,
		{
			"big": ["$", "f", 1e300],
			"edge": ["$", "f", edge],
			"set": ["$", "s", [["$", "f", 1e300]]],
		},
	]
	assert deserialize(json.loads(json.dumps(wire))) == {
		"big": 1e300,
		"edge": edge,
		"set": {1e300},
	}
	# JS encoders emit large integral doubles as integer literals.
	assert deserialize([5, ["$", "f", 2**53]]) == edge


@pytest.mark.parametrize(
	"marker",
	[
		["$", "f", 5],
		["$", "f", 2**53 - 1],
		["$", "f", "1e300"],
		["$", "f", float("inf")],
		["$", "f", float("nan")],
		["$", "f", 1e300, None],
		["$", "f"],
	],
)
def test_rejects_malformed_big_float_markers(marker: list[object]):
	with pytest.raises(ValueError, match="big-float marker"):
		deserialize([5, marker])


@pytest.mark.parametrize(
	"wire",
	[
		[5, 2**53],
		[5, -(2**53)],
		[5, float(2**53)],
		[5, 1e300],
		[5, float("inf")],
		[5, float("nan")],
	],
)
def test_rejects_invalid_numeric_values_on_decode(wire: list[object]):
	with pytest.raises(ValueError, match="Cannot deserialize"):
		deserialize(wire)


def test_nan_normalizes_to_null():
	assert serialize({"value": float("nan")}) == [5, {"value": None}]
	with pytest.raises(ValueError, match="duplicate set value"):
		serialize({None, float("nan")})


def test_rejects_nested_unsupported_values_with_paths():
	with pytest.raises(
		TypeError,
		match=r"Cannot serialize \$.items\[1\]: unsupported value of type function",
	):
		serialize({"items": [1, lambda: None]})


def test_rejects_naive_and_submillisecond_datetimes():
	with pytest.raises(ValueError, match="timezone-aware"):
		serialize(dt.datetime(2024, 1, 2, 3, 4, 5))

	with pytest.raises(ValueError, match="millisecond precision"):
		serialize(dt.datetime(2024, 1, 2, 3, 4, 5, 1, tzinfo=dt.UTC))

	microsecond_offset = dt.timezone(dt.timedelta(microseconds=1))
	with pytest.raises(ValueError, match="millisecond precision"):
		serialize(dt.datetime(2024, 1, 2, tzinfo=microsecond_offset))


def test_rejects_non_string_record_and_map_keys():
	with pytest.raises(TypeError, match="record keys must be strings"):
		serialize({1: "x"})

	bad_map = WireMap()
	bad_map[1] = "x"  # pyright: ignore[reportArgumentType]
	with pytest.raises(TypeError, match="map keys must be strings"):
		serialize(bad_map)


def test_decode_map_markers_validate_shape_and_duplicate_keys():
	with pytest.raises(ValueError, match="Malformed map entry"):
		deserialize([5, ["$", "m", [["ok"]]]])

	with pytest.raises(ValueError, match="Duplicate map key"):
		deserialize([5, ["$", "m", [["a", 1], ["a", 2]]]])


def test_decode_set_rejects_python_equality_collisions_and_equal_dates():
	with pytest.raises(ValueError, match="not canonically ordered"):
		deserialize([5, ["$", "s", [2, 1]]])

	with pytest.raises(ValueError, match="collides under Python equality"):
		deserialize([5, ["$", "s", [True, 1]]])

	with pytest.raises(ValueError, match="collides under Python equality"):
		deserialize(
			[
				5,
				[
					"$",
					"s",
					[
						["$", "t", "2024-01-02T00:00:00.000Z"],
						["$", "t", "2024-01-02T00:00:00.000Z"],
					],
				],
			]
		)


def test_decode_rejects_unknown_tags_and_malformed_markers():
	empty_escaped_array: object = json.loads('[5,["$","a",[]]]')

	with pytest.raises(ValueError, match="Unknown wire marker tag"):
		deserialize([5, ["$", "x", 1]])

	with pytest.raises(ValueError, match="Dangling reference"):
		deserialize([5, ["$", 1]])

	with pytest.raises(ValueError, match="payload must begin"):
		deserialize(empty_escaped_array)

	with pytest.raises(ValueError, match="payload must begin"):
		deserialize([5, ["$", "a", [1]]])


def test_decode_accepts_integral_json_number_identity_ids():
	wire = [5, {"self": ["$", 0.0]}]
	parsed = cast(dict[str, Any], deserialize(json.loads(json.dumps(wire))))

	assert parsed["self"] is parsed


def test_deserialize_accepts_untyped_boundary_input():
	payload: object = json.loads('[5,{"value":1}]')

	assert deserialize(payload) == {"value": 1}


def test_decode_normalizes_negative_zero_values_and_identity_ids():
	value = cast(float, deserialize([5, -0.0]))
	assert value == 0
	assert math.copysign(1.0, value) > 0

	root = cast(list[Any], deserialize([5, [["$", -0.0]]]))
	assert root[0] is root


def test_rejects_surrogate_code_points_on_encode_and_decode():
	with pytest.raises(ValueError, match="surrogate code points"):
		serialize({"value": "\ud800"})

	with pytest.raises(ValueError, match="surrogate code points"):
		deserialize([5, "\ud800"])


def test_decode_rejects_dangling_and_forward_references():
	forward_reference: object = json.loads('[5,{"first":["$",2],"second":{}}]')

	with pytest.raises(ValueError, match="Dangling reference"):
		deserialize([5, ["$", 0]])

	with pytest.raises(ValueError, match="Dangling reference"):
		deserialize(forward_reference)


def test_decode_rejects_invalid_date_and_datetime_literals():
	with pytest.raises(ValueError, match="Invalid datetime literal"):
		deserialize([5, ["$", "t", "2024-01-02T03:04:05Z"]])
