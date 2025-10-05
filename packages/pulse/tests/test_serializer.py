"""
Tests for the flatted serialization module.
"""

import datetime
import pytest
from typing import Any, Dict
from pulse.serializer import stringify, parse


class TestFlatted:
    """Test suite for flatted serialization."""

    def test_primitives(self):
        """Test serialization of primitive types."""
        # None
        assert stringify(None) is None
        assert parse(None) is None

        # Numbers
        assert stringify(42) == 42
        assert parse(42) == 42

        assert stringify(3.14) == 3.14
        assert parse(3.14) == 3.14

        # Strings
        assert stringify("hello") == "hello"
        assert parse("hello") == "hello"

        # Booleans
        assert stringify(True) is True
        assert parse(True) is True

        assert stringify(False) is False
        assert parse(False) is False

    def test_datetime_objects(self):
        """Test serialization of datetime objects."""
        date = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        serialized = stringify(date)

        assert serialized == {
            "__pulse": "date",
            "__id": 1,
            "timestamp": int(date.timestamp() * 1000),
        }

        parsed = parse(serialized)
        assert isinstance(parsed, datetime.datetime)
        # Compare timestamps since timezone info might differ
        assert abs(parsed.timestamp() - date.timestamp()) < 0.001

    def test_multiple_datetime_objects_same_value(self):
        """Test handling multiple datetime objects with same value."""
        date1 = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        date2 = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        data = {"first": date1, "second": date2}

        serialized = stringify(data)
        parsed = parse(serialized)

        # Should have different datetime objects (same value, different identity)
        assert isinstance(parsed["first"], datetime.datetime)
        assert isinstance(parsed["second"], datetime.datetime)
        assert parsed["first"] == parsed["second"]

    def test_lists(self):
        """Test serialization of lists."""
        # Simple list
        arr = [1, "hello", True, None]
        serialized = stringify(arr)

        assert serialized == {
            "__pulse": "array",
            "__id": 1,
            "items": [1, "hello", True, None],
        }

        parsed = parse(serialized)
        assert parsed == arr

        # Nested lists
        arr = [[1, 2], [3, 4]]
        serialized = stringify(arr)
        parsed = parse(serialized)
        assert parsed == arr

        # Lists with objects
        arr = [{"a": 1}, {"b": 2}]
        serialized = stringify(arr)
        parsed = parse(serialized)
        assert parsed == arr

    def test_dictionaries(self):
        """Test serialization of dictionaries."""
        # Simple dict
        obj = {"name": "test", "value": 42, "active": True}
        serialized = stringify(obj)

        assert serialized == {
            "__pulse": "object",
            "__id": 1,
            "__data": {"name": "test", "value": 42, "active": True},
        }

        parsed = parse(serialized)
        assert parsed == obj

        # Nested dict
        obj = {
            "user": {"name": "Alice", "age": 30},
            "settings": {"theme": "dark", "notifications": True},
        }

        serialized = stringify(obj)
        parsed = parse(serialized)
        assert parsed == obj

    def test_custom_objects(self):
        """Test serialization of custom objects."""

        class Person:
            def __init__(self, name, age):
                self.name = name
                self.age = age
                self._private = "secret"  # Should be ignored

        person = Person("Alice", 30)
        serialized = stringify(person)
        parsed = parse(serialized)

        # Should serialize public attributes only
        assert parsed == {"name": "Alice", "age": 30}

    def test_circular_references(self):
        """Test handling of circular references."""
        # Simple circular reference
        obj: Dict[str, Any] = {"name": "test"}
        obj["self"] = obj

        serialized = stringify(obj)
        parsed = parse(serialized)

        assert parsed["name"] == "test"
        assert parsed["self"] is parsed

    def test_mutual_circular_references(self):
        """Test mutual circular references between objects."""
        a: Dict[str, Any] = {"name": "a"}
        b: Dict[str, Any] = {"name": "b"}
        a["b"] = b
        b["a"] = a

        serialized = stringify({"a": a, "b": b})
        parsed = parse(serialized)

        assert parsed["a"]["name"] == "a"
        assert parsed["b"]["name"] == "b"
        assert parsed["a"]["b"] is parsed["b"]
        assert parsed["b"]["a"] is parsed["a"]

    def test_circular_references_with_arrays(self):
        """Test circular references involving arrays."""
        arr: Any = [1, 2]
        arr.append(arr)

        serialized = stringify(arr)
        parsed = parse(serialized)

        assert parsed[0] == 1
        assert parsed[1] == 2
        assert parsed[2] is parsed

    def test_shared_references(self):
        """Test preservation of shared object references."""
        shared = {"value": 42}
        data = {"first": shared, "second": shared}

        serialized = stringify(data)
        parsed = parse(serialized)

        assert parsed["first"] is parsed["second"]
        assert parsed["first"]["value"] == 42

    def test_shared_datetime_references(self):
        """Test preservation of shared datetime references."""
        date = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        data = {"start": date, "end": date}

        serialized = stringify(data)
        parsed = parse(serialized)

        assert parsed["start"] is parsed["end"]
        assert isinstance(parsed["start"], datetime.datetime)

    def test_collision_resistance(self):
        """Test that user objects with special properties are preserved."""
        # User object with __pulse property
        user_obj = {"__pulse": "date", "value": 42}
        data = {"user": user_obj, "real": datetime.datetime.now()}

        serialized = stringify(data)
        parsed = parse(serialized)

        assert parsed["user"]["__pulse"] == "date"
        assert parsed["user"]["value"] == 42
        assert isinstance(parsed["real"], datetime.datetime)

    def test_collision_resistance_other_markers(self):
        """Test collision resistance with other special markers."""
        # User objects with various special properties
        test_cases = [
            {"__id": 123, "name": "test"},
            {"__ref": 42, "value": "test"},
            {"__data": {"nested": "value"}, "meta": "info"},
        ]

        for user_obj in test_cases:
            data = {"user": user_obj}
            serialized = stringify(data)
            parsed = parse(serialized)
            assert parsed["user"] == user_obj

    def test_complex_scenarios(self):
        """Test complex mixed data types with circular references."""
        date = datetime.datetime.now()
        obj = {
            "name": "complex",
            "date": date,
            "metadata": {
                "nested": {"deep": True, "value": 42},
            },
        }
        obj["self"] = obj  # circular reference
        obj["metadata"]["parent"] = obj  # another circular reference

        serialized = stringify(obj)
        parsed = parse(serialized)

        assert parsed["name"] == "complex"
        assert isinstance(parsed["date"], datetime.datetime)
        assert parsed["metadata"]["nested"]["deep"] is True
        assert parsed["metadata"]["nested"]["value"] == 42
        assert parsed["self"] is parsed
        assert parsed["metadata"]["parent"] is parsed

    def test_parse_file_object(self):
        """Manual parse test for File-like objects coming from the client."""
        file_bytes = b"\x00\x01abc"
        serialized = {
            "__pulse": "file",
            "__id": 1,
            "name": "foo.txt",
            "type": "text/plain",
            "size": 5,
            "lastModified": 1710000000000,
            "file": file_bytes,
        }

        parsed = parse(serialized)

        assert parsed["name"] == "foo.txt"
        assert parsed["type"] == "text/plain"
        assert parsed["size"] == 5
        assert parsed["last_modified"] == 1710000000000
        assert parsed["contents"] == file_bytes

    def test_parse_formdata_mixed_values(self):
        """Manual parse test for FormData-like objects with mixed value types."""
        date = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        serialized = {
            "__pulse": "formdata",
            "__id": 1,
            "fields": {
                "title": "hello",
                "tags": ["a", "b"],
                "when": {
                    "__pulse": "date",
                    "__id": 2,
                    "timestamp": int(date.timestamp() * 1000),
                },
                "upload": {
                    "__pulse": "file",
                    "__id": 3,
                    "name": "foo.txt",
                    "type": "text/plain",
                    "size": 5,
                    "lastModified": 1710000000000,
                    "file": b"abcde",
                },
            },
        }

        parsed = parse(serialized)

        assert parsed["title"] == "hello"
        assert parsed["tags"] == ["a", "b"]
        assert isinstance(parsed["when"], datetime.datetime)
        assert parsed["upload"]["name"] == "foo.txt"
        assert parsed["upload"]["contents"] == b"abcde"

    def test_parse_formdata_multiple_values_per_key(self):
        """FormData with duplicate keys should deserialize as lists of values."""
        file1 = {
            "__pulse": "file",
            "__id": 10,
            "name": "a.txt",
            "type": "text/plain",
            "size": 1,
            "lastModified": 1710000000000,
            "file": b"a",
        }
        file2 = {
            "__pulse": "file",
            "__id": 11,
            "name": "b.txt",
            "type": "text/plain",
            "size": 1,
            "lastModified": 1710000000001,
            "file": b"b",
        }

        serialized = {
            "__pulse": "formdata",
            "__id": 1,
            "fields": {
                "names": ["alice", "bob"],
                "files": [file1, file2],
            },
        }

        parsed = parse(serialized)

        assert parsed["names"] == ["alice", "bob"]
        assert isinstance(parsed["files"], list)
        assert parsed["files"][0]["name"] == "a.txt"
        assert parsed["files"][0]["contents"] == b"a"
        assert parsed["files"][1]["name"] == "b.txt"
        assert parsed["files"][1]["contents"] == b"b"

    def test_empty_containers(self):
        """Test empty objects and arrays."""
        data = {"empty": {"obj": {}, "arr": []}}

        serialized = stringify(data)
        parsed = parse(serialized)

        assert parsed == data

    def test_round_trip_fidelity(self):
        """Test that complex structures survive round trips."""
        date = datetime.datetime.now()

        complex_data = {
            "id": 123,
            "title": "Complex Data",
            "created": date,
            "updated": date,  # shared reference
            "tags": ["test", "example", "complex"],
            "metadata": {
                "nested": {"deep": True, "value": 42},
            },
            "empty": {"obj": {}, "arr": []},
        }

        # Add circular reference
        complex_data["self"] = complex_data
        complex_data["metadata"]["parent"] = complex_data

        serialized = stringify(complex_data)
        parsed = parse(serialized)

        # Verify all data types and references
        assert parsed["id"] == 123
        assert parsed["title"] == "Complex Data"
        assert isinstance(parsed["created"], datetime.datetime)
        assert parsed["created"] is parsed["updated"]  # shared reference
        assert parsed["tags"] == ["test", "example", "complex"]

        # Nested structure
        assert parsed["metadata"]["nested"]["deep"] is True
        assert parsed["metadata"]["nested"]["value"] == 42

        # Empty containers
        assert parsed["empty"]["obj"] == {}
        assert parsed["empty"]["arr"] == []

        # Circular references
        assert parsed["self"] is parsed
        assert parsed["metadata"]["parent"] is parsed
