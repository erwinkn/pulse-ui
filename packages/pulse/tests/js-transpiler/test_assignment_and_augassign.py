from pulse.javascript import compile_python_to_js


def test_assign_and_return():
    def f(x):
        y = x + 1
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = x + 1;
return y;
}"""
    )


def test_annassign_and_return():
    def f(x: int):
        y: int = x
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = x;
return y;
}"""
    )


def test_reassignment_without_let():
    def f(x):
        y = x + 1
        y = y + 2
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = x + 1;
y = y + 2;
return y;
}"""
    )


def test_param_reassignment():
    def f(x):
        x = x + 1
        return x

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
x = x + 1;
return x;
}"""
    )


def test_augassign():
    def f(x):
        y = 1
        y += x
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = 1;
y += x;
return y;
}"""
    )
