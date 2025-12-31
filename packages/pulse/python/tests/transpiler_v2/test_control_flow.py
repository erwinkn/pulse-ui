"""
Tests for control flow transpilation: if/else, loops, assignments, etc.
"""

# pyright: reportPrivateUsage=false

from collections.abc import Iterable
from typing import Any

import pytest
from pulse.transpiler_v2 import (
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
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
# Multi-Statement Functions
# =============================================================================


class TestMultiStatement:
	"""Test multi-statement function transpilation."""

	def test_if_else_statement(self):
		@javascript
		def abs_val(x: int | float) -> int | float:
			if x < 0:
				return -x
			else:
				return x

		fn = abs_val.transpile()
		code = emit(fn)
		assert (
			code
			== "function abs_val_1(x) {\nif (x < 0) {\nreturn -x;\n} else {\nreturn x;\n}\n}"
		)

	def test_variable_assignment(self):
		@javascript
		def swap(x: Any, y: Any) -> list[Any]:
			temp = x
			x = y
			y = temp
			return [x, y]

		fn = swap.transpile()
		code = emit(fn)
		assert (
			code
			== "function swap_1(x, y) {\nlet temp = x;\nx = y;\ny = temp;\nreturn [x, y];\n}"
		)

	def test_while_loop(self):
		@javascript
		def countdown(n: int) -> int:
			while n > 0:
				n = n - 1
			return n

		fn = countdown.transpile()
		code = emit(fn)
		assert (
			code
			== "function countdown_1(n) {\nwhile (n > 0) {\nn = n - 1;\n}\nreturn n;\n}"
		)

	def test_for_of_loop(self):
		@javascript
		def sum_items(items: Iterable[int]) -> int:
			total = 0
			for x in items:
				total = total + x
			return total

		fn = sum_items.transpile()
		code = emit(fn)
		assert (
			code
			== "function sum_items_1(items) {\nlet total = 0;\nfor (const x of items) {\ntotal = total + x;\n}\nreturn total;\n}"
		)

	def test_for_of_with_tuple_unpacking(self):
		@javascript
		def sum_pairs(pairs: Iterable[tuple[int, int]]) -> int:
			total = 0
			for a, b in pairs:
				total = total + a + b
			return total

		fn = sum_pairs.transpile()
		code = emit(fn)
		assert (
			code
			== "function sum_pairs_1(pairs) {\nlet total = 0;\nfor (const [a, b] of pairs) {\ntotal = total + a + b;\n}\nreturn total;\n}"
		)

	def test_break_statement(self):
		@javascript
		def find_first(items: Iterable[Any], target: Any) -> Any:
			result = None
			for x in items:
				if x == target:
					result = x
					break
			return result

		fn = find_first.transpile()
		code = emit(fn)
		assert (
			code
			== "function find_first_1(items, target) {\nlet result = null;\nfor (const x of items) {\nif (x === target) {\nresult = x;\nbreak;\n}\n}\nreturn result;\n}"
		)

	def test_continue_statement(self):
		@javascript
		def count_positive(items: Iterable[int]) -> int:
			count = 0
			for x in items:
				if x <= 0:
					continue
				count = count + 1
			return count

		fn = count_positive.transpile()
		code = emit(fn)
		assert (
			code
			== "function count_positive_1(items) {\nlet count = 0;\nfor (const x of items) {\nif (x <= 0) {\ncontinue;\n}\ncount = count + 1;\n}\nreturn count;\n}"
		)

	def test_augmented_assignment(self):
		@javascript
		def add_to(x: int, y: int) -> int:
			x += y
			return x

		fn = add_to.transpile()
		code = emit(fn)
		assert code == "function add_to_1(x, y) {\nx += y;\nreturn x;\n}"

	def test_nested_function(self):
		@javascript
		def outer(x: int) -> int:
			def inner(y: int) -> int:
				return x + y

			return inner(10)

		fn = outer.transpile()
		code = emit(fn)
		assert (
			code
			== "function outer_1(x) {\nconst inner = function(y) {\nreturn x + y;\n};\nreturn inner(10);\n}"
		)

	def test_tuple_unpacking_assignment(self):
		@javascript
		def unpack(t: tuple[int, int]) -> int:
			a, b = t
			return a + b

		fn = unpack.transpile()
		code = emit(fn)
		assert (
			code
			== "function unpack_1(t) {\nconst $tmp0 = t;\nlet a = $tmp0[0];\nlet b = $tmp0[1];\nreturn a + b;\n}"
		)


# =============================================================================
# Exception Handling
# =============================================================================


class TestExceptionHandling:
	"""Test try/except/finally/raise transpilation."""

	def test_simple_try_except(self):
		"""Basic try/except block."""

		@javascript
		def safe_parse(s: str) -> int:
			try:
				return int(s)
			except:
				return 0

		fn = safe_parse.transpile()
		code = emit(fn)
		assert (
			code
			== "function safe_parse_1(s) {\ntry {\nreturn parseInt(s);\n} catch {\nreturn 0;\n}\n}"
		)

	def test_try_except_with_variable(self):
		"""Try/except with exception variable."""

		@javascript
		def safe_divide(a: int, b: int) -> int:
			try:
				return a // b
			except Exception as e:
				print(e)
				return 0

		fn = safe_divide.transpile()
		code = emit(fn)
		assert (
			code
			== "function safe_divide_1(a, b) {\ntry {\nreturn Math.floor(a / b);\n} catch (e) {\nconsole.log(e);\nreturn 0;\n}\n}"
		)

	def test_try_finally(self):
		"""Try/finally without except."""

		@javascript
		def cleanup(x: int) -> int:
			try:
				return x * 2
			finally:
				print("done")

		fn = cleanup.transpile()
		code = emit(fn)
		assert (
			code
			== 'function cleanup_1(x) {\ntry {\nreturn x * 2;\n} finally {\nconsole.log("done");\n}\n}'
		)

	def test_try_except_finally(self):
		"""Try/except/finally block."""

		@javascript
		def full_block(x: int) -> int:
			try:
				return x // 0
			except:
				return -1
			finally:
				print("cleanup")

		fn = full_block.transpile()
		code = emit(fn)
		assert (
			code
			== 'function full_block_1(x) {\ntry {\nreturn Math.floor(x / 0);\n} catch {\nreturn -1;\n} finally {\nconsole.log("cleanup");\n}\n}'
		)

	def test_raise_error(self):
		"""Raise an error."""

		@javascript
		def fail():
			raise Exception("something went wrong")

		fn = fail.transpile()
		code = emit(fn)
		assert (
			code
			== 'function fail_1() {\nthrow new Error("something went wrong");\n}'
		)

	def test_raise_with_variable(self):
		"""Raise with a variable."""

		@javascript
		def rethrow(e: Exception):
			raise e

		fn = rethrow.transpile()
		code = emit(fn)
		assert code == "function rethrow_1(e) {\nthrow e;\n}"
