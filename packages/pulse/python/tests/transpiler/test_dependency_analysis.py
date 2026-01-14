"""
Tests for dependency analysis in transpiled functions.

Focuses on:
- analyze_code_object: bytecode inspection for global vs attribute names
- analyze_deps: converting values to Expr dependencies
- Edge cases around closure variables, nested functions, and module imports
"""

# pyright: reportPrivateUsage=false
# pyright: reportUnusedVariable=false

import random as random_builtin

import pytest
from pulse.transpiler import (
	EXPR_REGISTRY,
	Identifier,
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
)
from pulse.transpiler.errors import TranspileError
from pulse.transpiler.function import (
	Constant,
	JsFunction,
	analyze_code_object,
	analyze_deps,
)


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()
	clear_import_registry()
	yield
	clear_function_cache()
	clear_import_registry()


# =============================================================================
# analyze_code_object: Bytecode analysis for global names
# =============================================================================


class TestAnalyzeCodeObject:
	"""Test analyze_code_object correctly distinguishes global vs attribute names."""

	def test_basic_global_reference(self):
		"""Global variable references are detected."""
		CONSTANT = 42

		def fn():
			return CONSTANT

		_, all_names = analyze_code_object(fn)
		assert "CONSTANT" in all_names

	def test_local_variable_not_in_names(self):
		"""Local variables are not included in global names."""

		def fn():
			local_var = 10
			return local_var

		_, all_names = analyze_code_object(fn)
		assert "local_var" not in all_names

	def test_parameter_not_in_names(self):
		"""Function parameters are not included in global names."""

		def fn(param):
			return param

		_, all_names = analyze_code_object(fn)
		assert "param" not in all_names

	def test_attribute_access_not_in_global_names(self):
		"""Attribute names (obj.attr) should NOT appear as global names."""

		class Obj:
			random = 42
			floor = 99

		obj = Obj()

		def fn():
			return obj.random + obj.floor

		_, all_names = analyze_code_object(fn)
		# 'obj' is the global, NOT 'random' or 'floor'
		assert "obj" in all_names
		assert "random" not in all_names
		assert "floor" not in all_names

	def test_method_call_attribute_not_in_global_names(self):
		"""Method names from calls (obj.method()) should NOT appear as global names."""

		class Api:
			def fetch(self):
				return "data"

		api = Api()

		def fn():
			return api.fetch()

		_, all_names = analyze_code_object(fn)
		assert "api" in all_names
		assert "fetch" not in all_names

	def test_chained_attribute_access(self):
		"""Chained attribute access (a.b.c) only detects the root as global."""

		class Inner:
			value = 1

		class Outer:
			inner = Inner()

		outer = Outer()

		def fn():
			return outer.inner.value

		_, all_names = analyze_code_object(fn)
		assert "outer" in all_names
		assert "inner" not in all_names
		assert "value" not in all_names

	def test_math_random_with_random_module_imported(self):
		"""The critical bug fix: Math.random should not pick up Python's random module.

		This is the specific issue that was fixed. When using Math.random() in a
		transpiled function, and the file also has `import random`, the old code
		would incorrectly see 'random' as a global reference.
		"""
		# Simulate the scenario from examples/channels.py
		Math = Identifier("Math")

		def fn():
			# This should only reference 'Math', not 'random'
			return Math.random()

		_, all_names = analyze_code_object(fn)
		assert "Math" in all_names
		# 'random' is an attribute access, NOT a global reference
		assert "random" not in all_names

	def test_multiple_attribute_accesses_same_name(self):
		"""Multiple objects with same attribute name don't leak attribute as global."""
		a = Identifier("a")
		b = Identifier("b")

		def fn():
			return a.value + b.value

		_, all_names = analyze_code_object(fn)
		assert "a" in all_names
		assert "b" in all_names
		assert "value" not in all_names

	def test_nested_function_globals(self):
		"""Global references in nested functions are collected."""
		OUTER_CONST = 1
		INNER_CONST = 2

		def fn():
			def nested():
				return INNER_CONST

			return OUTER_CONST + nested()

		_, all_names = analyze_code_object(fn)
		assert "OUTER_CONST" in all_names
		assert "INNER_CONST" in all_names

	def test_nested_function_attribute_not_global(self):
		"""Attribute accesses in nested functions are not treated as globals."""
		obj = Identifier("obj")

		def fn():
			def nested():
				return obj.attribute

			return nested()

		_, all_names = analyze_code_object(fn)
		assert "obj" in all_names
		assert "attribute" not in all_names

	def test_closure_variables_detected(self):
		"""Closure variables (freevars) are included in names."""

		def make_fn():
			captured = 42

			def fn():
				return captured

			return fn

		fn = make_fn()
		_, all_names = analyze_code_object(fn)
		assert "captured" in all_names

	def test_closure_with_attribute_access(self):
		"""Closure variable with attribute access: only variable is global."""

		def make_fn():
			captured = Identifier("captured")

			def fn():
				return captured.method()

			return fn

		fn = make_fn()
		_, all_names = analyze_code_object(fn)
		assert "captured" in all_names
		assert "method" not in all_names

	def test_builtin_names_detected(self):
		"""Builtin function calls are detected as names."""

		def fn(x):
			return len(x) + str(x)

		_, all_names = analyze_code_object(fn)
		assert "len" in all_names
		assert "str" in all_names

	def test_import_in_function_is_local(self):
		"""Imports inside functions are local bindings, not globals."""

		def fn():
			import json

			return json.dumps({})

		_, all_names = analyze_code_object(fn)
		# `import json` inside a function creates a LOCAL binding, not a global
		# The IMPORT_NAME opcode followed by STORE_FAST makes it local
		assert "json" not in all_names
		# 'dumps' is an attribute, not a global
		assert "dumps" not in all_names

	def test_global_store_detected(self):
		"""Global stores (assignment to globals) are detected."""

		def fn():
			global GLOBAL_VAR
			GLOBAL_VAR = 42

		_, all_names = analyze_code_object(fn)
		assert "GLOBAL_VAR" in all_names

	def test_delete_global_detected(self):
		"""Delete global statements are detected."""
		DELETABLE = 1  # noqa: F841

		def fn():
			global DELETABLE
			del DELETABLE

		_, all_names = analyze_code_object(fn)
		assert "DELETABLE" in all_names

	def test_lambda_inside_function(self):
		"""Lambda expressions in functions are analyzed."""
		LAMBDA_CONST = 10

		def fn():
			return (lambda x: x + LAMBDA_CONST)(5)

		_, all_names = analyze_code_object(fn)
		assert "LAMBDA_CONST" in all_names

	def test_comprehension_globals(self):
		"""List/dict/set comprehensions' globals are detected."""
		COMP_CONST = 2

		def fn():
			return [x * COMP_CONST for x in range(5)]

		_, all_names = analyze_code_object(fn)
		assert "COMP_CONST" in all_names
		assert "range" in all_names

	def test_generator_expression_globals(self):
		"""Generator expressions' globals are detected."""
		GEN_CONST = 3

		def fn():
			return sum(x * GEN_CONST for x in range(5))

		_, all_names = analyze_code_object(fn)
		assert "GEN_CONST" in all_names
		assert "sum" in all_names
		assert "range" in all_names


