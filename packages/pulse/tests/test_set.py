from pulse.javascript.transpiler import compile_python_to_js


def test_set_comprehension_simple():
    def f(xs):
        return {x + 1 for x in xs if x > 0}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return new Set(xs.filter(x => x > 0).map(x => x + 1));
}"""
    )
