from pulse.javascript.transpiler import compile_python_to_js


def test_subscript_access():
    def f(arr):
        return arr[0]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(arr){
return arr[0];
}"""
    )


def test_list_comprehension_map():
    def f(xs):
        return [x + 1 for x in xs]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.map(x => x + 1);
}"""
    )


def test_list_literal():
    def f():
        return [1, 2, 3]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(){
return [1, 2, 3];
}"""
    )


def test_tuple_literal_emits_array():
    def f(x):
        return (1, x)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return [1, x];
}"""
    )


def test_singleton_tuple_emits_array():
    def f(x):
        return (x,)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return [x];
}"""
    )


def test_list_literal_with_spread():
    def f(a):
        return [1, *a, 3]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return [1, ...a, 3];
}"""
    )


def test_tuple_spread_mixed_sources():
    def f(a, b):
        return (*a, 2, *b)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return [...a, 2, ...b];
}"""
    )


def test_list_index():
    def f(xs):
        return xs.index(3)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? xs.indexOf(3) : xs.index(3);
}"""
    )


def test_list_count():
    def f(xs):
        return xs.count(1)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? xs.filter(v => v === 1).length : xs.count(1);
}"""
    )


def test_copy():
    def f(xs):
        return xs.copy()

    code, _, _ = compile_python_to_js(f)
    print(code)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? xs.slice() : xs instanceof Map ? new Map(xs.entries()) : xs.copy();
}"""
    )


def test_append():
    # Append should be mapped to push and return None
    def f(xs):
        return xs.append(1)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? (xs.push(1), undefined) : xs.append(1);
}"""
    )


def test_list_sort_mutates_and_returns_none():
    def f(xs):
        return xs.sort()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? (xs.sort(), undefined) : xs.sort();
}"""
    )


def test_list_reverse_mutates_and_returns_none():
    def f(xs):
        return xs.reverse()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? (xs.reverse(), undefined) : xs.reverse();
}"""
    )


def test_pop_noarg():
    def f(xs):
        return xs.pop()

    code, _, _ = compile_python_to_js(f)
    print(code)
    assert code == (
        """function(xs){
return xs instanceof Set ? (() => {
const $it = xs.values();
const $r = $it.next();
if (!$r.done){
const $v = $r.value;
xs.delete($v);
return $v;
}
})() : xs.pop();
}"""
    )


def test_pop_index():
    def f(xs):
        return xs.pop(2)

    code, _, _ = compile_python_to_js(f)
    print("Code:\n", code)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? xs.splice(2, 1)[0] : xs instanceof Map ? (() => {
if (xs.has(2)){
const $v = xs.get(2);
xs.delete(2);
return $v;
} else {
return undefined;
}
})() : xs.pop(2);
}"""
    )


def test_in_list():
    def f(a):
        return 2 in a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return Array.isArray(a) || typeof a === "string" ? a.includes(2) : a instanceof Set || a instanceof Map ? a.has(2) : 2 in a;
}"""
    )


def test_not_in_list():
    def f(a):
        return 2 not in a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return !(Array.isArray(a) || typeof a === "string" ? a.includes(2) : a instanceof Set || a instanceof Map ? a.has(2) : 2 in a);
}"""
    )


def test_slice_range():
    def f(a):
        return a[1:3]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.slice(1, 3);
}"""
    )


def test_slice_prefix():
    def f(a):
        return a[:2]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.slice(0, 2);
}"""
    )


def test_slice_suffix():
    def f(a):
        return a[2:]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.slice(2);
}"""
    )


def test_slice_negative_suffix():
    def f(a):
        return a[-2:]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.slice(-2);
}"""
    )


def test_slice_negative_prefix():
    def f(a):
        return a[:-1]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.slice(0, -1);
}"""
    )


def test_index_negative_one():
    def f(a):
        return a[-1]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.at(-1);
}"""
    )


def test_index_negative_variable_uses_at():
    def f(a, i):
        return a[-i]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, i){
return a.at(-i);
}"""
    )


def test_any_over_iterable():
    def f(xs):
        return any(xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.some(v => v);
}"""
    )


def test_all_over_iterable():
    def f(xs):
        return all(xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.every(v => v);
}"""
    )


def test_any_with_predicate():
    def f(xs):
        return any(x > 0 for x in xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.some(x => x > 0);
}"""
    )


def test_all_with_predicate():
    def f(xs):
        return all(x > 0 for x in xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.every(x => x > 0);
}"""
    )


def test_sum_simple():
    def f(xs):
        return sum(xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.reduce((a, b) => a + b, 0);
}"""
    )


def test_sum_comprehension_filter_map():
    def f(xs):
        return sum(x + 1 for x in xs if x > 0)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.filter(x => x > 0).map(x => x + 1).reduce((a, b) => a + b, 0);
}"""
    )


def test_list_literal_method_simplification():
    def f():
        return [1, 2, 3].index(2)

    code, _, _ = compile_python_to_js(f)
    # Normally this would get transpiled to something with an `Array.isArray` check. However, in this case, t
    assert code == (
        """function(){
return [1, 2, 3].indexOf(2);
}"""
    )
