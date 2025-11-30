import shutil
import subprocess
import sys
from textwrap import dedent

import pytest
from pulse.javascript.function import JsFunction
from pulse.javascript.nodes import JSCompilationError


def test_transpile_single_function():
	def inc(x):
		return x + 1

	jf = JsFunction(inc)
	code = jf.emit().code.strip()
	# Basic shape checks: now emitted as named function declaration
	assert code.startswith("function ")
	assert "return" in code
	assert "+ 1" in code


def test_transpile_same_file_dependency(tmp_path, monkeypatch):
	# Create a temp module that defines both helper and f in the same file
	mod_path = tmp_path / "m_same.py"
	mod_path.write_text(
		dedent(
			"""
            def helper(y):
                return y * 2

            def f(x):
                return helper(x)
            """
		)
	)
	monkeypatch.syspath_prepend(str(tmp_path))
	from m_same import f  # type: ignore

	jf = JsFunction(f)
	code = jf.emit().code
	# Emits dependency as named function and body refers to allocated name (may be suffixed)
	assert "function helper" in code
	assert "function f" in code
	assert "return helper" in code


def test_transpile_cross_module_dependency(tmp_path, monkeypatch):
	# Create a temp module with a pure Python function
	mod_path = tmp_path / "mymod.py"
	mod_path.write_text(
		dedent(
			"""
            def g(z):
                return z - 3
            """
		)
	)

	sys_path_orig = list(sys.path)
	monkeypatch.syspath_prepend(str(tmp_path))

	# Import and expose as module-global name 'g'
	from mymod import g as g_imported  # type: ignore

	global g
	prev = globals().get("g", None)
	g = g_imported
	try:

		def f(x):
			return g(x)

		jf = JsFunction(f)
	finally:
		if prev is None:
			del globals()["g"]
		else:
			g = prev  # restore
	code = jf.emit().code
	# Emits dependency as named function and body refers to allocated name (may be suffixed)
	assert "function g" in code
	assert "function f" in code
	assert "return g" in code

	# Clean up path to avoid test pollution
	sys.path[:] = sys_path_orig


def test_transpile_with_deps_and_constants(tmp_path, monkeypatch):
	# Create a temp module that defines constants, helper, and f
	mod_path = tmp_path / "m_consts.py"
	mod_path.write_text(
		dedent(
			"""
            A_NUM = 42
            A_STR = "hi"
            A_LIST = [1, 2, 3]
            A_TUP = (4, 5)
            A_DICT = {"a": 1, "b": 2}
            A_SET = {7, 8}

            def helper(y):
                return y + 1

            def f(x):
                return helper(x) + A_NUM + len(A_LIST) + (A_DICT.get("a") or 0)
            """
		)
	)
	monkeypatch.syspath_prepend(str(tmp_path))
	from m_consts import f  # type: ignore

	jf = JsFunction(f)
	code = jf.emit().code
	# Dependency and constants should be emitted
	assert "function helper" in code
	assert "const A_NUM = 42" in code
	assert "const A_LIST = [1, 2, 3]" in code
	assert "const A_DICT = new Map(" in code
	# We don't assert set order, but ensure Set emission exists if used in future
	# assert "new Set(" in code  # not referenced in f, so not emitted
	# Function body should reference allocated helper name
	assert "return helper" in code


def test_complex_graph_across_modules(tmp_path, monkeypatch):
	# Module A: helper uses a module-level C and shadows builtin len
	(tmp_path / "mod_a.py").write_text(
		dedent(
			"""
            C = 10

            def len(x):
                return 999

            def helper(v):
                return len([1, 2]) + v + C
            """
		)
	)

	# Module B: helper uses its own C with the same name but different value
	(tmp_path / "mod_b.py").write_text(
		dedent(
			"""
            C = 20

            def helper(v):
                return v * C
            """
		)
	)

	# Module C: composes both helpers across files
	(tmp_path / "mod_c.py").write_text(
		dedent(
			"""
            from mod_a import helper as a_helper
            from mod_b import helper as b_helper

            def f(xs):
                total = 0
                for x in xs:
                    total = total + a_helper(x) + b_helper(x)
                return total
            """
		)
	)

	monkeypatch.syspath_prepend(str(tmp_path))
	from mod_c import f  # type: ignore

	jf = JsFunction(f)
	code = jf.emit().code

	# Two helpers emitted with allocated names, plus shadowing len from mod_a
	assert code.count("function helper") >= 2
	assert "function len" in code

	# Conflicting constants named C should be emitted once per unique value
	assert "const C = 10" in code
	# Another C with different value gets suffixed name (e.g., C2)
	assert "const C2 = 20" in code or "const C3 = 20" in code

	# Root function present and calls helpers via allocated names
	assert "function f" in code
	assert "a_helper(" not in code and "b_helper(" not in code
	assert "helper" in code

	# Optional: execute with Bun if available and verify runtime result
	bun = shutil.which("bun")
	if bun is None:
		return
	run_js = tmp_path / "run.js"
	run_js.write_text(code + f"\nconsole.log({jf.js_name}([1,2,3]));\n")
	res = subprocess.run([bun, str(run_js)], capture_output=True, text=True)
	assert res.returncode == 0
	# Expected: sum over x in [1,2,3] of (999 + x + 10) + (x * 20) = 3153
	last_line = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
	assert last_line == "3153"


def test_unknown_name_errors(tmp_path, monkeypatch):
	mod_path = tmp_path / "m_unknown.py"
	mod_path.write_text(
		dedent(
			"""
            def f(x):
                return not_defined + x
            """
		)
	)
	monkeypatch.syspath_prepend(str(tmp_path))
	from m_unknown import f  # type: ignore

	with pytest.raises(JSCompilationError):
		JsFunction(f).emit()


def test_unknown_function_call_errors(tmp_path, monkeypatch):
	# Calling an undefined function should error
	mod_path = tmp_path / "m_unknown_fn.py"
	mod_path.write_text(
		dedent(
			"""
            def f(x):
                return missing_fn(x)
            """
		)
	)
	monkeypatch.syspath_prepend(str(tmp_path))
	from m_unknown_fn import f  # type: ignore

	with pytest.raises(JSCompilationError):
		JsFunction(f).emit()


def test_unknown_method_call_errors(tmp_path, monkeypatch):
	# Calling a method on an undefined object should error at object reference
	mod_path = tmp_path / "m_unknown_method.py"
	mod_path.write_text(
		dedent(
			"""
            def f(x):
                return missing_obj.do(x)
            """
		)
	)
	monkeypatch.syspath_prepend(str(tmp_path))
	from m_unknown_method import f  # type: ignore

	with pytest.raises(JSCompilationError):
		JsFunction(f).emit()


def test_unknown_attribute_access_errors(tmp_path, monkeypatch):
	# Attribute access on an undefined object should error at object reference
	mod_path = tmp_path / "m_unknown_attr.py"
	mod_path.write_text(
		dedent(
			"""
            def f(x):
                return missing_obj.attr
            """
		)
	)
	monkeypatch.syspath_prepend(str(tmp_path))
	from m_unknown_attr import f  # type: ignore

	with pytest.raises(JSCompilationError):
		JsFunction(f).emit()
