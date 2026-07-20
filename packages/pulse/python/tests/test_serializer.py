from __future__ import annotations

import datetime as dt
import json
from dataclasses import FrozenInstanceError, dataclass
from typing import Any, cast, override

import pytest
from pulse.serializer import (
	PulseSerializable,
	Serializer,
	SerializerAdapter,
	WireMap,
	deserialize,
	serialize,
)


def wire_roundtrip(value: object) -> Any:
	return deserialize(json.loads(json.dumps(serialize(value))))


def test_serializer_configuration_is_immutable():
	class Value:
		pass

	adapter = SerializerAdapter(Value, lambda _: {"ok": True})
	serializer = Serializer([adapter])

	with pytest.raises(FrozenInstanceError):
		serializer._adapter_lookup = {}  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue]
	with pytest.raises(TypeError):
		serializer._adapter_lookup[Value] = adapter  # pyright: ignore[reportPrivateUsage,reportIndexIssue]


@pytest.mark.parametrize(
	"target",
	[
		object,
		type(None),
		bool,
		int,
		float,
		str,
		list,
		tuple,
		dict,
		set,
		dt.date,
		dt.datetime,
		WireMap,
	],
)
def test_rejects_adapters_for_core_types(target: type[object]):
	with pytest.raises(ValueError, match="core type"):
		Serializer([SerializerAdapter(target, lambda value: value)])


def test_rejects_duplicate_adapter_targets():
	class Value:
		pass

	with pytest.raises(ValueError, match="Duplicate serializer adapter"):
		Serializer(
			[
				SerializerAdapter(Value, lambda _: 1),
				SerializerAdapter(Value, lambda _: 2),
			]
		)


def test_adapter_resolution_uses_exact_then_nearest_mro():
	class Root:
		pass

	class Middle(Root):
		pass

	class Leaf(Middle):
		pass

	serializer = Serializer(
		[
			SerializerAdapter(Root, lambda _: "root"),
			SerializerAdapter(Middle, lambda _: "middle"),
		]
	)

	assert serializer.serialize(Leaf()) == [5, "middle"]


def test_configured_adapter_beats_to_pulse_and_dataclass_projection():
	@dataclass
	class Value(PulseSerializable):
		name: str

		@override
		def to_pulse(self) -> object:
			return {"source": "self", "name": self.name}

	serializer = Serializer(
		[
			SerializerAdapter(
				Value, lambda value: {"source": "adapter", "name": value.name}
			)
		]
	)

	assert serializer.serialize(Value("x")) == [
		5,
		{"source": "adapter", "name": "x"},
	]


def test_to_pulse_precedes_dataclass_projection():
	@dataclass
	class Value(PulseSerializable):
		ignored: str

		@override
		def to_pulse(self) -> object:
			return {"kept": True}

	assert serialize(Value("x")) == [5, {"kept": True}]


def test_dataclasses_project_fields_and_preserve_cycles():
	@dataclass
	class Node:
		name: str
		child: object = None

	root = Node("root")
	root.child = root

	assert serialize(root) == [5, {"name": "root", "child": ["$", 0]}]
	decoded = wire_roundtrip(root)
	assert decoded["child"] is decoded


def test_structural_adapter_projection_reuses_source_identity():
	class Node:
		def __init__(self, name: str) -> None:
			self.name: str = name
			self.child: Node | None = None

	root = Node("root")
	root.child = root
	serializer = Serializer(
		[SerializerAdapter(Node, lambda node: {"name": node.name, "child": node.child})]
	)

	wire = serializer.serialize({"first": root, "second": root})
	assert wire == [
		5,
		{
			"first": {"name": "root", "child": ["$", 1]},
			"second": ["$", 1],
		},
	]
	decoded = cast(dict[str, Any], serializer.deserialize(json.loads(json.dumps(wire))))
	assert decoded["first"] is decoded["second"]
	assert decoded["first"]["child"] is decoded["first"]


