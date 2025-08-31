from pulse.javascript.transpiler import compile_python_to_js


def test_attribute_access():
    def f(obj):
        return obj.value

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(obj){
return obj.value;
}"""
    )
