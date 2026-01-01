from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any, ClassVar, NamedTuple, TypedDict, final

# ============================================================
# Node kind constants
# ============================================================

K_LIT = 0
K_ADD = 1
K_MUL = 2
K_LIST = 3
K_OBJ = 4

# ============================================================
# Variant 1: plain tagged tuples
# ============================================================

TupleNode = tuple  # (kind, ...)


def build_tuple_tree(depth: int, leaf_value: int = 1) -> TupleNode:
	"""
	Build a tree using plain tuples with varied node types.

	Shapes:
	  (K_LIT, value)
	  (K_ADD, left_node, right_node)
	  (K_MUL, left_node, right_node)
	  (K_LIST, child1, child2, ...)
	  (K_OBJ, (key1, val1), (key2, val2), ...)
	"""
	if depth == 0:
		return (K_LIT, leaf_value)

	mod = depth % 4
	if mod == 0:
		# List node with 5 children
		return (
			K_LIST,
			build_tuple_tree(depth - 1, leaf_value),
			build_tuple_tree(depth - 1, leaf_value + 1),
			build_tuple_tree(depth - 1, leaf_value + 2),
			build_tuple_tree(depth - 1, leaf_value + 3),
			build_tuple_tree(depth - 1, leaf_value + 4),
		)
	elif mod == 1:
		# Object node with 5 key-value pairs
		return (
			K_OBJ,
			("k1", build_tuple_tree(depth - 1, leaf_value)),
			("k2", build_tuple_tree(depth - 1, leaf_value + 1)),
			("k3", build_tuple_tree(depth - 1, leaf_value + 2)),
			("k4", build_tuple_tree(depth - 1, leaf_value + 3)),
			("k5", build_tuple_tree(depth - 1, leaf_value + 4)),
		)
	elif mod == 2:
		return (
			K_ADD,
			build_tuple_tree(depth - 1, leaf_value),
			build_tuple_tree(depth - 1, leaf_value + 1),
		)
	else:
		return (
			K_MUL,
			build_tuple_tree(depth - 1, leaf_value),
			build_tuple_tree(depth - 1, leaf_value + 1),
		)


def count_tuple(node: TupleNode, counts: list[int]) -> None:
	kind = node[0]
	counts[kind] += 1
	if kind == K_LIT:
		return
	elif kind == K_ADD or kind == K_MUL:
		count_tuple(node[1], counts)
		count_tuple(node[2], counts)
	elif kind == K_LIST:
		for child in node[1:]:
			count_tuple(child, counts)
	elif kind == K_OBJ:
		for _, val in node[1:]:
			count_tuple(val, counts)


# ============================================================
# Variant 2: NamedTuple-based nodes
# ============================================================


class LitNT(NamedTuple):
	value: int


class AddNT(NamedTuple):
	left: NTNode
	right: NTNode


class MulNT(NamedTuple):
	left: NTNode
	right: NTNode


class ListNT(NamedTuple):
	children: tuple[NTNode, ...]


class ObjNT(NamedTuple):
	fields: tuple[tuple[str, NTNode], ...]


NTNode = LitNT | AddNT | MulNT | ListNT | ObjNT


def build_namedtuple_tree(depth: int, leaf_value: int = 1) -> NTNode:
	if depth == 0:
		return LitNT(leaf_value)

	mod = depth % 4
	if mod == 0:
		return ListNT(
			(
				build_namedtuple_tree(depth - 1, leaf_value),
				build_namedtuple_tree(depth - 1, leaf_value + 1),
				build_namedtuple_tree(depth - 1, leaf_value + 2),
				build_namedtuple_tree(depth - 1, leaf_value + 3),
				build_namedtuple_tree(depth - 1, leaf_value + 4),
			)
		)
	elif mod == 1:
		return ObjNT(
			(
				("k1", build_namedtuple_tree(depth - 1, leaf_value)),
				("k2", build_namedtuple_tree(depth - 1, leaf_value + 1)),
				("k3", build_namedtuple_tree(depth - 1, leaf_value + 2)),
				("k4", build_namedtuple_tree(depth - 1, leaf_value + 3)),
				("k5", build_namedtuple_tree(depth - 1, leaf_value + 4)),
			)
		)
	elif mod == 2:
		return AddNT(
			build_namedtuple_tree(depth - 1, leaf_value),
			build_namedtuple_tree(depth - 1, leaf_value + 1),
		)
	else:
		return MulNT(
			build_namedtuple_tree(depth - 1, leaf_value),
			build_namedtuple_tree(depth - 1, leaf_value + 1),
		)


