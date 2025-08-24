from pulse.javascript import compile_python_to_js, JSCompilationError


def test_list_literal():
    def f():
        return [1, 2, 3]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(){
return [1, 2, 3];
}"""
    )


def test_tuple_literal_emits_array():
    def f(x):
        return (1, x)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return [1, x];
}"""
    )


def test_singleton_tuple_emits_array():
    def f(x):
        return (x,)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return [x];
}"""
    )


def test_dict_literal():
    def f(x):
        return {"a": 1, "b": x}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return {"a": 1, "b": x};
}"""
    )


def test_string_join():
    def f(xs):
        return ",".join(xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.join(`,`);
}"""
    )


def test_slice_step_error():
    def f(a):
        return a[::2]

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for slice step"
    except JSCompilationError as e:
        assert "slice step" in str(e).lower()


def test_non_string_dict_key_error():
    def f(x):
        return {x: 1}

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for non-string dict key"
    except JSCompilationError as e:
        assert "dict keys" in str(e)