def test_fresh_adapter_projections_never_alias_via_id_reuse():
	class Point:
		def __init__(self, n: int) -> None:
			self.n: int = n

	serializer = Serializer([SerializerAdapter(Point, lambda point: {"n": point.n})])

	# Each projection is a temporary; if the encoder tracks identities by id()
	# without keeping the object alive, CPython reuses the freed address and
	# later points collapse into back references to the first one.
	wire = serializer.serialize([Point(n) for n in range(50)])
	assert wire == [5, [{"n": n} for n in range(50)]]


def test_adapter_projection_root_aliases_existing_container_identity():
	class Wrapper:
		def __init__(self, value: dict[str, object]) -> None:
			self.value: dict[str, object] = value

	shared: dict[str, object] = {"ok": True}
	wrapped = Wrapper(shared)
	serializer = Serializer([SerializerAdapter(Wrapper, lambda value: value.value)])

	wire = serializer.serialize({"shared": shared, "wrapped": wrapped})
	assert wire == [5, {"shared": {"ok": True}, "wrapped": ["$", 1]}]
	decoded = cast(dict[str, Any], serializer.deserialize(wire))
	assert decoded["shared"] is decoded["wrapped"]


def test_scalar_adapter_projection_has_value_semantics():
	class Value:
		pass

	value = Value()
	serializer = Serializer([SerializerAdapter(Value, lambda _: "projected")])

	assert serializer.serialize([value, value]) == [5, ["projected", "projected"]]


def test_adapter_output_recursively_uses_other_adapters():
	class Outer:
		def __init__(self, inner: Inner) -> None:
			self.inner: Inner = inner

	class Inner:
		def __init__(self, value: int) -> None:
			self.value: int = value

	serializer = Serializer(
		[
			SerializerAdapter(Outer, lambda value: value.inner),
			SerializerAdapter(Inner, lambda value: {"value": value.value}),
		]
	)

	assert serializer.serialize(Outer(Inner(3))) == [5, {"value": 3}]


def test_adapter_can_project_through_finite_chain_of_same_type():
	class Box:
		def __init__(self, value: object) -> None:
			self.value: object = value

	serializer = Serializer([SerializerAdapter(Box, lambda box: box.value)])

	assert serializer.serialize(Box(Box(Box(3)))) == [5, 3]


def test_to_pulse_can_project_through_finite_chain_of_same_type():
	class Box(PulseSerializable):
		def __init__(self, value: object) -> None:
			self.value: object = value

		@override
		def to_pulse(self) -> object:
			return self.value

	assert serialize(Box(Box(Box(3)))) == [5, 3]


def test_adapter_direct_return_and_projection_cycles_fail():
	class Left:
		pass

	class Right:
		pass

	left = Left()
	right = Right()
	direct = Serializer([SerializerAdapter(Left, lambda value: value)])
	cycle = Serializer(
		[
			SerializerAdapter(Left, lambda _: right),
			SerializerAdapter(Right, lambda _: left),
		]
	)

	with pytest.raises(ValueError, match="returned its source"):
		direct.serialize(left)
	with pytest.raises(ValueError, match="projection cycle"):
		cycle.serialize(left)


def test_adapter_fresh_object_non_convergence_is_bounded():
	class Left:
		pass

	class Right:
		pass

	serializer = Serializer(
		[
			SerializerAdapter(Left, lambda _: Right()),
			SerializerAdapter(Right, lambda _: Left()),
		]
	)

	with pytest.raises(ValueError, match="projection exceeded 64 steps"):
		serializer.serialize(Left())


def test_container_subclasses_use_builtin_storage_after_adapter_resolution():
	class Values(list[object]):
		@override
		def __iter__(self):
			raise AssertionError("override must not run")

	values = Values([1, 2])
	assert serialize(values) == [5, [1, 2]]

	serializer = Serializer([SerializerAdapter(Values, lambda _: ["adapted"])])
	assert serializer.serialize(values) == [5, ["adapted"]]


def test_arbitrary_dunder_dict_objects_are_rejected():
	class Value:
		def __init__(self) -> None:
			self.visible: bool = True

	with pytest.raises(TypeError, match="unsupported value of type Value"):
		serialize(Value())