class TestAnalyzeCodeObjectEffectiveGlobals:
	"""Test that effective_globals correctly merges function globals with closure values."""

	def test_function_globals_available(self):
		"""Function's __globals__ values are available."""
		MODULE_LEVEL = "module"

		def fn():
			return MODULE_LEVEL

		effective_globals, _ = analyze_code_object(fn)
		assert "MODULE_LEVEL" in effective_globals
		assert effective_globals["MODULE_LEVEL"] == "module"

	def test_closure_values_resolved(self):
		"""Closure variable values are resolved from cells."""

		def make_fn():
			closed_over = "closure_value"

			def fn():
				return closed_over

			return fn

		fn = make_fn()
		effective_globals, _ = analyze_code_object(fn)
		assert "closed_over" in effective_globals
		assert effective_globals["closed_over"] == "closure_value"

	def test_closure_shadows_global(self):
		"""Closure variables shadow globals of the same name."""
		SHADOWED = "global"  # noqa: F841

		def make_fn():
			SHADOWED = "closure"  # noqa: F841

			def fn():
				return SHADOWED

			return fn

		fn = make_fn()
		effective_globals, _ = analyze_code_object(fn)
		# Closure value should be used, not global
		assert effective_globals["SHADOWED"] == "closure"

	def test_empty_closure_cell_skipped(self):
		"""Empty closure cells (unbound variables) are skipped."""

		def make_fn():
			# This creates a closure cell that may be empty in some edge cases
			def fn():
				pass

			return fn

		fn = make_fn()
		# Should not raise even with no freevars
		effective_globals, _ = analyze_code_object(fn)
		assert isinstance(effective_globals, dict)


