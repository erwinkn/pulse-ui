from pulse.javascript import compile_python_to_js


def test_keys():
    def f(d):
        return list(d.keys())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Object.keys(d);
}"""
    )


def test_values():
    def f(d):
        return list(d.values())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Object.values(d);
}"""
    )


def test_items():
    def f(d):
        return list(d.items())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Object.entries(d);
}"""
    )
