/* eslint-disable @typescript-eslint/no-explicit-any */

// https://github.com/WebReflection/flatted/blob/main/test/index.js
// (c) 2020-present Andrea Giammarchi
import { describe, it, expect, beforeEach } from "vitest";
import { parse, stringify, toJSON, fromJSON } from "./flatted";

describe("flatted", () => {
  it("handles multiple nulls", () => {
    expect(stringify([null, null])).toBe("[[null,null]]");
  });

  it("handles empty arrays and objects", () => {
    expect(stringify([])).toBe("[[]]");
    expect(stringify({})).toBe("[{}]");
  });

  it("handles recursive arrays and objects", () => {
    const a: any[] = [];
    a.push(a);
    expect(stringify(a)).toBe('[["0"]]');
    const o: any = {};
    o.o = o;
    expect(stringify(o)).toBe('[{"o":"0"}]');
  });

  it("restores recursive arrays", () => {
    const a: any[] = [];
    a.push(a);
    const b = parse(stringify(a));
    expect(Array.isArray(b) && b[0] === b).toBe(true);
  });

  it("handles values in arrays and objects", () => {
    const a: any[] = [];
    a.push(a, 1, "two", true);
    const o: any = {};
    o.o = o;
    o.one = 1;
    o.two = "two";
    o.three = true;

    expect(stringify(a)).toBe('[["0",1,"1",true],"two"]');
    expect(stringify(o)).toBe(
      '[{"o":"0","one":1,"two":"1","three":true},"two"]'
    );
  });

  it("handles objects in arrays and vice versa", () => {
    const a: any[] = [];
    a.push(a, 1, "two", true);
    const o: any = {};
    o.o = o;
    o.one = 1;
    o.two = "two";
    o.three = true;
    a.push(o);
    o.a = a;

    expect(stringify(a)).toBe(
      '[["0",1,"1",true,"2"],"two",{"o":"2","one":1,"two":"1","three":true,"a":"0"}]'
    );
    expect(stringify(o)).toBe(
      '[{"o":"0","one":1,"two":"1","three":true,"a":"2"},"two",["2",1,"1",true,"0"]]'
    );
  });

  it("handles complex nested objects and arrays", () => {
    const a: any[] = [];
    a.push(a, 1, "two", true);
    const o: any = {};
    o.o = o;
    o.one = 1;
    o.two = "two";
    o.three = true;
    a.push(o);
    o.a = a;
    a.push({ test: "OK" }, [1, 2, 3]);
    o.test = { test: "OK" };
    o.array = [1, 2, 3];

    expect(stringify(a)).toBe(
      '[["0",1,"1",true,"2","3","4"],"two",{"o":"2","one":1,"two":"1","three":true,"a":"0","test":"5","array":"6"},{"test":"7"},[1,2,3],{"test":"7"},[1,2,3],"OK"]'
    );
    expect(stringify(o)).toBe(
      '[{"o":"0","one":1,"two":"1","three":true,"a":"2","test":"3","array":"4"},"two",["2",1,"1",true,"0","5","6"],{"test":"7"},[1,2,3],{"test":"7"},[1,2,3],"OK"]'
    );
  });

  describe("parsing and verification", () => {
    let a: any, o: any;

    beforeEach(() => {
      const initialA: any[] = [];
      initialA.push(initialA, 1, "two", true);
      const initialO: any = {};
      initialO.o = initialO;
      initialO.one = 1;
      initialO.two = "two";
      initialO.three = true;
      initialA.push(initialO);
      initialO.a = initialA;
      initialA.push({ test: "OK" }, [1, 2, 3]);
      initialO.test = { test: "OK" };
      initialO.array = [1, 2, 3];

      a = parse(stringify(initialA));
      o = parse(stringify(initialO));
    });

    it("parses recursive structures correctly", () => {
      expect(a[0]).toBe(a);
      expect(o.o).toBe(o);
    });

    it("verifies array values", () => {
      expect(a[1]).toBe(1);
      expect(a[2]).toBe("two");
      expect(a[3]).toBe(true);
      expect(a[4]).toBeInstanceOf(Object);
      expect(JSON.stringify(a[5])).toBe(JSON.stringify({ test: "OK" }));
      expect(JSON.stringify(a[6])).toBe(JSON.stringify([1, 2, 3]));
      expect(a[4]).toBe(a[4].o);
      expect(a).toBe(a[4].o.a);
    });

    it("verifies object values", () => {
      expect(o.one).toBe(1);
      expect(o.two).toBe("two");
      expect(o.three).toBe(true);
      expect(Array.isArray(o.a)).toBe(true);
      expect(JSON.stringify(o.test)).toBe(JSON.stringify({ test: "OK" }));
      expect(JSON.stringify(o.array)).toBe(JSON.stringify([1, 2, 3]));
      expect(o.a).toBe(o.a[0]);
      expect(o).toBe(o.a[4]);
    });
  });

  describe("primitive types", () => {
    it("handles numbers", () => {
      expect(parse(stringify(1))).toBe(1);
    });
    it("handles booleans", () => {
      expect(parse(stringify(false))).toBe(false);
    });
    it("handles null", () => {
      expect(parse(stringify(null))).toBe(null);
    });
    it("handles strings", () => {
      expect(parse(stringify("test"))).toBe("test");
    });
  });

  describe("Date object serialization", () => {
    it.only("should serialize a Date object", () => {
      const date = new Date();
      const str = stringify({ date });
      console.log("JSON string:", str)
      const parsed = parse(str);
      expect(parsed.date).toBeInstanceOf(Date);
      expect(parsed.date.getTime()).toBe(date.getTime());
    });

    it("should serialize a standalone Date object", () => {
      const date = new Date();
      const str = stringify(date);
      const parsed = parse(str);
      expect(parsed).toBeInstanceOf(Date);
      expect(parsed.getTime()).toBe(date.getTime());
    });

    it("should serialize a Date object in an array", () => {
      const date = new Date();
      const str = stringify([date]);
      const parsed = parse(str);
      expect(parsed[0]).toBeInstanceOf(Date);
      expect(parsed[0].getTime()).toBe(date.getTime());
    });

    it("should handle multiple Date objects", () => {
      const date1 = new Date();
      const date2 = new Date(date1.getTime() + 1000);
      const str = stringify({ date1, date2 });
      const parsed = parse(str);
      expect(parsed.date1).toBeInstanceOf(Date);
      expect(parsed.date1.getTime()).toBe(date1.getTime());
      expect(parsed.date2).toBeInstanceOf(Date);
      expect(parsed.date2.getTime()).toBe(date2.getTime());
    });
  });

  describe("special characters", () => {
    it("handles ~", () => {
      const special = "\\x7e";
      expect(parse(stringify({ a: special })).a).toBe(special);
    });
    it("handles special char sequences", () => {
      const special = "~\\x7e";
      expect(parse(stringify({ a: special })).a).toBe(special);
    });
  });

  describe("JSON compatibility", () => {
    it("works like JSON.parse", () => {
      const o = { a: "a", b: "b", c: function () {}, d: { e: 123 } };
      const a = JSON.stringify(o);
      const b = stringify(o);
      expect(JSON.stringify(JSON.parse(a))).toBe(JSON.stringify(parse(b)));
    });
  });

  describe("replacer function", () => {
    it("accepts a replacer callback", () => {
      const o = { a: "a", b: "b", c: function () {}, d: { e: 123 } };
      expect(
        stringify(o, function (key, value) {
          if (!key || key === "a") return value;
        })
      ).toBe('[{"a":"1"},"a"]');
    });

    it("can whitelist properties with an array", () => {
      const o = { a: 1, b: { a: 1, b: 2 } };
      expect(stringify(o, ["b"])).toBe('[{"b":"1"},{"b":2}]');
    });
  });

  describe("reviver function", () => {
    it("accepts a reviver callback", () => {
      const parsed = parse('[{"a":"1"},"a"]', function (key, value) {
        if (key === "a") return "b";
        return value;
      });
      expect(JSON.stringify(parsed)).toBe('{"a":"b"}');
    });

    it("can be used to augment parsed objects", () => {
      let o: any = {};
      o.a = o;
      o.b = o;
      o = parse('[{"a":"0"}]', function (key, value) {
        if (!key) {
          value.b = value;
        }
        return value;
      });
      expect(o.a).toBe(o);
      expect(o.b).toBe(o);
    });
  });

  describe("complex recursive structures", () => {
    it("recreates original structure", () => {
      const o: any = {};
      o.a = o;
      o.c = {};
      o.d = {
        a: 123,
        b: o,
      };
      o.c.e = o;
      o.c.f = o.d;
      o.b = o.c;
      const before = stringify(o);
      const parsed = parse(before);

      expect(parsed.b).toBe(parsed.c);
      expect(parsed.c.e).toBe(parsed);
      expect(parsed.d.a).toBe(123);
      expect(parsed.d.b).toBe(parsed);
      expect(parsed.c.f).toBe(parsed.d);
    });

    it("handles tilde characters in keys and values", () => {
      let o: any = {};
      o["~"] = o;
      o["\\x7e"] = "\\x7e";
      o.test = "~";

      o = parse(stringify(o));
      expect(o["~"]).toBe(o);
      expect(o.test).toBe("~");

      let o2: any = {
        a: ["~", "~~", "~~~"],
      };
      o2.a.push(o2);
      o2.o = o2;
      o2["~"] = o2.a;
      o2["~~"] = o2.a;
      o2["~~~"] = o2.a;
      o2 = parse(stringify(o2));

      expect(o2).toBe(o2.a[3]);
      expect(o2).toBe(o2.o);
      expect(o2["~"]).toBe(o2.a);
      expect(o2["~~"]).toBe(o2.a);
      expect(o2["~~~"]).toBe(o2.a);
      expect(o2.a).toBe(o2.a[3].a);
      expect(o2.a.pop()).toBe(o2);
      expect(o2.a.join("")).toBe("~~~~~~");
    });
  });

  describe("prototype chain", () => {
    it("does not serialize inherited properties", () => {
      (Object.prototype as any).shenanigans = true;
      const item: any = {
        name: "TEST",
      };
      const original = {
        outer: [
          {
            a: "b",
            c: "d",
            one: item,
            many: [item],
            e: "f",
          },
        ],
      };
      item.value = item;
      const str = stringify(original);
      const output = parse(str);
      expect(str).toBe(
        '[{"outer":"1"},["2"],{"a":"3","c":"4","one":"5","many":"6","e":"7"},"b","d",{"name":"8","value":"5"},["5"],"f","TEST"]'
      );
      expect(original.outer[0].one.name).toBe(output.outer[0].one.name);
      expect(original.outer[0].many[0].name).toBe(output.outer[0].many[0].name);
      expect(output.outer[0].many[0]).toBe(output.outer[0].one);
      delete (Object.prototype as any).shenanigans;
    });
  });

  describe("deeply nested objects", () => {
    it("handles very nested structures", () => {
      const unique = { a: "sup" };
      const nested = {
        prop: {
          value: 123,
        },
        a: [
          {},
          {
            b: [
              {
                a: 1,
                d: 2,
                c: unique,
                z: {
                  g: 2,
                  a: unique,
                  b: {
                    r: 4,
                    u: unique,
                    c: 5,
                  },
                  f: 6,
                },
                h: 1,
              },
            ],
          },
        ],
        b: {
          e: "f",
          t: unique,
          p: 4,
        },
      };
      const str = stringify(nested);
      expect(str).toBe(
        '[{"prop":"1","a":"2","b":"3"},{"value":123},["4","5"],{"e":"6","t":"7","p":4},{},{"b":"8"},"f",{"a":"9"},["10"],"sup",{"a":1,"d":2,"c":"7","z":"11","h":1},{"g":2,"a":"7","b":"12","f":6},{"r":4,"u":"7","c":5}]'
      );
      const output = parse(str);
      expect(output.b.t.a).toBe("sup");
      expect(output.a[1].b[0].c).toBe(output.b.t);
    });
  });

  describe("empty keys", () => {
    it("handles empty keys as non-root objects", () => {
      const a: any = { b: { "": { c: { d: 1 } } } };
      a._circular = a.b[""];
      const json = stringify(a);
      const nosj = parse(json);
      expect(nosj._circular).toBe(nosj.b[""]);
      expect(JSON.stringify(nosj._circular)).toBe(JSON.stringify(a._circular));
      delete a._circular;
      delete nosj._circular;
      expect(JSON.stringify(nosj)).toBe(JSON.stringify(a));
    });
  });

  if (typeof Symbol !== "undefined") {
    describe("Symbol properties", () => {
      it("are ignored like JSON.stringify", () => {
        const o: any = { a: 1 };
        const a = [1, Symbol("test"), 2];
        o[Symbol("test")] = 123;
        expect("[" + JSON.stringify(o) + "]").toBe(stringify(o));
        expect("[" + JSON.stringify(a) + "]").toBe(stringify(a));
      });
    });
  }

  describe("extra arguments", () => {
    it("handles extra arguments like JSON.stringify", () => {
      const args: any = [{ a: [1] }, null, "  "];
      expect(stringify.apply(null, args)).toBe('[{\n  "a": "1"\n},[\n  1\n]]');
    });
  });

  describe("custom toJSON/fromJSON", () => {
    class RecursiveMap extends Map {
      static fromJSON(any: any) {
        return new this(fromJSON(any));
      }
      toJSON() {
        return toJSON([...this.entries()]);
      }
    }
    it("works with custom toJSON", () => {
      const jsonMap = new RecursiveMap([["test", "value"]]);
      const asJSON = JSON.stringify(jsonMap);
      const expected = '[["1"],["2","3"],"test","value"]';
      expect(asJSON).toBe(expected);
    });
    it("works with custom fromJSON", () => {
      const jsonMap = new RecursiveMap([["test", "value"]]);
      const asJSON = JSON.stringify(jsonMap);
      const revived = RecursiveMap.fromJSON(JSON.parse(asJSON));
      expect(revived.get("test")).toBe("value");
    });
    it("handles recursive custom Maps", () => {
      const recursive = new RecursiveMap();
      const same: any = {};
      same.same = same;
      recursive.set("same", same);
      const asString = JSON.stringify(recursive);
      const asMap = RecursiveMap.fromJSON(JSON.parse(asString));
      expect(asMap.get("same").same).toBe(asMap.get("same"));
    });
  });
});
