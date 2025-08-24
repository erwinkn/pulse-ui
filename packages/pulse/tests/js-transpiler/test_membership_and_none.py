from pulse.javascript import compile_python_to_js


def test_is_none():
    def f(x):
        return x is None

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x === null;
}"""
    )


def test_is_not_none():
    def f(x):
        return x is not None

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x !== null;
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


def test_membership_in_string():
    def f(s):
        return "x" in s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.includes(`x`);
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
