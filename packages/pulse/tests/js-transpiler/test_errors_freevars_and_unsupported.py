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
