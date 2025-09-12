"""
Simple object transformation for socket.io transport
Handles Dates, circular references, and basic Python objects
"""

from datetime import datetime
from typing import Any


def stringify(input_value: Any) -> Any:
    """
    Convert Python objects into a serializable format that handles circular references.

    Args:
        input_value: The object to serialize

    Returns:
        A JSON-serializable object with special markers for complex types
    """
    seen: dict[int, int] = {}  # Map object id to assigned ID
    next_id = 1

    def transform(value: Any) -> Any:
        nonlocal next_id

        # Handle primitives
        if value is None or isinstance(value, (int, float, str, bool)):
            return value

        # Handle objects that can have circular references
        if isinstance(value, (dict, list, datetime)) or hasattr(value, "__dict__"):
            obj_id = id(value)
            if obj_id in seen:
                return {"__ref": seen[obj_id]}

        # Special type transformations
        if isinstance(value, datetime):
            current_id = next_id
            next_id += 1
            seen[id(value)] = current_id
            # Type checker safety: we know value is datetime here
            dt_value: datetime = value  # type: ignore
            return {
                "__pulse": "date",
                "__id": current_id,
                "timestamp": int(
                    dt_value.timestamp() * 1000
                ),  # Convert to milliseconds
            }

        # Handle lists
        if isinstance(value, list):
            current_id = next_id
            next_id += 1
            seen[id(value)] = current_id
            return {
                "__pulse": "array",
                "__id": current_id,
                "items": [transform(item) for item in value],
            }

        # Handle dictionaries
        if isinstance(value, dict):
            current_id = next_id
            next_id += 1
            seen[id(value)] = current_id

            user_data = {}
            for key, val in value.items():
                if callable(val):
                    continue  # Skip functions/methods
                user_data[str(key)] = transform(val)

            return {"__pulse": "object", "__id": current_id, "__data": user_data}

        # Handle custom objects with __dict__
        if hasattr(value, "__dict__"):
            current_id = next_id
            next_id += 1
            seen[id(value)] = current_id

            user_data = {}
            for key, val in value.__dict__.items():
                if callable(val) or key.startswith("_"):
                    continue  # Skip private attributes and methods
                user_data[str(key)] = transform(val)

            return {"__pulse": "object", "__id": current_id, "__data": user_data}

        # Fallback for unknown types - convert to string
        return str(value)

    return transform(input_value)


def parse(input_value: Any) -> Any:
    """
    Parse serialized objects back into Python objects, resolving circular references.

    Args:
        input_value: The serialized object to parse

    Returns:
        The reconstructed Python object
    """
    objects: dict[int, Any] = {}

    def resolve(value: Any) -> Any:
        if value is None or isinstance(value, (int, float, str, bool)):
            return value

        if isinstance(value, list):
            return [resolve(item) for item in value]

        if not isinstance(value, dict):
            return value

        obj = value

        # Handle references
        if "__ref" in obj:
            ref_id = obj["__ref"]
            return objects.get(ref_id)

        # Handle special types (only if they have __pulse marker)
        if obj.get("__pulse") == "date":
            obj_id = obj["__id"]
            timestamp_ms = obj["timestamp"]
            resolved_date = datetime.fromtimestamp(timestamp_ms / 1000.0)
            objects[obj_id] = resolved_date
            return resolved_date

        # Handle File objects serialized from the client
        if obj.get("__pulse") == "file":
            obj_id = obj["__id"]
            # Resolve the underlying binary payload if present (socket.io may provide bytes directly)
            raw_file_value = obj.get("file")
            resolved_bytes = resolve(raw_file_value)

            resolved_file = {
                "name": obj.get("name"),
                "type": obj.get("type"),
                "size": obj.get("size"),
                "last_modified": obj.get("lastModified"),
                "contents": resolved_bytes,
            }
            objects[obj_id] = resolved_file
            return resolved_file

        # Handle FormData objects serialized from the client
        if obj.get("__pulse") == "formdata":
            obj_id = obj["__id"]
            fields = obj.get("fields", {})
            resolved_formdata: dict[str, Any] = {}
            objects[obj_id] = resolved_formdata

            # Fields may contain single values or arrays (for duplicate keys)
            for key, value in fields.items():
                if isinstance(value, list):
                    resolved_formdata[key] = [resolve(item) for item in value]
                else:
                    resolved_formdata[key] = resolve(value)
            return resolved_formdata

        if obj.get("__pulse") == "array":
            obj_id = obj["__id"]
            resolved_list: list[Any] = []
            objects[obj_id] = resolved_list

            items = obj["items"]
            for item in items:
                resolved_list.append(resolve(item))
            return resolved_list

        if obj.get("__pulse") == "object":
            obj_id = obj["__id"]
            resolved_object: dict[str, Any] = {}
            objects[obj_id] = resolved_object

            user_data = obj["__data"]
            for key, val in user_data.items():
                resolved_object[key] = resolve(val)
            return resolved_object

        # Unknown object type - process properties
        result = {}
        for key, val in obj.items():
            result[key] = resolve(val)
        return result

    return resolve(input_value)