def count_namedtuple(node: NTNode, counts: dict[type, int]) -> None:
	t = type(node)
	counts[t] += 1
	if t is LitNT:
		return
	elif t is AddNT or t is MulNT:
		count_namedtuple(node.left, counts)
		count_namedtuple(node.right, counts)
	elif t is ListNT:
		for child in node.children:
			count_namedtuple(child, counts)
	elif t is ObjNT:
		for _, val in node.fields:
			count_namedtuple(val, counts)


# ============================================================
# Variant 3: dataclass + slots + ClassVar kind
# ============================================================


@dataclass(slots=True)
class DCNode:
	"""Base type just for typing / structure."""


@dataclass(slots=True)
class DCLit(DCNode):
	kind: ClassVar[int] = K_LIT
	value: int


@dataclass(slots=True)
class DCAdd(DCNode):
	kind: ClassVar[int] = K_ADD
	left: DCNode
	right: DCNode


@dataclass(slots=True)
class DCMul(DCNode):
	kind: ClassVar[int] = K_MUL
	left: DCNode
	right: DCNode


@dataclass(slots=True)
class DCList(DCNode):
	kind: ClassVar[int] = K_LIST
	children: tuple[DCNode, ...]


@dataclass(slots=True)
class DCObj(DCNode):
	kind: ClassVar[int] = K_OBJ
	fields: tuple[tuple[str, DCNode], ...]


def build_dataclass_tree(depth: int, leaf_value: int = 1) -> DCNode:
	if depth == 0:
		return DCLit(leaf_value)

	mod = depth % 4
	if mod == 0:
		return DCList(
			(
				build_dataclass_tree(depth - 1, leaf_value),
				build_dataclass_tree(depth - 1, leaf_value + 1),
				build_dataclass_tree(depth - 1, leaf_value + 2),
				build_dataclass_tree(depth - 1, leaf_value + 3),
				build_dataclass_tree(depth - 1, leaf_value + 4),
			)
		)
	elif mod == 1:
		return DCObj(
			(
				("k1", build_dataclass_tree(depth - 1, leaf_value)),
				("k2", build_dataclass_tree(depth - 1, leaf_value + 1)),
				("k3", build_dataclass_tree(depth - 1, leaf_value + 2)),
				("k4", build_dataclass_tree(depth - 1, leaf_value + 3)),
				("k5", build_dataclass_tree(depth - 1, leaf_value + 4)),
			)
		)
	elif mod == 2:
		return DCAdd(
			build_dataclass_tree(depth - 1, leaf_value),
			build_dataclass_tree(depth - 1, leaf_value + 1),
		)
	else:
		return DCMul(
			build_dataclass_tree(depth - 1, leaf_value),
			build_dataclass_tree(depth - 1, leaf_value + 1),
		)


def count_dataclass(node: DCNode, counts: list[int]) -> None:
	kind = node.kind
	counts[kind] += 1
	if kind == K_LIT:
		return
	elif kind == K_ADD or kind == K_MUL:
		count_dataclass(node.left, counts)  # type: ignore[attr-defined]
		count_dataclass(node.right, counts)  # type: ignore[attr-defined]
	elif kind == K_LIST:
		for child in node.children:  # type: ignore[attr-defined]
			count_dataclass(child, counts)
	elif kind == K_OBJ:
		for _, val in node.fields:  # type: ignore[attr-defined]
			count_dataclass(val, counts)


# ============================================================
# Variant 3b: dataclass + slots + virtual methods
# ============================================================


# @dataclass(slots=True)
# class DCVMNode(ABC):
# 	"""Base type with virtual methods."""

# 	@abstractmethod
# 	def count(self, counts: list[int]) -> None:
# 		"""Count this node and recursively count children."""
# 		pass


@dataclass(slots=True)
class DCLitVM:
	value: int

	def count(self, counts: list[int]) -> None:
		counts[K_LIT] += 1


@dataclass(slots=True)
class DCAddVM:
	left: DCVMNode
	right: DCVMNode

	def count(self, counts: list[int]) -> None:
		counts[K_ADD] += 1
		self.left.count(counts)
		self.right.count(counts)


@dataclass(slots=True)
class DCMulVM:
	left: DCVMNode
	right: DCVMNode

	def count(self, counts: list[int]) -> None:
		counts[K_MUL] += 1
		self.left.count(counts)
		self.right.count(counts)


