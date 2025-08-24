from pulse.javascript import compile_python_to_js


def test_if_else_statement():
    def f(x):
        if x > 0:
            return 1
        else:
            return 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
if (x > 0){
return 1;
} else {
return 2;
}
}"""
    )


def test_conditional_expression():
    def f(x):
        return 1 if x > 0 else 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x > 0 ? 1 : 2;
}"""
    )


def test_boolean_precedence_or():
    def f(a, b, c):
        return (a and b) or c

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b, c){
return a && b || c;
}"""
    )


def test_nested_ternary():
    def f(x):
        return 1 if x > 0 else 2 if x < -1 else 3

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x > 0 ? 1 : x < -1 ? 2 : 3;
}"""
    )
