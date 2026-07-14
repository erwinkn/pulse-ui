from __future__ import annotations

import datetime as dt
import json
import random
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from pulse.marker_serializer import Serialized, WireMap, deserialize, serialize

ROOT = Path(__file__).resolve().parents[4]
JS_HARNESS = ROOT / "packages/pulse/js/test/marker-serializer-interop.ts"

Descriptor = dict[str, Any]


def materialize(
	descriptor: Descriptor,
	objects: dict[str, object] | None = None,
) -> object:
	if objects is None:
		objects = {}

	kind = descriptor["t"]
	if kind == "null":
		return None
	if kind in {"bool", "number", "string"}:
		return descriptor["value"]
	if kind == "date":
		result_date = dt.date.fromisoformat(descriptor["value"])
		if identifier := descriptor.get("id"):
			objects[identifier] = result_date
		return result_date
	if kind == "datetime":
		result_datetime = dt.datetime.fromisoformat(
			descriptor["value"].replace("Z", "+00:00")
		)
		if identifier := descriptor.get("id"):
			objects[identifier] = result_datetime
		return result_datetime
	if kind == "ref":
		return objects[descriptor["id"]]

	identifier = descriptor.get("id")
	if kind == "array":
		result: list[object] = []
		if identifier is not None:
			objects[identifier] = result
		result.extend(materialize(item, objects) for item in descriptor["items"])
		return result
	if kind == "record":
		result_dict: dict[str, object] = {}
		if identifier is not None:
			objects[identifier] = result_dict
		for key, value in descriptor["entries"]:
			result_dict[key] = materialize(value, objects)
		return result_dict
	if kind == "map":
		result_map = WireMap()
		if identifier is not None:
			objects[identifier] = result_map
		for key, value in descriptor["entries"]:
			result_map[key] = materialize(value, objects)
		return result_map
	if kind == "set":
		result_set: set[object] = set()
		if identifier is not None:
			objects[identifier] = result_set
		for item in descriptor["items"]:
			result_set.add(materialize(item, objects))
		return result_set
	raise AssertionError(f"Unknown descriptor kind: {kind}")


def snapshot(value: object, seen: dict[int, int] | None = None) -> object:
	if seen is None:
		seen = {}
	if value is None:
		return ["null"]
	if isinstance(value, bool):
		return ["bool", value]
	if isinstance(value, int | float):
		return ["number", value]
	if isinstance(value, str):
		return ["string", value]
	if isinstance(value, dt.datetime):
		return [
			"datetime",
			value.astimezone(dt.UTC)
			.isoformat(timespec="milliseconds")
			.replace("+00:00", "Z"),
		]
	if isinstance(value, dt.date):
		return ["date", value.isoformat()]

	identity = id(value)
	if identity in seen:
		return ["ref", seen[identity]]
	node_id = len(seen)
	seen[identity] = node_id

	if isinstance(value, list):
		value = cast(list[object], value)
		return ["array", node_id, [snapshot(item, seen) for item in value]]
	if isinstance(value, WireMap):
		value = cast(dict[str, object], value)
		return [
			"map",
			node_id,
			[[key, snapshot(item, seen)] for key, item in value.items()],
		]
	if isinstance(value, set):
		value = cast(set[object], value)
		items = [snapshot(item, seen) for item in value]
		items.sort(key=lambda item: json.dumps(item, separators=(",", ":")))
		return ["set", node_id, items]
	if isinstance(value, dict):
		value = cast(dict[str, object], value)
		return [
			"record",
			node_id,
			[[key, snapshot(value[key], seen)] for key in sorted(value)],
		]
	raise AssertionError(f"Unsupported snapshot value: {type(value)!r}")


def run_javascript(request: dict[str, object]) -> object:
	completed = subprocess.run(
		["bun", str(JS_HARNESS)],
		cwd=ROOT,
		input=json.dumps(request),
		text=True,
		capture_output=True,
		check=True,
	)
	return cast(object, json.loads(completed.stdout))