@dataclass(slots=True)
class DCListVM:
	children: tuple[DCVMNode, ...]

	def count(self, counts: list[int]) -> None:
		counts[K_LIST] += 1
		for child in self.children:
			child.count(counts)


@dataclass(slots=True)
class DCObjVM:
	fields: tuple[tuple[str, DCVMNode], ...]

	def count(self, counts: list[int]) -> None:
		counts[K_OBJ] += 1
		for _, val in self.fields:
			val.count(counts)


DCVMNode = DCLitVM | DCAddVM | DCMulVM | DCListVM | DCObjVM


def build_dataclass_vm_tree(depth: int, leaf_value: int = 1) -> DCVMNode:
	if depth == 0:
		return DCLitVM(leaf_value)

	mod = depth % 4
	if mod == 0:
		return DCListVM(
			(
				build_dataclass_vm_tree(depth - 1, leaf_value),
				build_dataclass_vm_tree(depth - 1, leaf_value + 1),
				build_dataclass_vm_tree(depth - 1, leaf_value + 2),
				build_dataclass_vm_tree(depth - 1, leaf_value + 3),
				build_dataclass_vm_tree(depth - 1, leaf_value + 4),
			)
		)
	elif mod == 1:
		return DCObjVM(
			(
				("k1", build_dataclass_vm_tree(depth - 1, leaf_value)),
				("k2", build_dataclass_vm_tree(depth - 1, leaf_value + 1)),
				("k3", build_dataclass_vm_tree(depth - 1, leaf_value + 2)),
				("k4", build_dataclass_vm_tree(depth - 1, leaf_value + 3)),
				("k5", build_dataclass_vm_tree(depth - 1, leaf_value + 4)),
			)
		)
	elif mod == 2:
		return DCAddVM(
			build_dataclass_vm_tree(depth - 1, leaf_value),
			build_dataclass_vm_tree(depth - 1, leaf_value + 1),
		)
	else:
		return DCMulVM(
			build_dataclass_vm_tree(depth - 1, leaf_value),
			build_dataclass_vm_tree(depth - 1, leaf_value + 1),
		)


def count_dataclass_vm(node: DCVMNode, counts: list[int]) -> None:
	node.count(counts)


# ============================================================
# Variant 4: plain slot classes + type dispatch
# ============================================================


@final
class LitSlot:
	__slots__ = ("value",)

	def __init__(self, value: int) -> None:
		self.value = value


@final
class AddSlot:
	__slots__ = ("left", "right")

	def __init__(self, left: SlotNode, right: SlotNode) -> None:
		self.left = left
		self.right = right


@final
class MulSlot:
	__slots__ = ("left", "right")

	def __init__(self, left: SlotNode, right: SlotNode) -> None:
		self.left = left
		self.right = right


@final
class ListSlot:
	__slots__ = ("children",)

	def __init__(self, children: tuple[SlotNode, ...]) -> None:
		self.children = children


@final
class ObjSlot:
	__slots__ = ("fields",)

	def __init__(self, fields: tuple[tuple[str, SlotNode], ...]) -> None:
		self.fields = fields


SlotNode = LitSlot | AddSlot | MulSlot | ListSlot | ObjSlot


def build_slot_tree(depth: int, leaf_value: int = 1) -> SlotNode:
	if depth == 0:
		return LitSlot(leaf_value)

	mod = depth % 4
	if mod == 0:
		return ListSlot(
			(
				build_slot_tree(depth - 1, leaf_value),
				build_slot_tree(depth - 1, leaf_value + 1),
				build_slot_tree(depth - 1, leaf_value + 2),
				build_slot_tree(depth - 1, leaf_value + 3),
				build_slot_tree(depth - 1, leaf_value + 4),
			)
		)
	elif mod == 1:
		return ObjSlot(
			(
				("k1", build_slot_tree(depth - 1, leaf_value)),
				("k2", build_slot_tree(depth - 1, leaf_value + 1)),
				("k3", build_slot_tree(depth - 1, leaf_value + 2)),
				("k4", build_slot_tree(depth - 1, leaf_value + 3)),
				("k5", build_slot_tree(depth - 1, leaf_value + 4)),
			)
		)
	elif mod == 2:
		return AddSlot(
			build_slot_tree(depth - 1, leaf_value),
			build_slot_tree(depth - 1, leaf_value + 1),
		)
	else:
		return MulSlot(
			build_slot_tree(depth - 1, leaf_value),
			build_slot_tree(depth - 1, leaf_value + 1),
		)


