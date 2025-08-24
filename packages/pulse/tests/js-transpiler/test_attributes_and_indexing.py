from pulse.javascript import compile_python_to_js


def test_attribute_access():
    def f(obj):
        return obj.value

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(obj){
return obj.value;
}"""
    )


def test_subscript_access():
    def f(arr):
        return arr[0]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(arr){
return arr[0];
}"""
    )
