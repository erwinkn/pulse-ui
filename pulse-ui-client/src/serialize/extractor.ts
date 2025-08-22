
type Simplify<T> = { [K in keyof T]: T[K] } & {};

export function createExtractor<T extends object>() {
  function _createExtractor<
    const K extends readonly (keyof T)[],
    C extends Partial<Record<K[number] | string, (src: T) => any>>,
  >(keys: K, computed?: C) {
    return (
      src: T
    ): Simplify<
      Pick<T, K[number]> & {
        [P in keyof C]-?: C[P] extends (...args: any) => infer R ? R : never;
      }
    > => {
      const out: any = {};
      for (const key of keys) {
        out[key as string] = (src as any)[key as string];
      }
      if (computed) {
        for (const key in computed) {
          const fn = computed[key]!;
          out[key] = fn(src);
        }
      }
      return out;
    };
  }
  return _createExtractor;
}