def count_slot(node: SlotNode, counts: dict[type, int]) -> None:
	t = type(node)
	counts[t] += 1
	if t is LitSlot:
		return
	elif t is AddSlot or t is MulSlot:
		count_slot(node.left, counts)
		count_slot(node.right, counts)
	elif t is ListSlot:
		for child in node.children:
			count_slot(child, counts)
	elif t is ObjSlot:
		for _, val in node.fields:
			count_slot(val, counts)


# ============================================================
# Variant 5: TypedDict-based nodes
# ============================================================


class LitTD(TypedDict):
	kind: int
	value: int


class AddTD(TypedDict):
	kind: int
	left: dict[str, Any]
	right: dict[str, Any]


class MulTD(TypedDict):
	kind: int
	left: dict[str, Any]
	right: dict[str, Any]


class ListTD(TypedDict):
	kind: int
	children: tuple[dict[str, Any], ...]


class ObjTD(TypedDict):
	kind: int
	fields: tuple[tuple[str, dict[str, Any]], ...]


TDNode = dict[str, Any]


def build_typeddict_tree(depth: int, leaf_value: int = 1) -> TDNode:
	if depth == 0:
		return {"kind": K_LIT, "value": leaf_value}

	mod = depth % 4
	if mod == 0:
		return {
			"kind": K_LIST,
			"children": (
				build_typeddict_tree(depth - 1, leaf_value),
				build_typeddict_tree(depth - 1, leaf_value + 1),
				build_typeddict_tree(depth - 1, leaf_value + 2),
				build_typeddict_tree(depth - 1, leaf_value + 3),
				build_typeddict_tree(depth - 1, leaf_value + 4),
			),
		}
	elif mod == 1:
		return {
			"kind": K_OBJ,
			"fields": (
				("k1", build_typeddict_tree(depth - 1, leaf_value)),
				("k2", build_typeddict_tree(depth - 1, leaf_value + 1)),
				("k3", build_typeddict_tree(depth - 1, leaf_value + 2)),
				("k4", build_typeddict_tree(depth - 1, leaf_value + 3)),
				("k5", build_typeddict_tree(depth - 1, leaf_value + 4)),
			),
		}
	elif mod == 2:
		return {
			"kind": K_ADD,
			"left": build_typeddict_tree(depth - 1, leaf_value),
			"right": build_typeddict_tree(depth - 1, leaf_value + 1),
		}
	else:
		return {
			"kind": K_MUL,
			"left": build_typeddict_tree(depth - 1, leaf_value),
			"right": build_typeddict_tree(depth - 1, leaf_value + 1),
		}


def count_typeddict(node: TDNode, counts: list[int]) -> None:
	kind = node["kind"]
	counts[kind] += 1
	if kind == K_LIT:
		return
	elif kind == K_ADD or kind == K_MUL:
		count_typeddict(node["left"], counts)
		count_typeddict(node["right"], counts)
	elif kind == K_LIST:
		for child in node["children"]:
			count_typeddict(child, counts)
	elif kind == K_OBJ:
		for _, val in node["fields"]:
			count_typeddict(val, counts)


# ============================================================
# Memory sizing helpers
# ============================================================


def size_tuple(node: TupleNode, seen: set[int]) -> int:
	oid = id(node)
	if oid in seen:
		return 0
	seen.add(oid)

	total = sys.getsizeof(node)
	kind = node[0]
	if kind == K_LIT:
		total += sys.getsizeof(node[1])
	elif kind == K_ADD or kind == K_MUL:
		total += size_tuple(node[1], seen)
		total += size_tuple(node[2], seen)
	elif kind == K_LIST:
		for child in node[1:]:
			total += size_tuple(child, seen)
	elif kind == K_OBJ:
		for pair in node[1:]:
			total += sys.getsizeof(pair)
			key, val = pair
			total += sys.getsizeof(key)
			total += size_tuple(val, seen)
	return total


def size_namedtuple(node: NTNode, seen: set[int]) -> int:
	oid = id(node)
	if oid in seen:
		return 0
	seen.add(oid)

	total = sys.getsizeof(node)
	if isinstance(node, LitNT):
		total += sys.getsizeof(node.value)
	elif isinstance(node, (AddNT, MulNT)):
		total += size_namedtuple(node.left, seen)
		total += size_namedtuple(node.right, seen)
	elif isinstance(node, ListNT):
		total += sys.getsizeof(node.children)
		for child in node.children:
			total += size_namedtuple(child, seen)
	elif isinstance(node, ObjNT):
		total += sys.getsizeof(node.fields)
		for key, val in node.fields:
			total += sys.getsizeof(key)
			total += size_namedtuple(val, seen)
	return total


