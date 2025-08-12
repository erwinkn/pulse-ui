/* eslint-disable @typescript-eslint/no-explicit-any */
// Adapted from: https://github.com/WebReflection/flatted/blob/main/esm/index.js
// (c) 2020-present Andrea Giammarchi

const { parse: $parse, stringify: $stringify } = JSON;
const { keys } = Object;

const Primitive = String; // it could be Number
const primitive = "string"; // it could be 'number'

const ignore = {};
const object = "object";

const noop = (_: any, value: any): any => value;

const primitives = (value: any): any =>
  value instanceof Primitive ? Primitive(value) : value;

const Primitives = (_: any, value: any): any => {
  if (
    typeof value === "object" &&
    value !== null &&
    value.__type__ === "Date" &&
    typeof value.value === "string"
  ) {
    return new Date(value.value);
  }
  return typeof value === primitive ? new Primitive(value) : value;
};

type Reviver = (this: any, key: string, value: any) => any;

const revive = (
  input: any[],
  parsed: Set<any>,
  output: { [key: string]: any },
  $: Reviver
): any => {
  const lazy: {
    k: string;
    a: [any[], Set<any>, any, Reviver];
  }[] = [];
  for (let ke = keys(output), { length } = ke, y = 0; y < length; y++) {
    const k = ke[y];
    const value = output[k];
    if (value instanceof Primitive) {
      const tmp = input[value as any]; // Q: is value a string or a number here?
      if (typeof tmp === object && !parsed.has(tmp)) {
        parsed.add(tmp);
        output[k] = ignore;
        lazy.push({ k, a: [input, parsed, tmp, $] });
      } else output[k] = $.call(output, k, tmp);
    } else if (output[k] !== ignore) output[k] = $.call(output, k, value);
  }
  for (let { length } = lazy, i = 0; i < length; i++) {
    const { k, a } = lazy[i];
    output[k] = $.call(output, k, revive.apply(null, a));
  }
  return output;
};

const set = (known: Map<any, string>, input: any[], value: any): string => {
  const index = Primitive(input.push(value) - 1);
  known.set(value, index);
  return index;
};

/**
 * Converts a specialized flatted string into a JS value.
 * @param {string} text
 * @param {(this: any, key: string, value: any) => any} [reviver]
 * @returns {any}
 */
export const parse = (text: string, reviver?: Reviver): any => {
  const input = $parse(text, Primitives).map(primitives);
  const value = input[0];
  const $ = reviver || noop;
  const tmp =
    typeof value === object && value
      ? revive(input, new Set(), value, $)
      : value;
  return $.call({ "": tmp }, "", tmp);
};

type Replacer =
  | ((this: any, key: string, value: any) => any)
  | (string | number)[];

/**
 * Converts a JS value into a specialized flatted string.
 * @param {any} value
 * @param {((this: any, key: string, value: any) => any) | (string | number)[] | null | undefined} [replacer]
 * @param {string | number | undefined} [space]
 * @returns {string}
 */
export const stringify = (
  value: any,
  replacer?: Replacer | null,
  space?: string | number
): string => {
  const $ =
    replacer && Array.isArray(replacer)
      ? (k: string, v: any) =>
          k === "" || -1 < replacer.indexOf(k) ? v : void 0
      : replacer || noop;
  const known = new Map();
  const input: any[] = [];
  const output: string[] = [];
  let i = +set(known, input, $.call({ "": value }, "", value));
  let firstRun = !i;
  while (i < input.length) {
    firstRun = true;
    output[i] = $stringify(input[i++], replace, space);
  }
  return "[" + output.join(",") + "]";
  function replace(this: any, key: string, value: any) {
    if (firstRun) {
      firstRun = !firstRun;
      return value;
    }
    const after = $.call(this, key, value);
    // console.log(`After. ${key}=`)
    // if (after instanceof Date) {
    //   return { __type__: "Date", value: after.toISOString() };
    // }
    switch (typeof after) {
      case object:
        if (after === null) return after;
      // eslint-disable-next-line no-fallthrough
      case primitive:
        return known.get(after) || set(known, input, after);
    }
    return after;
  }
};

/**
 * Converts a generic value into a JSON serializable object without losing recursion.
 * @param {any} value
 * @returns {any}
 */
export const toJSON = (value: any): any => $parse(stringify(value));

/**
 * Converts a previously serialized object with recursion into a recursive one.
 * @param {any} value
 * @returns {any}
 */
export const fromJSON = (value: any): any => parse($stringify(value));
