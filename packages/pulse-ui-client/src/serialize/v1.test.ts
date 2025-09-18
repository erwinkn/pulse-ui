import { describe, it, expect } from "vitest";
import { stringify, parse } from "./v1";

describe("flatted serialization", () => {
  describe("primitives", () => {
    it("handles null", () => {
      const result = stringify(null);
      expect(result).toBe(null);
      expect(parse(result)).toBe(null);
    });

    it("handles numbers", () => {
      const result = stringify(42);
      expect(result).toBe(42);
      expect(parse(result)).toBe(42);
    });

    it("handles strings", () => {
      const result = stringify("hello");
      expect(result).toBe("hello");
      expect(parse(result)).toBe("hello");
    });

    it("handles booleans", () => {
      const result = stringify(true);
      expect(result).toBe(true);
      expect(parse(result)).toBe(true);
    });
  });

  describe("Date objects", () => {
    it("serializes and deserializes Dates", () => {
      const date = new Date("2024-01-01T00:00:00Z");
      const serialized = stringify(date);

      expect(serialized).toEqual({
        __pulse: "date",
        __id: 1,
        timestamp: date.getTime(),
      });

      const parsed = parse(serialized);
      expect(parsed).toBeInstanceOf(Date);
      expect((parsed as Date).getTime()).toBe(date.getTime());
    });

    it("handles multiple Date objects with same value", () => {
      const date1 = new Date("2024-01-01T00:00:00Z");
      const date2 = new Date("2024-01-01T00:00:00Z");
      const data = { date1, date2 };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.date1).toBeInstanceOf(Date);
      expect(parsed.date2).toBeInstanceOf(Date);
      expect(parsed.date1.getTime()).toBe(date1.getTime());
      expect(parsed.date2.getTime()).toBe(date2.getTime());
      // Different objects, so not reference-equal
      expect(parsed.date1).not.toBe(parsed.date2);
    });
  });

  describe("arrays", () => {
    it("handles simple arrays", () => {
      const arr = [1, "hello", true, null];
      const serialized = stringify(arr);

      expect(serialized).toEqual({
        __pulse: "array",
        __id: 1,
        items: [1, "hello", true, null],
      });

      const parsed = parse(serialized);
      expect(Array.isArray(parsed)).toBe(true);
      expect(parsed).toEqual(arr);
    });

    it("handles nested arrays", () => {
      const arr = [1, [2, 3], [4, [5, 6]]];
      const serialized = stringify(arr);
      const parsed = parse(serialized);

      expect(parsed).toEqual(arr);
    });

    it("handles arrays with objects", () => {
      const arr = [{ a: 1 }, { b: 2 }];
      const serialized = stringify(arr);
      const parsed = parse(serialized);

      expect(parsed).toEqual(arr);
    });
  });

  describe("objects", () => {
    it("handles simple objects", () => {
      const obj = { name: "test", value: 42, active: true };
      const serialized = stringify(obj);

      expect(serialized).toEqual({
        __pulse: "object",
        __id: 1,
        __data: { name: "test", value: 42, active: true },
      });

      const parsed = parse(serialized);
      expect(parsed).toEqual(obj);
    });

    it("handles nested objects", () => {
      const obj = {
        user: { name: "Alice", age: 30 },
        settings: { theme: "dark", notifications: true },
      };

      const serialized = stringify(obj);
      const parsed = parse(serialized);

      expect(parsed).toEqual(obj);
    });

    it("filters out functions, symbols, and undefined", () => {
      const sym = Symbol("test");
      const obj = {
        name: "test",
        fn: () => {},
        sym,
        undef: undefined,
        value: 42,
      };

      const serialized = stringify(obj);
      const parsed = parse(serialized) as any;

      expect(parsed.name).toBe("test");
      expect(parsed.value).toBe(42);
      expect(parsed.fn).toBeUndefined();
      expect(parsed.sym).toBeUndefined();
      expect(parsed.undef).toBeUndefined();
    });
  });

  describe("circular references", () => {
    it("handles simple circular references", () => {
      const obj: any = { name: "test" };
      obj.self = obj;

      const serialized = stringify(obj);
      const parsed = parse(serialized) as any;

      expect(parsed.name).toBe("test");
      expect(parsed.self).toBe(parsed);
    });

    it("handles mutual circular references", () => {
      const a: any = { name: "a" };
      const b: any = { name: "b" };
      a.b = b;
      b.a = a;

      const serialized = stringify({ a, b });
      const parsed = parse(serialized) as any;

      expect(parsed.a.name).toBe("a");
      expect(parsed.b.name).toBe("b");
      expect(parsed.a.b).toBe(parsed.b);
      expect(parsed.b.a).toBe(parsed.a);
    });

    it("handles circular references with arrays", () => {
      const arr: any[] = [1, 2];
      arr.push(arr);

      const serialized = stringify(arr);
      const parsed = parse(serialized) as any;

      expect(parsed[0]).toBe(1);
      expect(parsed[1]).toBe(2);
      expect(parsed[2]).toBe(parsed);
    });
  });

  describe("shared references", () => {
    it("preserves shared object references", () => {
      const shared = { value: 42 };
      const data = { first: shared, second: shared };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.first).toBe(parsed.second);
      expect(parsed.first.value).toBe(42);
    });

    it("preserves shared Date references", () => {
      const date = new Date("2024-01-01T00:00:00Z");
      const data = { start: date, end: date };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.start).toBe(parsed.end);
      expect(parsed.start).toBeInstanceOf(Date);
      expect(parsed.start.getTime()).toBe(date.getTime());
    });
  });

  describe("collision resistance", () => {
    it("preserves user objects with __pulse properties", () => {
      const userObj = { __pulse: "date", value: 42 };
      const data = { user: userObj, real: new Date() };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.user.__pulse).toBe("date");
      expect(parsed.user.value).toBe(42);
      expect(parsed.real).toBeInstanceOf(Date);
    });

    it("preserves user objects with __type properties", () => {
      const userObj = { __type: "date", timestamp: 999 };
      const data = { user: userObj, real: new Date(999) };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.user.__type).toBe("date");
      expect(parsed.user.timestamp).toBe(999);
      expect(parsed.user).not.toBeInstanceOf(Date);
      expect(parsed.real).toBeInstanceOf(Date);
    });

    it("preserves user objects with __id properties", () => {
      const userObj = { __id: 123, name: "test" };
      const data = { user: userObj };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.user.__id).toBe(123);
      expect(parsed.user.name).toBe("test");
    });

    it("preserves user objects with __ref properties", () => {
      const userObj = { __ref: 42, value: "test" };
      const data = { user: userObj };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.user.__ref).toBe(42);
      expect(parsed.user.value).toBe("test");
    });

    it("preserves user objects with __data properties", () => {
      const userObj = { __data: { nested: "value" }, meta: "info" };
      const data = { user: userObj };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.user.__data.nested).toBe("value");
      expect(parsed.user.meta).toBe("info");
    });
  });

  describe("complex scenarios", () => {
    it("handles mixed data types with circular references", () => {
      const date = new Date("2024-01-01T00:00:00Z");
      const arr = [1, 2, 3];
      const obj: any = {
        name: "complex",
        date,
        numbers: arr,
        metadata: {
          created: date, // shared reference
          tags: ["test", "example"],
        },
      };
      obj.self = obj; // circular reference
      obj.metadata.parent = obj; // another circular reference

      const serialized = stringify(obj);
      const parsed = parse(serialized) as any;

      expect(parsed.name).toBe("complex");
      expect(parsed.date).toBeInstanceOf(Date);
      expect(parsed.date.getTime()).toBe(date.getTime());
      expect(parsed.numbers).toEqual([1, 2, 3]);
      expect(parsed.metadata.created).toBe(parsed.date); // shared reference preserved
      expect(parsed.metadata.tags).toEqual(["test", "example"]);
      expect(parsed.self).toBe(parsed); // circular reference preserved
      expect(parsed.metadata.parent).toBe(parsed); // circular reference preserved
    });

    it("handles empty objects and arrays", () => {
      const data = {
        emptyObj: {},
        emptyArr: [],
        nested: {
          alsoEmpty: {},
          anotherArr: [],
        },
      };

      const serialized = stringify(data);
      const parsed = parse(serialized);

      expect(parsed).toEqual(data);
    });
  });

  describe("File objects", () => {
    it("handles File objects with metadata", () => {
      // Create a real File object
      const fileContent = new Uint8Array([72, 101, 108, 108, 111]); // "Hello"
      const file = new File([fileContent], "test.txt", {
        type: "text/plain",
        lastModified: 1640995200000, // 2022-01-01
      });

      const data = { document: file, metadata: { author: "test" } };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      // File should be restored to original location as File object
      expect(parsed.document).toBeInstanceOf(File);
      expect(parsed.document.name).toBe("test.txt");
      expect(parsed.document.type).toMatch(/^text\/plain/); // Bun adds charset
      expect(parsed.document.size).toBe(5);
      expect(parsed.document.lastModified).toBe(1640995200000);
      expect(parsed.metadata.author).toBe("test");
    });

    it("handles shared File references", () => {
      const file = new File(["content"], "shared.txt", { type: "text/plain" });
      const data = { first: file, second: file };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      // Should preserve shared reference
      expect(parsed.first).toBe(parsed.second);
      expect(parsed.first).toBeInstanceOf(File);
    });
  });

  describe("FormData objects", () => {
    it("handles FormData with various field types", () => {
      const formData = new FormData();
      const file = new File(["content"], "upload.txt", { type: "text/plain" });

      formData.append("name", "Alice");
      formData.append("age", "30");
      formData.append("active", "true");
      formData.append("document", file);

      const data = { form: formData };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      // FormData should be restored as FormData object
      expect(parsed.form).toBeInstanceOf(FormData);
      expect(parsed.form.get("name")).toBe("Alice");
      expect(parsed.form.get("age")).toBe("30");
      expect(parsed.form.get("active")).toBe("true");

      // File field should be restored as File object
      const fileField = parsed.form.get("document");
      expect(fileField).toBeInstanceOf(File);
      expect((fileField as File).name).toBe("upload.txt");
      expect((fileField as File).type).toMatch(/^text\/plain/); // Bun adds charset
    });

    it("handles FormData with multiple values for same field", () => {
      const formData = new FormData();
      const file1 = new File(["content1"], "file1.txt", { type: "text/plain" });
      const file2 = new File(["content2"], "file2.txt", { type: "text/plain" });

      formData.append("tag", "important");
      formData.append("tag", "urgent");
      formData.append("files", file1);
      formData.append("files", file2);

      const data = { form: formData };

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      // Multiple values should be preserved in FormData
      expect(parsed.form).toBeInstanceOf(FormData);
      const tags = parsed.form.getAll("tag");
      expect(tags).toEqual(["important", "urgent"]);

      const files = parsed.form.getAll("files");
      expect(files).toHaveLength(2);
      expect(files[0]).toBeInstanceOf(File);
      expect(files[1]).toBeInstanceOf(File);
      expect((files[0] as File).name).toBe("file1.txt");
      expect((files[1] as File).name).toBe("file2.txt");
    });

    it("handles FormData with circular references", () => {
      const formData = new FormData();
      formData.append("info", "test");

      const obj: any = { name: "test" };
      obj.self = obj; // circular reference

      // Test FormData with circular refs in the containing structure
      const data: any = { form: formData, circular: obj };
      data.backref = data; // circular reference to the container

      const serialized = stringify(data);
      const parsed = parse(serialized) as any;

      expect(parsed.form).toBeInstanceOf(FormData);
      expect(parsed.form.get("info")).toBe("test");
      expect(parsed.circular.name).toBe("test");
      expect(parsed.circular.self).toBe(parsed.circular);
      expect(parsed.backref).toBe(parsed);
    });
  });

  describe("round trip fidelity", () => {
    it("preserves all data types in complex structure", () => {
      const file = new File(["test content"], "document.pdf", {
        type: "application/pdf",
        lastModified: Date.now(),
      });

      const formData = new FormData();
      formData.append("title", "Test Form");
      formData.append("attachment", file);

      const date = new Date("2024-01-01T00:00:00Z");

      const complex: any = {
        id: 123,
        title: "Complex Data",
        created: date,
        updated: date, // shared reference
        tags: ["test", "example", "complex"],
        metadata: {
          form: formData,
          file: file, // shared reference
          nested: {
            deep: true,
            value: 42,
          },
        },
        empty: {
          obj: {},
          arr: [],
        },
      };

      // Add circular reference
      complex.self = complex;
      complex.metadata.parent = complex;

      const serialized = stringify(complex);
      const parsed = parse(serialized) as any;

      // Verify all data types and references
      expect(parsed.id).toBe(123);
      expect(parsed.title).toBe("Complex Data");
      expect(parsed.created).toBeInstanceOf(Date);
      expect(parsed.created).toBe(parsed.updated); // shared Date reference
      expect(parsed.tags).toEqual(["test", "example", "complex"]);

      // FormData
      expect(parsed.metadata.form).toBeInstanceOf(FormData);
      expect(parsed.metadata.form.get("title")).toBe("Test Form");
      expect(parsed.metadata.form.get("attachment")).toBeInstanceOf(File);

      // File reference
      expect(parsed.metadata.file).toBeInstanceOf(File);
      expect(parsed.metadata.file.name).toBe("document.pdf");
      expect(parsed.metadata.file.size).toBe(12);

      // Nested structure
      expect(parsed.metadata.nested.deep).toBe(true);
      expect(parsed.metadata.nested.value).toBe(42);

      // Empty containers
      expect(parsed.empty.obj).toEqual({});
      expect(parsed.empty.arr).toEqual([]);

      // Circular references
      expect(parsed.self).toBe(parsed);
      expect(parsed.metadata.parent).toBe(parsed);
    });
  });
});