def size_dataclass(node: DCNode, seen: set[int]) -> int:
	oid = id(node)
	if oid in seen:
		return 0
	seen.add(oid)

	total = sys.getsizeof(node)
	kind = node.kind
	if kind == K_LIT:
		total += sys.getsizeof(node.value)  # type: ignore[attr-defined]
	elif kind == K_ADD or kind == K_MUL:
		total += size_dataclass(node.left, seen)  # type: ignore[attr-defined]
		total += size_dataclass(node.right, seen)  # type: ignore[attr-defined]
	elif kind == K_LIST:
		children = node.children  # type: ignore[attr-defined]
		total += sys.getsizeof(children)
		for child in children:
			total += size_dataclass(child, seen)
	elif kind == K_OBJ:
		fields = node.fields  # type: ignore[attr-defined]
		total += sys.getsizeof(fields)
		for key, val in fields:
			total += sys.getsizeof(key)
			total += size_dataclass(val, seen)
	return total


def size_dataclass_vm(node: DCVMNode, seen: set[int]) -> int:
	oid = id(node)
	if oid in seen:
		return 0
	seen.add(oid)

	total = sys.getsizeof(node)
	if isinstance(node, DCLitVM):
		total += sys.getsizeof(node.value)
	elif isinstance(node, (DCAddVM, DCMulVM)):
		total += size_dataclass_vm(node.left, seen)
		total += size_dataclass_vm(node.right, seen)
	elif isinstance(node, DCListVM):
		children = node.children
		total += sys.getsizeof(children)
		for child in children:
			total += size_dataclass_vm(child, seen)
	elif isinstance(node, DCObjVM):
		fields = node.fields
		total += sys.getsizeof(fields)
		for key, val in fields:
			total += sys.getsizeof(key)
			total += size_dataclass_vm(val, seen)
	return total


def size_slot(node: SlotNode, seen: set[int]) -> int:
	oid = id(node)
	if oid in seen:
		return 0
	seen.add(oid)

	total = sys.getsizeof(node)
	if isinstance(node, LitSlot):
		total += sys.getsizeof(node.value)
	elif isinstance(node, (AddSlot, MulSlot)):
		total += size_slot(node.left, seen)
		total += size_slot(node.right, seen)
	elif isinstance(node, ListSlot):
		children = node.children
		total += sys.getsizeof(children)
		for child in children:
			total += size_slot(child, seen)
	elif isinstance(node, ObjSlot):
		fields = node.fields
		total += sys.getsizeof(fields)
		for key, val in fields:
			total += sys.getsizeof(key)
			total += size_slot(val, seen)
	return total


def size_typeddict(node: TDNode, seen: set[int]) -> int:
	oid = id(node)
	if oid in seen:
		return 0
	seen.add(oid)

	total = sys.getsizeof(node)
	kind = node["kind"]
	total += sys.getsizeof(kind)
	if kind == K_LIT:
		total += sys.getsizeof(node["value"])
	elif kind == K_ADD or kind == K_MUL:
		total += size_typeddict(node["left"], seen)
		total += size_typeddict(node["right"], seen)
	elif kind == K_LIST:
		children = node["children"]
		total += sys.getsizeof(children)
		for child in children:
			total += size_typeddict(child, seen)
	elif kind == K_OBJ:
		fields = node["fields"]
		total += sys.getsizeof(fields)
		for key, val in fields:
			total += sys.getsizeof(key)
			total += size_typeddict(val, seen)
	return total


def print_sizes(trees: list[tuple[str, Any, Any]]) -> None:
	print("\nMemory (deep size including children):")
	for label, tree, sizer in trees:
		size = sizer(tree, set())
		print(f"{label:25s} {size / (1024 * 1024):.3f} MiB  ({size} B)")


# ============================================================
# Benchmark harness
# ============================================================


def bench_count(
	label: str, count_func, tree, make_counts, iterations: int = 100
) -> None:
	# Warmup
	for _ in range(10):
		count_func(tree, make_counts())

	start = time.perf_counter()
	for _ in range(iterations):
		counts = make_counts()
		count_func(tree, counts)
	elapsed = time.perf_counter() - start
	print(f"{label:25s} {elapsed:.3f}s  ({elapsed / iterations * 1000:.2f}ms/iter)")


