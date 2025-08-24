from pulse.javascript import compile_python_to_js


def test_simple_addition():
    def f(a, b):
        return a + b

    code, n_args, h = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return a + b;
}"""
    )
    assert n_args == 2
    assert len(h) == 16 and all(c in "0123456789abcdef" for c in h)


def test_constants_arithmetic_comparisons_boolean_ops():
    def f(x):
        return (x * 2 + 3) > 0 and not (x == 5)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return (x * 2 + 3 > 0) && !(x === 5);
}"""
    )


def test_unary_minus():
    def f(x):
        return -x

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return -x;
}"""
    )


def test_compare_chaining():
    def f(x):
        return 0 < x < 10

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return 0 < x && x < 10;
}"""
    )
