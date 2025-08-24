from pulse.javascript import compile_python_to_js


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