def fixed_cases() -> list[Descriptor]:
	return [
		{"t": "null"},
		{"t": "bool", "value": True},
		{"t": "number", "value": 42},
		{"t": "string", "value": "text"},
		{"t": "date", "value": "0001-01-02"},
		{"t": "datetime", "value": "2024-01-02T03:04:05.006Z"},
		{
			"t": "array",
			"items": [
				{"t": "string", "value": "$"},
				{"t": "string", "value": "m"},
			],
		},
		{
			"t": "record",
			"entries": [
				["__proto__", {"t": "number", "value": 0}],
				["2", {"t": "string", "value": "two"}],
				["1", {"t": "string", "value": "one"}],
			],
		},
		{
			"t": "record",
			"entries": [
				[
					"2",
					{
						"t": "array",
						"id": "numeric-key-shared",
						"items": [],
					},
				],
				["1", {"t": "ref", "id": "numeric-key-shared"}],
			],
		},
		{
			"t": "record",
			"entries": [
				[
					"values",
					{
						"t": "set",
						"items": [
							{
								"t": "date",
								"id": "late",
								"value": "2025-01-01",
							},
							{
								"t": "date",
								"id": "early",
								"value": "2024-01-01",
							},
						],
					},
				],
				["early", {"t": "ref", "id": "early"}],
				["late", {"t": "ref", "id": "late"}],
			],
		},
		{
			"t": "map",
			"entries": [
				["2", {"t": "date", "value": "2024-01-01"}],
				["1", {"t": "string", "value": "one"}],
			],
		},
		{
			"t": "set",
			"items": [
				{"t": "string", "value": "b"},
				{"t": "string", "value": "a"},
				{"t": "date", "value": "2024-01-01"},
			],
		},
		{
			"t": "set",
			"items": [
				{"t": "datetime", "value": "2024-01-01T00:00:00.000Z"},
				{"t": "string", "value": "😀"},
				{"t": "string", "value": "\ue000"},
				{"t": "number", "value": 2},
				{"t": "number", "value": 10},
				{"t": "number", "value": -10},
				{"t": "number", "value": 1.5},
				{"t": "bool", "value": False},
				{"t": "null"},
			],
		},
		{
			"t": "record",
			"id": "root",
			"entries": [
				[
					"shared",
					{
						"t": "array",
						"id": "shared",
						"items": [{"t": "number", "value": 1}],
					},
				],
				["again", {"t": "ref", "id": "shared"}],
				["self", {"t": "ref", "id": "root"}],
			],
		},
	]


def random_cases(count: int, seed: int = 20260714) -> list[Descriptor]:
	rng = random.Random(seed)

	def leaf() -> Descriptor:
		kind = rng.randrange(6)
		if kind == 0:
			return {"t": "null"}
		if kind == 1:
			return {"t": "bool", "value": bool(rng.randrange(2))}
		if kind == 2:
			return {"t": "number", "value": rng.randrange(-10_000, 10_001)}
		if kind == 3:
			return {"t": "string", "value": f"value-{rng.randrange(20)}"}
		if kind == 4:
			return {"t": "date", "value": f"{rng.randrange(1, 10_000):04d}-01-01"}
		return {
			"t": "datetime",
			"value": f"{rng.randrange(1, 10_000):04d}-01-01T00:00:00.000Z",
		}

	def build(depth: int) -> Descriptor:
		if depth == 0 or rng.random() < 0.35:
			return leaf()
		kind = rng.randrange(4)
		size = rng.randrange(4)
		if kind == 0:
			return {"t": "array", "items": [build(depth - 1) for _ in range(size)]}
		if kind == 1:
			return {
				"t": "record",
				"entries": [[str(index), build(depth - 1)] for index in range(size)],
			}
		if kind == 2:
			return {
				"t": "map",
				"entries": [
					[f"key-{index}", build(depth - 1)] for index in range(size)
				],
			}
		return {
			"t": "set",
			"items": [
				{"t": "string", "value": f"set-{index}"} for index in range(size)
			],
		}

	return [build(4) for _ in range(count)]


def malformed_wires() -> list[object]:
	return [
		[4, None],
		[5, ["$"]],
		[5, ["$", "unknown"]],
		[5, ["$", "a", [], "extra"]],
		[5, ["$", "a", []]],
		[5, ["$", "a", [1]]],
		[5, ["$", "d", "2024-02-30"]],
		[5, ["$", "d", "2024-01-02\n"]],
		[5, ["$", "t", "2024-01-01T00:00:00Z"]],
		[5, ["$", "m", "not-entries"]],
		[5, ["$", "m", [["key", 1], ["key", 2]]]],
		[5, ["$", "s", [[]]]],
		[5, ["$", "s", [True, 1]]],
		[5, ["$", "s", [2, 1]]],
		[5, "\ud800"],
		[5, ["$", "i", 0, []]],
		[5, ["$", "r"]],
		[5, ["$", "r", True]],
		[5, ["$", "r", 0.5]],
		[5, ["$", "r", -1]],
		[5, ["$", "r", 0]],
		[5, [["$", "r", 1], {}]],
		[5, [1, ["$", "r", 1]]],
	]


def test_javascript_to_python_marker_interop():
	cases = fixed_cases() + random_cases(1_000)
	expected = [snapshot(materialize(case)) for case in cases]
	encoded = cast(
		list[dict[str, object]],
		run_javascript({"op": "encode", "cases": cases}),
	)

	assert [result["snapshot"] for result in encoded] == expected
	assert [result["decodedSnapshot"] for result in encoded] == expected

	python_wires = [
		json.loads(json.dumps(serialize(materialize(case)))) for case in cases
	]
	assert [result["wire"] for result in encoded] == python_wires

	javascript_wires = [result["wire"] for result in encoded]
	python_values = [deserialize(cast(Serialized, wire)) for wire in javascript_wires]
	assert [snapshot(value) for value in python_values] == expected

	python_roundtrip_wires = [
		json.loads(json.dumps(serialize(value))) for value in python_values
	]
	assert python_roundtrip_wires == javascript_wires
	roundtripped = cast(
		list[dict[str, object]],
		run_javascript({"op": "transcode", "wires": javascript_wires}),
	)
	assert [result["snapshot"] for result in roundtripped] == expected
	assert [result["wire"] for result in roundtripped] == javascript_wires


