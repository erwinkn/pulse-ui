#!/usr/bin/env python3

import json
import datetime
from pulse.flatted import stringify


def create_test_data():
    """Create complex test data that matches our test cases."""

    # Create complex test data
    test_data = {
        # Primitives
        "nullValue": None,
        "number": 42,
        "float": 3.14159,
        "string": "Hello, JavaScript!",
        "boolean": True,
        # Date objects
        "singleDate": datetime.datetime(
            2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
        ),
        # Arrays
        "simpleArray": [1, "hello", True, None],
        "nestedArray": [[1, 2], [3, 4]],
        # Objects
        "simpleObject": {"name": "test", "value": 42, "active": True},
        "nestedObject": {
            "user": {"name": "Alice", "age": 30},
            "settings": {"theme": "dark", "notifications": True},
        },
        # Empty containers
        "emptyObject": {},
        "emptyArray": [],
    }

    # Add shared references
    shared_date = datetime.datetime(
        2023, 6, 15, 12, 30, 0, tzinfo=datetime.timezone.utc
    )
    test_data["sharedDateStart"] = shared_date
    test_data["sharedDateEnd"] = shared_date

    shared_object = {"value": 99, "type": "shared"}
    test_data["sharedFirst"] = shared_object
    test_data["sharedSecond"] = shared_object

    # Add circular references
    circular_obj = {"name": "circular", "value": 123}
    circular_obj["self"] = circular_obj
    test_data["circular"] = circular_obj

    # Mutual circular references
    obj_a = {"name": "A"}
    obj_b = {"name": "B"}
    obj_a["refToB"] = obj_b
    obj_b["refToA"] = obj_a
    test_data["mutualA"] = obj_a
    test_data["mutualB"] = obj_b

    # Complex circular structure
    test_data["complexCircular"] = {
        "root": True,
        "child": {
            "parent": None,  # Will be set to test_data["complexCircular"]
            "data": [1, 2, 3],
        },
    }
    test_data["complexCircular"]["child"]["parent"] = test_data["complexCircular"]

    # Self-reference on main object
    test_data["selfRef"] = test_data

    return test_data


def main():
    print("🐍 Python serializer starting...")

    # Create test data
    print("\nCreating test data...")
    test_data = create_test_data()

    print("Test data structure:")
    print("- Primitives: null, number, float, string, boolean")
    print("- Dates: single date, shared date references")
    print("- Arrays: simple, nested")
    print("- Objects: simple, nested, empty containers")
    print("- Shared references: date and object")
    print("- Circular references: self, mutual, complex, self-ref on root")

    # Serialize using our custom stringify
    print("\n🔄 Serializing with Pulse stringify()...")
    try:
        serialized = stringify(test_data)
        print("✅ Successfully serialized data")
    except Exception as e:
        print(f"❌ Error during serialization: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # Write to JSON file
    print("\n📝 Writing to python-to-js-payload.json...")
    try:
        json_payload = json.dumps(serialized, indent=2)
        with open("python-to-js-payload.json", "w") as f:
            f.write(json_payload)
        print("✅ Successfully wrote JSON payload")
        print(f"📄 File size: {len(json_payload)} bytes")
    except Exception as e:
        print(f"❌ Error writing JSON file: {e}")
        return 1

    print("\n🎉 Python serialization complete!")
    print("\nYou can now run the JavaScript deserializer:")
    print("bun test-js-from-python.js")

    return 0


if __name__ == "__main__":
    exit(main())
