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


def test_membership_in_list():
    def f(a):
        return 2 in a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.includes(2);
}"""
    )


def test_not_in_list():
    def f(a):
        return 3 not in a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return !a.includes(3);
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