from pulse.javascript import compile_python_to_js, JSCompilationError


def test_freevars_raise():
    y = 5

    def f(x):
        return x + y

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for free variable"
    except JSCompilationError as e:
        assert "free variables" in str(e)


def test_unsupported_statement_for_loop():
    def f(xs):
        s = 0
        for i in xs:
            s = s + i
        return s

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for unsupported statement"
    except JSCompilationError as e:
        assert "Unsupported statement" in str(e)


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