# =============================================================================
# analyze_deps: Converting values to Expr dependencies
# =============================================================================


class TestAnalyzeDeps:
	"""Test analyze_deps correctly converts values to Expr dependencies."""

	def test_primitive_constants_inlined(self):
		"""Primitive constants (int, float, str, bool, None) are inlined as Expr."""
		INT_CONST = 42
		FLOAT_CONST = 3.14
		STR_CONST = "hello"
		BOOL_CONST = True
		NONE_CONST = None

		def fn():
			return (INT_CONST, FLOAT_CONST, STR_CONST, BOOL_CONST, NONE_CONST)

		deps = analyze_deps(fn)
		# All should be Expr, not Constant (hoisted)
		assert "INT_CONST" in deps
		assert not isinstance(deps["INT_CONST"], Constant)
		assert emit(deps["INT_CONST"]) == "42"

	def test_nonprimitive_constants_hoisted(self):
		"""Non-primitive constants (list, dict, set) are wrapped in Constant."""
		LIST_CONST = [1, 2, 3]
		DICT_CONST = {"a": 1}

		def fn():
			return (LIST_CONST, DICT_CONST)

		deps = analyze_deps(fn)
		assert isinstance(deps["LIST_CONST"], Constant)
		assert isinstance(deps["DICT_CONST"], Constant)

	def test_expr_values_passed_through(self):
		"""Existing Expr instances are passed through as-is."""
		expr = Identifier("existing")

		def fn():
			return expr

		deps = analyze_deps(fn)
		assert deps["expr"] is expr

	def test_function_dependencies(self):
		"""Plain Python functions are wrapped in JsFunction."""

		def helper():
			return 1

		def fn():
			return helper()

		deps = analyze_deps(fn)
		assert isinstance(deps["helper"], JsFunction)

	def test_jsfunction_cached(self):
		"""JsFunction dependencies are cached and reused."""

		@javascript
		def helper():
			return 1

		def fn():
			return helper()

		deps = analyze_deps(fn)
		assert deps["helper"] is helper

	def test_expr_registry_lookup(self):
		"""Values in EXPR_REGISTRY are looked up."""
		sentinel = object()
		sentinel_expr = Identifier("sentinel")
		EXPR_REGISTRY[id(sentinel)] = sentinel_expr

		try:

			def fn():
				return sentinel

			deps = analyze_deps(fn)
			assert deps["sentinel"] is sentinel_expr
		finally:
			del EXPR_REGISTRY[id(sentinel)]

	def test_module_without_registration_raises(self):
		"""Unregistered modules raise TranspileError."""
		import sys

		def fn():
			return sys.version

		with pytest.raises(TranspileError, match="Could not resolve module"):
			analyze_deps(fn)

	def test_callable_non_function_raises(self):
		"""Callable objects that aren't functions raise TranspileError."""

		class Callable:
			def __call__(self):
				return 1

		obj = Callable()

		def fn():
			return obj()

		with pytest.raises(TranspileError, match="not supported"):
			analyze_deps(fn)

	def test_expr_subclass_skipped(self):
		"""Expr subclasses (the classes themselves) are skipped."""
		from pulse.transpiler.nodes import Identifier

		def fn():
			# Type annotation or class reference
			x: Identifier = Identifier("x")
			return x

		# Should not raise
		deps = analyze_deps(fn)
		# Identifier class itself should not be in deps
		assert "Identifier" not in deps

	def test_inconvertible_value_raises(self):
		"""Values that can't be converted to Expr raise TranspileError."""

		class Custom:
			pass

		obj = Custom()

		def fn():
			return obj

		with pytest.raises(TranspileError, match="Cannot convert"):
			analyze_deps(fn)


# =============================================================================
# Integration: Math.random with random module scenario
# =============================================================================


