import inspect


def test_constant_string_escapes_control_chars():
	def f():
		return "a\nb\rc\t\b\f\v"

	print(inspect.getsource(f))


test_constant_string_escapes_control_chars()
