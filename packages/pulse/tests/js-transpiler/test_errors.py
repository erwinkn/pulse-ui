from pulse.javascript.transpiler import compile_python_to_js, JSCompilationError


def test_freevars_raise():
    y = 5

    def f(x):
        return x + y

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for free variable"
    except JSCompilationError as e:
        assert "free variables" in str(e)


def test_unsupported_statement_augassign_op():
    def f(x):
        y = 1
        y //= x
        return y

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for unsupported operator"
    except JSCompilationError as e:
        assert "operator" in str(e).lower()


def test_slice_step_error():
    def f(a):
        return a[::2]

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for slice step"
    except JSCompilationError as e:
        assert "slice step" in str(e).lower()
