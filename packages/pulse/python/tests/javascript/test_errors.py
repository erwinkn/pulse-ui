from pulse.javascript.transpiler import JSCompilationError, compile_python_to_js


def test_freevars_raise():
	y = 5

	def f(x):
		return x + y

	try:
		compile_python_to_js(f)
		raise AssertionError("Expected JSCompilationError for free variable")
	except JSCompilationError as e:
		assert "Unbound name" in str(e)


def test_unsupported_statement_augassign_op():
	def f(x):
		y = 1
		y //= x
		return y

	try:
		compile_python_to_js(f)
		raise AssertionError("Expected JSCompilationError for unsupported operator")
	except JSCompilationError as e:
		assert "operator" in str(e).lower()


def test_slice_step_error():
	def f(a):
		return a[::2]

	try:
		compile_python_to_js(f)
		raise AssertionError("Expected JSCompilationError for slice step")
	except JSCompilationError as e:
		assert "slice step" in str(e).lower()
