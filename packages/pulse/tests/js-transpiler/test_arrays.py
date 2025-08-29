from pulse.javascript import compile_python_to_js


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
return xs.indexOf(3);
}"""
    )


def test_list_count():
    def f(xs):
        return xs.count(1)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.filter(v => v === 1).length;
}"""
    )


def test_list_copy():
    def f(xs):
        return xs.copy()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Array.isArray(xs) ? xs.slice() : {...xs};
}"""
    )


def test_list_append_emits_push_and_returns_none():
    def f(xs):
        return xs.append(1)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return (() => {if (Array.isArray(xs)) { xs.push(1); return; } if (xs && typeof xs.append === "function") { return xs.append(1); } return; })();
}"""
    )


def test_list_sort_mutates_and_returns_none():
    def f(xs):
        return xs.sort()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return (xs.sort(), undefined);
}"""
    )


def test_list_reverse_mutates_and_returns_none():
    def f(xs):
        return xs.reverse()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return (xs.reverse(), undefined);
}"""
    )


def test_list_pop_noarg():
    def f(xs):
        return xs.pop()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.pop();
}"""
    )


def test_list_pop_index():
    def f(xs):
        return xs.pop(2)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return (() => {const __k=2; if (Array.isArray(xs)) { return xs.splice(__k, 1)[0]; } if (xs && typeof xs === "object") { if (Object.hasOwn(xs, __k)) { const __v = xs[__k]; delete xs[__k]; return __v; } } return xs.pop(__k); })();
}"""
    )


def test_dict_pop():
    def f(d: dict):
        return d.pop("aa")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return (() => {const __k="aa"; if (Object.hasOwn(d, __k)) { const __v = d[__k]; delete d[__k]; return __v; } })();
}"""
    )


def test_membership_in_list():
    def f(a):
        return 2 in a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return ((Array.isArray(a) || typeof a === "string") ? a.includes(2) : (a && typeof a === "object" && Object.hasOwn(a, String(2))));
}"""
    )


def test_not_in_list():
    def f(a):
        return 3 not in a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return !((Array.isArray(a) || typeof a === "string") ? a.includes(3) : (a && typeof a === "object" && Object.hasOwn(a, String(3))));
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