def main(skip_perf: bool = False) -> None:
	depth = 12
	print(f"Building trees at depth {depth} ...")

	tuple_tree = build_tuple_tree(depth)
	nt_tree = build_namedtuple_tree(depth)
	dc_tree = build_dataclass_tree(depth)
	dc_vm_tree = build_dataclass_vm_tree(depth)
	slot_tree = build_slot_tree(depth)
	td_tree = build_typeddict_tree(depth)

	# Count nodes to verify tree sizes match
	tuple_counts: list[int] = [0, 0, 0, 0, 0]
	count_tuple(tuple_tree, tuple_counts)
	total_nodes = sum(tuple_counts)
	print(f"Total nodes: {total_nodes}")
	print(
		f"  LIT={tuple_counts[K_LIT]} ADD={tuple_counts[K_ADD]} MUL={tuple_counts[K_MUL]} LIST={tuple_counts[K_LIST]} OBJ={tuple_counts[K_OBJ]}"
	)

	# Verify all variants count the same nodes
	nt_counts = {LitNT: 0, AddNT: 0, MulNT: 0, ListNT: 0, ObjNT: 0}
	count_namedtuple(nt_tree, nt_counts)
	dc_counts: list[int] = [0, 0, 0, 0, 0]
	count_dataclass(dc_tree, dc_counts)
	dc_vm_counts: list[int] = [0, 0, 0, 0, 0]
	count_dataclass_vm(dc_vm_tree, dc_vm_counts)
	slot_counts = {LitSlot: 0, AddSlot: 0, MulSlot: 0, ListSlot: 0, ObjSlot: 0}
	count_slot(slot_tree, slot_counts)
	td_counts: list[int] = [0, 0, 0, 0, 0]
	count_typeddict(td_tree, td_counts)

	# Normalize to list format for comparison
	nt_normalized = [
		nt_counts[LitNT],
		nt_counts[AddNT],
		nt_counts[MulNT],
		nt_counts[ListNT],
		nt_counts[ObjNT],
	]
	slot_normalized = [
		slot_counts[LitSlot],
		slot_counts[AddSlot],
		slot_counts[MulSlot],
		slot_counts[ListSlot],
		slot_counts[ObjSlot],
	]

	all_match = (
		tuple_counts == dc_counts
		and tuple_counts == dc_vm_counts
		and tuple_counts == nt_normalized
		and tuple_counts == slot_normalized
		and tuple_counts == td_counts
	)
	if all_match:
		print("✓ All variants count the same nodes")
	else:
		print("✗ Count mismatch detected!")
		print(f"  tuple:     {tuple_counts}")
		print(f"  dataclass: {dc_counts}")
		print(f"  dataclass+vm: {dc_vm_counts}")
		print(f"  namedtuple: {nt_normalized}")
		print(f"  slots:     {slot_normalized}")
		print(f"  typeddict:  {td_counts}")

	if not skip_perf:
		print("\nBenchmark (count traversal):")
		bench_count("tuple", count_tuple, tuple_tree, lambda: [0, 0, 0, 0, 0])
		bench_count(
			"namedtuple",
			count_namedtuple,
			nt_tree,
			lambda: {LitNT: 0, AddNT: 0, MulNT: 0, ListNT: 0, ObjNT: 0},
		)
		bench_count("dataclass", count_dataclass, dc_tree, lambda: [0, 0, 0, 0, 0])
		bench_count(
			"dataclass+vm", count_dataclass_vm, dc_vm_tree, lambda: [0, 0, 0, 0, 0]
		)
		bench_count(
			"slots+type",
			count_slot,
			slot_tree,
			lambda: {LitSlot: 0, AddSlot: 0, MulSlot: 0, ListSlot: 0, ObjSlot: 0},
		)
		bench_count("typeddict", count_typeddict, td_tree, lambda: [0, 0, 0, 0, 0])

	print_sizes(
		[
			("tuple", tuple_tree, size_tuple),
			("namedtuple", nt_tree, size_namedtuple),
			("dataclass", dc_tree, size_dataclass),
			("dataclass+vm", dc_vm_tree, size_dataclass_vm),
			("slots+type", slot_tree, size_slot),
			("typeddict", td_tree, size_typeddict),
		]
	)


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--skip-perf", action="store_true", help="Skip performance benchmark"
	)
	args = parser.parse_args()
	main(skip_perf=args.skip_perf)
