from pulse.javascript import compile_python_to_js


def test_list_comprehension_map():
    def f(xs):
        return [x + 1 for x in xs]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.map(x => x + 1);
}"""
    )


def test_dict_comprehension_simple():
    def f(xs):
        return {x: x + 1 for x in xs}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Object.fromEntries(xs.map(x => [String(x), x + 1]));
}"""
    )


def test_dict_comprehension_filter():
    def f(pairs):
        return {k: v for (k, v) in pairs if v > 0}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(pairs){
return Object.fromEntries(pairs.filter(([k, v]) => (v > 0)).map(([k, v]) => [String(k), v]));
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