class TestMathRandomScenario:
	"""Integration tests for the Math.random + random module scenario."""

	def test_math_random_transpiles_correctly(self):
		"""Math.random() transpiles without picking up Python's random module."""
		Math = Identifier("Math")

		@javascript
		def generate_id():
			return Math.random()

		# Should transpile successfully
		fn = generate_id.transpile()
		code = emit(fn)

		assert code == "function generate_id_1() {\nreturn Math.random();\n}"

	def test_math_random_with_random_import_in_scope(self):
		"""Even with random module in scope, Math.random works correctly."""
		# random_builtin is imported at module level
		Math = Identifier("Math")

		@javascript
		def fn():
			# This should work: Math.random() should not see Python's random
			return Math.random()

		# Should not raise about unregistered module
		fn.transpile()
		code = emit(fn.transpile())

		assert code == "function fn_1() {\nreturn Math.random();\n}"

	def test_actual_random_module_usage_raises(self):
		"""Actually using Python's random module raises (not registered)."""

		def fn():
			return random_builtin.randint(1, 10)

		with pytest.raises(TranspileError, match="Could not resolve module"):
			analyze_deps(fn)

	def test_attribute_with_same_name_as_module(self):
		"""Attribute access with same name as imported module works."""
		# This simulates: `import json` at module level, then `obj.json` access
		import json as json_builtin  # noqa: F401

		obj = Identifier("obj")

		@javascript
		def fn():
			return obj.json

		# 'json' should not be detected as a global (it's an attribute)
		fn.transpile()
		code = emit(fn.transpile())

		assert code == "function fn_1() {\nreturn obj.json;\n}"


# =============================================================================
# Edge cases and challenging scenarios
# =============================================================================


class TestEdgeCases:
	"""Test edge cases and challenging scenarios."""

	def test_deeply_nested_functions(self):
		"""Deeply nested functions correctly collect all globals."""
		LEVEL_0 = 0
		LEVEL_1 = 1
		LEVEL_2 = 2

		def fn():
			def level1():
				def level2():
					return LEVEL_2

				return LEVEL_1 + level2()

			return LEVEL_0 + level1()

		_, all_names = analyze_code_object(fn)
		assert "LEVEL_0" in all_names
		assert "LEVEL_1" in all_names
		assert "LEVEL_2" in all_names

	def test_mixed_closure_and_global(self):
		"""Mix of closure variables and globals works correctly."""
		GLOBAL = "global"

		def make_fn():
			closure = "closure"

			def fn():
				return GLOBAL + closure

			return fn

		fn = make_fn()
		effective_globals, all_names = analyze_code_object(fn)
		assert "GLOBAL" in all_names
		assert "closure" in all_names
		assert effective_globals["GLOBAL"] == "global"
		assert effective_globals["closure"] == "closure"

	def test_mutual_recursion_deps(self):
		"""Mutual recursion in dependencies is handled when both exist in scope."""
		# For mutual recursion to work, both functions must exist in the enclosing
		# scope BEFORE decoration. This simulates module-level mutual recursion.

		def fn_a():
			return fn_b()

		def fn_b():
			return fn_a()

		# Now wrap them - at this point both exist in scope
		js_a = JsFunction(fn_a)
		js_b = JsFunction(fn_b)

		# Both should have each other as deps
		assert "fn_b" in js_a.deps
		assert "fn_a" in js_b.deps

	def test_self_reference_in_function(self):
		"""Function referencing itself works when name exists in scope."""
		# Self-reference works at module level where the name exists in globals
		# before analyze_deps runs. Inside a test function, we need to simulate this.

		def factorial(n: int) -> int:
			if n <= 1:
				return 1
			return n * factorial(n - 1)

		# Wrap after definition - now 'factorial' exists in this scope
		js_factorial = JsFunction(factorial)

		assert "factorial" in js_factorial.deps
		assert js_factorial.deps["factorial"] is js_factorial

	def test_subscript_vs_attribute(self):
		"""Subscript access doesn't affect global detection."""
		obj = Identifier("obj")

		def fn():
			return obj["key"]

		_, all_names = analyze_code_object(fn)
		assert "obj" in all_names
		assert "key" not in all_names  # string literal, not a name

	def test_dynamic_attribute_via_getattr(self):
		"""getattr calls: the function name is global, not the attr string."""

		def fn():
			obj = {}
			return getattr(obj, "method")  # noqa: B009

		_, all_names = analyze_code_object(fn)
		assert "getattr" in all_names
		assert "method" not in all_names

	def test_walrus_operator(self):
		"""Walrus operator (:=) creates locals, not globals."""

		def fn():
			if (x := 10) > 5:
				return x
			return 0

		_, all_names = analyze_code_object(fn)
		assert "x" not in all_names

	def test_exception_variable(self):
		"""Exception variables in except clauses are local."""

		def fn():
			try:
				return 1
			except Exception as e:
				return e

		_, all_names = analyze_code_object(fn)
		assert "Exception" in all_names  # the class
		assert "e" not in all_names  # local binding

	def test_with_statement_variable(self):
		"""With statement target variables are local."""

		def fn():
			with open("file") as f:
				return f.read()

		_, all_names = analyze_code_object(fn)
		assert "open" in all_names
		assert "f" not in all_names
		assert "read" not in all_names  # attribute

	def test_for_loop_variable(self):
		"""For loop variables are local."""

		def fn():
			for i in range(10):  # noqa: B007
				pass
			return i

		_, all_names = analyze_code_object(fn)
		assert "range" in all_names
		assert "i" not in all_names

	def test_class_definition_inside_function(self):
		"""Class definitions inside functions: class body names are walked.

		Python class bodies have their own code objects which we walk into.
		Class body code uses STORE_NAME for class attributes and LOAD_NAME for
		special names like __name__, __qualname__, __module__.

		Note: This doesn't cause issues in practice because these names either:
		- Don't exist in the enclosing scope (so analyze_deps skips them), or
		- Are builtins handled separately by the transpiler
		"""

		def fn():
			class LocalClass:
				value = 1

			return LocalClass.value

		_, all_names = analyze_code_object(fn)
		# Class body internal names ARE collected (this is expected bytecode behavior)
		# These include __name__, __qualname__, __module__, and attribute names
		assert "__name__" in all_names or "__qualname__" in all_names
		# The class attribute 'value' is stored in the class body via STORE_NAME
		assert "value" in all_names
		# But 'LocalClass' is a local variable (STORE_FAST in the outer function)
		# so it won't appear as a global load
		assert "LocalClass" not in all_names

	def test_async_function_analysis(self):
		"""Async functions are analyzed correctly."""
		ASYNC_CONST = 42

		async def fn():
			return ASYNC_CONST

		_, all_names = analyze_code_object(fn)
		assert "ASYNC_CONST" in all_names

	def test_decorator_applied_to_inner_function(self):
		"""Decorator applied inside function: decorator is global, not decorated."""
		from pulse.transpiler import javascript

		def fn():
			@javascript
			def inner():
				return 1

			return inner

		_, all_names = analyze_code_object(fn)
		assert "javascript" in all_names
		assert "inner" not in all_names  # local

	def test_starred_expression(self):
		"""Starred expressions in function calls."""
		args = [1, 2, 3]

		def fn():
			return sum(*args)

		_, all_names = analyze_code_object(fn)
		assert "sum" in all_names
		assert "args" in all_names

	def test_double_starred_expression(self):
		"""Double-starred expressions in function calls."""
		kwargs = {"a": 1}

		def fn():
			return dict(**kwargs)

		_, all_names = analyze_code_object(fn)
		assert "dict" in all_names
		assert "kwargs" in all_names