def test_python_to_javascript_marker_interop():
	cases = fixed_cases() + random_cases(1_000)
	values = [materialize(case) for case in cases]
	expected = [snapshot(value) for value in values]
	wires = [json.loads(json.dumps(serialize(value))) for value in values]

	transcoded = cast(
		list[dict[str, object]],
		run_javascript({"op": "transcode", "wires": wires}),
	)
	assert [result["snapshot"] for result in transcoded] == expected
	assert [result["wire"] for result in transcoded] == wires

	python_roundtrips = [
		deserialize(cast(Serialized, result["wire"])) for result in transcoded
	]
	assert [snapshot(value) for value in python_roundtrips] == expected


def test_shared_date_and_datetime_identity_is_preserved_in_both_runtimes():
	case: Descriptor = {
		"t": "record",
		"entries": [
			["day", {"t": "date", "id": "day", "value": "2024-01-02"}],
			["dayAgain", {"t": "ref", "id": "day"}],
			[
				"when",
				{
					"t": "datetime",
					"id": "when",
					"value": "2024-01-02T03:04:05.006Z",
				},
			],
			["whenAgain", {"t": "ref", "id": "when"}],
		],
	}
	wire = cast(
		Serialized,
		[
			5,
			{
				"day": ["$", "d", "2024-01-02"],
				"dayAgain": ["$", "r", 1],
				"when": ["$", "t", "2024-01-02T03:04:05.006Z"],
				"whenAgain": ["$", "r", 2],
			},
		],
	)

	value = cast(dict[str, object], materialize(case))
	assert serialize(value) == wire
	python_decoded = cast(dict[str, object], deserialize(wire))
	assert python_decoded["day"] is python_decoded["dayAgain"]
	assert python_decoded["when"] is python_decoded["whenAgain"]

	javascript_encoded = cast(
		list[dict[str, object]],
		run_javascript({"op": "encode", "cases": [case]}),
	)
	assert javascript_encoded[0]["wire"] == wire
	javascript_transcoded = cast(
		list[dict[str, object]],
		run_javascript({"op": "transcode", "wires": [wire]}),
	)
	assert javascript_transcoded[0]["wire"] == wire


def test_marker_structure_does_not_consume_implicit_ids():
	case: Descriptor = {
		"t": "record",
		"entries": [
			[
				"map",
				{
					"t": "map",
					"entries": [
						[
							"day",
							{
								"t": "date",
								"id": "day",
								"value": "2024-01-02",
							},
						],
					],
				},
			],
			["again", {"t": "ref", "id": "day"}],
			["escaped", {"t": "array", "items": [{"t": "string", "value": "$"}]}],
		],
	}
	wire = cast(
		Serialized,
		[
			5,
			{
				"map": [
					"$",
					"m",
					[["day", ["$", "d", "2024-01-02"]]],
				],
				"again": ["$", "r", 2],
				"escaped": ["$", "a", ["$"]],
			},
		],
	)

	value = cast(dict[str, object], materialize(case))
	assert serialize(value) == wire
	python_decoded = cast(dict[str, object], deserialize(wire))
	decoded_map = cast(WireMap, python_decoded["map"])
	assert decoded_map["day"] is python_decoded["again"]

	javascript_encoded = cast(
		list[dict[str, object]],
		run_javascript({"op": "encode", "cases": [case]}),
	)
	assert javascript_encoded[0]["wire"] == wire
	javascript_transcoded = cast(
		list[dict[str, object]],
		run_javascript({"op": "transcode", "wires": [wire]}),
	)
	assert javascript_transcoded[0]["wire"] == wire


def test_both_decoders_reject_the_shared_malformed_corpus():
	wires = malformed_wires()
	for wire in wires:
		with pytest.raises((TypeError, ValueError)):
			deserialize(cast(Serialized, json.loads(json.dumps(wire))))

	javascript_rejections = cast(
		list[bool],
		run_javascript({"op": "reject", "wires": wires}),
	)
	assert javascript_rejections == [True] * len(wires)


def test_both_decoders_accept_integral_json_number_reference_ids():
	wire = cast(
		Serialized,
		json.loads('[5,[["$","r",0.0]]]'),
	)
	python_value = deserialize(wire)
	assert python_value[0] is python_value

	javascript = cast(
		list[dict[str, object]],
		run_javascript({"op": "transcode", "wires": [wire]}),
	)
	assert javascript[0]["snapshot"] == [
		"array",
		0,
		[["ref", 0]],
	]
