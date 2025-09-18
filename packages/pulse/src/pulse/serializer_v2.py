"""
Serializer v2: Flatted-like format with extension support.

Format:
- Serialized value is a tuple: (extension_indices_per_extension, entries)
- entries is a flat list of nodes:
  - primitives: int | float | str | bool
  - list: list of child indices
  - dict: str -> child index

Extensions:
- Each extension is an object with three callables: check(x) -> bool, encode(x) -> JSON-like, decode(JSON-like) -> object
- During serialization, when check(value) is True, encode(value) is serialized and the node index is recorded under that extension.
- During deserialization, if a node index is marked for an extension, the node is first resolved into a regular Python value and then passed to extension.decode to obtain the final value.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, Protocol, Sequence, Tuple, TypeVar

Primitive = int | float | str | bool
DataEntry = Primitive | list[int] | dict[str, int]
Serialized = Tuple[list[list[int]], list[DataEntry]]

T = TypeVar("T")
R = TypeVar("R")

class Extension(Protocol, Generic[T]):
    @staticmethod
    def check(value: T) -> bool: ...
    @staticmethod
    def encode(value: T, encode: Callable[[Any], int]) -> Any: ...
    @staticmethod
    def decode(entry: Any, decode: Callable[[int], Any]) -> T: ...


def serialize(data: Any, extensions: Sequence[Extension]) -> Serialized:
    entries: list[DataEntry] = []
    ext_idx_lists: list[list[int]] = [[] for _ in extensions]

    # Use identity for objects/containers; primitives don't get identity de-dup by default
    seen_by_id: dict[int, int] = {}

    def add(value: Any) -> int:
        # Identity-based memoization for containers and objects
        if isinstance(value, (dict, list)) or (
            not isinstance(value, Primitive) and hasattr(value, "__dict__")
        ):
            obj_id = id(value)
            if obj_id in seen_by_id:
                return seen_by_id[obj_id]

        # Primitives are stored directly
        if isinstance(value, Primitive):
            idx = len(entries)
            entries.append(value)
            return idx

        # Extensions
        for e, ext in enumerate(extensions):
            if ext.check(value):
                obj_id = id(value)
                if obj_id in seen_by_id:
                    return seen_by_id[obj_id]
                idx = len(entries)
                # placeholder to support cycles during encode
                entries.append([])
                seen_by_id[obj_id] = idx
                entry = ext.encode(value, lambda v: add(v))
                entries[idx] = entry
                ext_idx_lists[e].append(idx)
                return idx

        # Containers
        if isinstance(value, list):
            idx = len(entries)
            entries.append([])
            seen_by_id[id(value)] = idx
            child_indices: list[int] = []
            for item in value:
                child_indices.append(add(item))
            entries[idx] = child_indices
            return idx

        if isinstance(value, dict):
            idx = len(entries)
            entries.append({})
            seen_by_id[id(value)] = idx
            obj_map: dict[str, int] = {}
            for k, v in value.items():
                obj_map[str(k)] = add(v)
            entries[idx] = obj_map
            return idx

        # Fallback for objects with __dict__ (serialize public attributes)
        if hasattr(value, "__dict__"):
            idx = len(entries)
            entries.append({})
            seen_by_id[id(value)] = idx
            rec: dict[str, int] = {}
            for k, v in value.__dict__.items():
                if k.startswith("_"):
                    continue
                rec[str(k)] = add(v)
            entries[idx] = rec
            return idx

        raise TypeError(f"Unsupported value for serialize(): {type(value)}")

    add(data)
    return (ext_idx_lists, entries)


def deserialize(data: Serialized, extensions: Sequence[Extension]) -> Any:
    ext_idx_lists, entries = data

    node_to_ext: dict[int, int] = {}
    for e, indices in enumerate(ext_idx_lists):
        for idx in indices:
            node_to_ext[idx] = e

    resolved: dict[int, Any] = {}

    def resolve(idx: int) -> Any:
        if idx in resolved:
            return resolved[idx]

        try:
            entry = entries[idx]
        except IndexError:
            raise ValueError(f"Invalid serialized data: missing entry at index {idx}")

        # Extension decoding
        if idx in node_to_ext:
            ext_index = node_to_ext[idx]
            ext = extensions[ext_index]
            entry = entries[idx]
            val = ext.decode(entry, lambda j: resolve(j))
            resolved[idx] = val
            return val

        # Primitives
        if isinstance(entry, Primitive):
            resolved[idx] = entry
            return entry

        # Array node
        if isinstance(entry, list):
            arr: list[Any] = []
            resolved[idx] = arr
            for child in entry:
                arr.append(resolve(child))
            return arr

        # Object node
        if isinstance(entry, dict):
            obj: dict[str, Any] = {}
            resolved[idx] = obj
            for k, child in entry.items():
                obj[k] = resolve(child)
            return obj

        raise TypeError(f"Invalid entry type at index {idx}: {type(entry)}")

    if not entries:
        raise ValueError("Invalid serialized data: empty entries array")
    return resolve(0)
