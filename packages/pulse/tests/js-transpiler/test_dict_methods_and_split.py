from pulse.javascript import compile_python_to_js


def test_dict_get_with_default():
    def f(d):
        return d.get("x", 0)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d["x"] ?? 0;
}"""
    )


def test_dict_get_without_default():
    def f(d):
        return d.get("y")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d["y"] ?? null;
}"""
    )


def test_string_split():
    def f(s):
        return s.split(",")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.split(`,`);
}"""
    )