class TestConstantDeduplication:
	"""Test that constants are properly deduplicated."""

	def test_same_list_shared(self):
		"""Same list object used in multiple functions is deduplicated."""
		SHARED = [1, 2, 3]

		@javascript
		def fn1():
			return SHARED[0]

		@javascript
		def fn2():
			return SHARED[1]

		# Both should reference the same Constant
		const1 = fn1.deps["SHARED"]
		const2 = fn2.deps["SHARED"]
		assert const1 is const2
		assert isinstance(const1, Constant)

	def test_equal_but_different_lists_not_shared(self):
		"""Equal but different list objects get different Constants."""
		LIST_A = [1, 2, 3]
		LIST_B = [1, 2, 3]  # Same content, different object

		@javascript
		def fn1():
			return LIST_A[0]

		@javascript
		def fn2():
			return LIST_B[0]

		const_a = fn1.deps["LIST_A"]
		const_b = fn2.deps["LIST_B"]
		# Different objects, different Constants
		assert const_a is not const_b


class TestAnalyzeDepsWithRegisteredModules:
	"""Test analyze_deps with properly registered modules."""

	def test_registered_module_resolves(self):
		"""Modules registered in EXPR_REGISTRY resolve correctly."""
		# Math from pulse.js is an Identifier registered in EXPR_REGISTRY
		from pulse.js import Math

		@javascript
		def fn():
			return Math.floor(3.7)

		# Should not raise
		fn.transpile()
		code = emit(fn.transpile())

		assert code == "function fn_1() {\nreturn Math.floor(3.7);\n}"

	def test_multiple_js_builtins(self):
		"""Multiple JS builtins work together."""
		from pulse.js import JSON, Math, console

		@javascript
		def fn():
			console.log(JSON.stringify(Math.random()))

		fn.transpile()
		code = emit(fn.transpile())

		assert (
			code
			== "function fn_1() {\nreturn console.log(JSON.stringify(Math.random()));\n}"
		)
