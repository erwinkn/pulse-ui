"""
Tests for builtin function and method transpilation.

Tests both individual builtins and the runtime type dispatch for methods
that exist on multiple Python types.
"""

from collections.abc import Iterable, Sequence, Sized
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
# Builtin Functions
# =============================================================================


class TestLen:
	def test_len_generates_length_size_fallback(self):
		@javascript
		def get_length(x: Sized):
			return len(x)

		fn = get_length.transpile()
		code = emit(fn)
		assert code == "function get_length_1(x) {\nreturn x.length ?? x.size;\n}"


class TestPrint:
	def test_print_single_arg(self):
		@javascript
		def log(msg: object):
			print(msg)

		fn = log.transpile()
		code = emit(fn)
		assert code == "function log_1(msg) {\nreturn console.log(msg);\n}"

	def test_print_multiple_args(self):
		@javascript
		def log(a: object, b: object, c: object):
			print(a, b, c)

		fn = log.transpile()
		code = emit(fn)
		assert code == "function log_1(a, b, c) {\nreturn console.log(a, b, c);\n}"


class TestMinMax:
	def test_min_two_args(self):
		@javascript
		def get_min(a: int | float, b: int | float):
			return min(a, b)

		fn = get_min.transpile()
		code = emit(fn)
		assert code == "function get_min_1(a, b) {\nreturn Math.min(a, b);\n}"

	def test_max_two_args(self):
		@javascript
		def get_max(a: int | float, b: int | float):
			return max(a, b)

		fn = get_max.transpile()
		code = emit(fn)
		assert code == "function get_max_1(a, b) {\nreturn Math.max(a, b);\n}"

	def test_nested_min_max(self):
		@javascript
		def clamp(x: int | float, lo: int | float, hi: int | float):
			return min(max(x, lo), hi)

		fn = clamp.transpile()
		code = emit(fn)
		assert (
			code
			== "function clamp_1(x, lo, hi) {\nreturn Math.min(Math.max(x, lo), hi);\n}"
		)


class TestTypeConversions:
	def test_str(self):
		@javascript
		def to_string(x: object):
			return str(x)

		fn = to_string.transpile()
		code = emit(fn)
		assert code == "function to_string_1(x) {\nreturn String(x);\n}"

	def test_int(self):
		@javascript
		def to_int(x: str | int | float):
			return int(x)

		fn = to_int.transpile()
		code = emit(fn)
		assert code == "function to_int_1(x) {\nreturn parseInt(x);\n}"

	def test_int_with_base(self):
		@javascript
		def parse_hex(x: str):
			return int(x, 16)

		fn = parse_hex.transpile()
		code = emit(fn)
		assert code == "function parse_hex_1(x) {\nreturn parseInt(x, 16);\n}"

	def test_float(self):
		@javascript
		def to_float(x: str | int | float):
			return float(x)

		fn = to_float.transpile()
		code = emit(fn)
		assert code == "function to_float_1(x) {\nreturn parseFloat(x);\n}"

	def test_bool(self):
		@javascript
		def to_bool(x: object):
			return bool(x)

		fn = to_bool.transpile()
		code = emit(fn)
		assert code == "function to_bool_1(x) {\nreturn Boolean(x);\n}"


class TestListSetDictConversions:
	def test_list(self):
		@javascript
		def to_list(x: Iterable[Any]):
			return list(x)

		fn = to_list.transpile()
		code = emit(fn)
		assert code == "function to_list_1(x) {\nreturn Array.from(x);\n}"

	def test_set_empty(self):
		@javascript
		def empty_set() -> set[object]:
			return set()

		fn = empty_set.transpile()
		code = emit(fn)
		assert code == "function empty_set_1() {\nreturn new Set();\n}"

	def test_set_from_iterable(self):
		@javascript
		def to_set(x: Iterable[Any]):
			return set(x)

		fn = to_set.transpile()
		code = emit(fn)
		assert code == "function to_set_1(x) {\nreturn new Set(x);\n}"

	def test_dict_empty(self):
		@javascript
		def empty_dict() -> dict[str, object]:
			return dict()

		fn = empty_dict.transpile()
		code = emit(fn)
		assert code == "function empty_dict_1() {\nreturn new Map();\n}"

	def test_dict_from_iterable(self):
		@javascript
		def to_dict(x: Iterable[tuple[Any, Any]]):
			return dict(x)

		fn = to_dict.transpile()
		code = emit(fn)
		assert code == "function to_dict_1(x) {\nreturn new Map(x);\n}"

	def test_tuple_empty(self):
		@javascript
		def empty_tuple() -> tuple[int]:
			return tuple()

		fn = empty_tuple.transpile()
		code = emit(fn)
		assert code == "function empty_tuple_1() {\nreturn [];\n}"

	def test_tuple_from_iterable(self):
		@javascript
		def to_tuple(x: Iterable[Any]):
			return tuple(x)

		fn = to_tuple.transpile()
		code = emit(fn)
		assert code == "function to_tuple_1(x) {\nreturn Array.from(x);\n}"


class TestRange:
	def test_range_single_arg(self):
		@javascript
		def get_range():
			return range(10)

		fn = get_range.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_range_1() {\nreturn Array.from(new Array(Math.max(0, 10)).keys());\n}"
		)

	def test_range_start_stop(self):
		@javascript
		def get_range(start: int, stop: int):
			return range(start, stop)

		fn = get_range.transpile()
		code = emit(fn)
		assert "Math.ceil" in code
		assert "start + i * 1" in code

	def test_range_with_step(self):
		@javascript
		def get_range(start: int, stop: int, step: int):
			return range(start, stop, step)

		fn = get_range.transpile()
		code = emit(fn)
		assert "Math.ceil" in code
		assert "start + i * step" in code


class TestEnumerate:
	def test_enumerate_default_start(self):
		@javascript
		def enum(items: Iterable[Any]):
			return enumerate(items)

		fn = enum.transpile()
		code = emit(fn)
		assert (
			code
			== "function enum_1(items) {\nreturn items.map((v, i) => [i + 0, v]);\n}"
		)

	def test_enumerate_custom_start(self):
		@javascript
		def enum(items: Iterable[Any], n: int):
			return enumerate(items, n)

		fn = enum.transpile()
		code = emit(fn)
		assert (
			code
			== "function enum_1(items, n) {\nreturn items.map((v, i) => [i + n, v]);\n}"
		)


class TestZip:
	def test_zip_two_arrays(self):
		@javascript
		def combine(a: Iterable[Any], b: Iterable[Any]):
			return zip(a, b)  # noqa: B905

		fn = combine.transpile()
		code = emit(fn)
		assert "Math.min(a.length, b.length)" in code
		assert "[a[i], b[i]]" in code

	def test_zip_three_arrays(self):
		@javascript
		def combine(a: Iterable[Any], b: Iterable[Any], c: Iterable[Any]):
			return zip(a, b, c)  # noqa: B905

		fn = combine.transpile()
		code = emit(fn)
		assert "Math.min(Math.min(a.length, b.length), c.length)" in code
		assert "[a[i], b[i], c[i]]" in code


class TestMapFilter:
	def test_map_with_lambda(self):
		@javascript
		def double_all(items: Iterable[Any]):
			return map(lambda x: x * 2, items)

		fn = double_all.transpile()
		code = emit(fn)
		assert (
			code == "function double_all_1(items) {\nreturn items.map(x => x * 2);\n}"
		)

	def test_filter_with_lambda(self):
		@javascript
		def get_positive(items: Iterable[int]):
			return filter(lambda x: x > 0, items)

		fn = get_positive.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_positive_1(items) {\nreturn items.filter(x => x > 0);\n}"
		)

	def test_filter_truthy(self):
		@javascript
		def filter_truthy(items: Iterable[Any]):
			return filter(None, items)

		fn = filter_truthy.transpile()
		code = emit(fn)
		assert (
			code == "function filter_truthy_1(items) {\nreturn items.filter(v => v);\n}"
		)


class TestReduceBuiltins:
	def test_sum_default_start(self):
		@javascript
		def total(items: Iterable[int | float]):
			return sum(items)

		fn = total.transpile()
		code = emit(fn)
		assert (
			code
			== "function total_1(items) {\nreturn items.reduce((a, b) => a + b, 0);\n}"
		)

	def test_sum_with_start(self):
		@javascript
		def total(items: Iterable[int | float], start: int | float):
			return sum(items, start)

		fn = total.transpile()
		code = emit(fn)
		assert (
			code
			== "function total_1(items, start) {\nreturn items.reduce((a, b) => a + b, start);\n}"
		)

	def test_any(self):
		@javascript
		def has_truthy(items: Iterable[Any]):
			return any(items)

		fn = has_truthy.transpile()
		code = emit(fn)
		assert code == "function has_truthy_1(items) {\nreturn items.some(v => v);\n}"

	def test_all(self):
		@javascript
		def all_truthy(items: Iterable[Any]):
			return all(items)

		fn = all_truthy.transpile()
		code = emit(fn)
		assert code == "function all_truthy_1(items) {\nreturn items.every(v => v);\n}"


class TestMathBuiltins:
	def test_abs(self):
		@javascript
		def get_abs(x: int | float):
			return abs(x)

		fn = get_abs.transpile()
		code = emit(fn)
		assert code == "function get_abs_1(x) {\nreturn Math.abs(x);\n}"

	def test_round_no_digits(self):
		@javascript
		def round_it(x: int | float):
			return round(x)

		fn = round_it.transpile()
		code = emit(fn)
		assert code == "function round_it_1(x) {\nreturn Math.round(x);\n}"

	def test_round_with_digits(self):
		@javascript
		def round_it(x: int | float, n: int):
			return round(x, n)

		fn = round_it.transpile()
		code = emit(fn)
		assert code == "function round_it_1(x, n) {\nreturn Number(x).toFixed(n);\n}"

	def test_pow(self):
		@javascript
		def power(base: int | float, exp: int | float):
			return pow(base, exp)

		fn = power.transpile()
		code = emit(fn)
		assert code == "function power_1(base, exp) {\nreturn Math.pow(base, exp);\n}"

	def test_divmod(self):
		@javascript
		def divmod_it(x: int | float, y: int | float):
			return divmod(x, y)

		fn = divmod_it.transpile()
		code = emit(fn)
		assert "Math.floor(x / y)" in code


class TestCharOrdBuiltins:
	def test_chr(self):
		@javascript
		def to_char(x: int):
			return chr(x)

		fn = to_char.transpile()
		code = emit(fn)
		assert code == "function to_char_1(x) {\nreturn String.fromCharCode(x);\n}"

	def test_ord(self):
		@javascript
		def to_code(x: str):
			return ord(x)

		fn = to_code.transpile()
		code = emit(fn)
		assert code == "function to_code_1(x) {\nreturn x.charCodeAt(0);\n}"


class TestSortingBuiltins:
	def test_sorted_simple(self):
		@javascript
		def sort_items(items: Iterable[Any]):
			return sorted(items)

		fn = sort_items.transpile()
		code = emit(fn)
		assert "items.slice().sort((a, b) => (a > b) - (a < b))" in code

	def test_reversed(self):
		@javascript
		def flip(items: Sequence[Any]):
			return reversed(items)

		fn = flip.transpile()
		code = emit(fn)
		assert code == "function flip_1(items) {\nreturn items.slice().reverse();\n}"


# =============================================================================
# String Methods - Known Type (literal)
# =============================================================================


class TestStringMethodsKnownType:
	"""String literal methods dispatch without runtime checks."""

	def test_upper_on_literal(self):
		@javascript
		def get_upper():
			return "hello".upper()

		fn = get_upper.transpile()
		code = emit(fn)
		assert code == 'function get_upper_1() {\nreturn "hello".toUpperCase();\n}'

	def test_lower_on_literal(self):
		@javascript
		def get_lower():
			return "HELLO".lower()

		fn = get_lower.transpile()
		code = emit(fn)
		assert code == 'function get_lower_1() {\nreturn "HELLO".toLowerCase();\n}'

	def test_strip_on_literal(self):
		@javascript
		def clean():
			return "  hello  ".strip()

		fn = clean.transpile()
		code = emit(fn)
		assert code == 'function clean_1() {\nreturn "  hello  ".trim();\n}'

	def test_replace_on_literal(self):
		@javascript
		def sub():
			return "hello".replace("l", "x")

		fn = sub.transpile()
		code = emit(fn)
		assert code == 'function sub_1() {\nreturn "hello".replaceAll("l", "x");\n}'


# =============================================================================
# String Methods - Unknown Type (runtime check)
# =============================================================================


class TestStringMethodsUnknownType:
	"""Unknown type string methods use runtime checks."""

	def test_upper_runtime_check(self):
		@javascript
		def process(s: str):
			return s.upper()

		fn = process.transpile()
		code = emit(fn)
		assert (
			code
			== 'function process_1(s) {\nreturn typeof s === "string" ? s.toUpperCase() : s.upper();\n}'
		)

	def test_lower_runtime_check(self):
		@javascript
		def process(s: str):
			return s.lower()

		fn = process.transpile()
		code = emit(fn)
		assert (
			code
			== 'function process_1(s) {\nreturn typeof s === "string" ? s.toLowerCase() : s.lower();\n}'
		)

	def test_strip_runtime_check(self):
		@javascript
		def clean(s: str):
			return s.strip()

		fn = clean.transpile()
		code = emit(fn)
		assert (
			code
			== 'function clean_1(s) {\nreturn typeof s === "string" ? s.trim() : s.strip();\n}'
		)

	def test_lstrip_runtime_check(self):
		@javascript
		def clean(s: str):
			return s.lstrip()

		fn = clean.transpile()
		code = emit(fn)
		assert (
			code
			== 'function clean_1(s) {\nreturn typeof s === "string" ? s.trimStart() : s.lstrip();\n}'
		)

	def test_rstrip_runtime_check(self):
		@javascript
		def clean(s: str):
			return s.rstrip()

		fn = clean.transpile()
		code = emit(fn)
		assert (
			code
			== 'function clean_1(s) {\nreturn typeof s === "string" ? s.trimEnd() : s.rstrip();\n}'
		)

	def test_replace_runtime_check(self):
		@javascript
		def sub(s: str, old: str, new: str):
			return s.replace(old, new)

		fn = sub.transpile()
		code = emit(fn)
		assert (
			code
			== 'function sub_1(s, old, new) {\nreturn typeof s === "string" ? s.replaceAll(old, new) : s.replace(old, new);\n}'
		)

	def test_startswith_runtime_check(self):
		@javascript
		def check(s: str, prefix: str):
			return s.startswith(prefix)

		fn = check.transpile()
		code = emit(fn)
		assert (
			code
			== 'function check_1(s, prefix) {\nreturn typeof s === "string" ? s.startsWith(prefix) : s.startswith(prefix);\n}'
		)

	def test_endswith_runtime_check(self):
		@javascript
		def check(s: str, suffix: str):
			return s.endswith(suffix)

		fn = check.transpile()
		code = emit(fn)
		assert (
			code
			== 'function check_1(s, suffix) {\nreturn typeof s === "string" ? s.endsWith(suffix) : s.endswith(suffix);\n}'
		)

	def test_capitalize_runtime_check(self):
		@javascript
		def cap(s: str):
			return s.capitalize()

		fn = cap.transpile()
		code = emit(fn)
		assert 'typeof s === "string"' in code
		assert "s.charAt(0).toUpperCase() + s.slice(1).toLowerCase()" in code

	def test_zfill_runtime_check(self):
		@javascript
		def pad(s: str, width: int):
			return s.zfill(width)

		fn = pad.transpile()
		code = emit(fn)
		assert 'typeof s === "string"' in code
		assert 's.padStart(width, "0")' in code

	def test_join_runtime_check(self):
		"""join is reversed: sep.join(items) -> items.join(sep)"""

		@javascript
		def join_them(sep: str, items: Iterable[str]):
			return sep.join(items)

		fn = join_them.transpile()
		code = emit(fn)
		assert 'typeof sep === "string"' in code
		assert "items.join(sep)" in code

	def test_split_no_transformation(self):
		"""split doesn't need transformation."""

		@javascript
		def split_it(s: str):
			return s.split(",")

		fn = split_it.transpile()
		code = emit(fn)
		# split falls through to default, no ternary needed
		assert code == 'function split_it_1(s) {\nreturn s.split(",");\n}'


# =============================================================================
# List Methods - Known Type (literal)
# =============================================================================


class TestListMethodsKnownType:
	"""List literal methods dispatch without runtime checks."""

	def test_append_on_literal(self):
		@javascript
		def add():
			return [1, 2].append(3)

		fn = add.transpile()
		code = emit(fn)
		# Uses array indexing [expr, undefined][1] for comma-like behavior
		assert code == "function add_1() {\nreturn [[1, 2].push(3), undefined][1];\n}"

	def test_pop_no_index_on_literal(self):
		@javascript
		def remove():
			return [1, 2, 3].pop()

		fn = remove.transpile()
		code = emit(fn)
		# pop() without index falls through to default .pop()
		assert code == "function remove_1() {\nreturn [1, 2, 3].pop();\n}"


# =============================================================================
# List Methods - Unknown Type (runtime check)
# =============================================================================


class TestListMethodsUnknownType:
	def test_append_runtime_check(self):
		@javascript
		def add_item(items: list[Any], val: Any):
			items.append(val)

		fn = add_item.transpile()
		code = emit(fn)
		assert "Array.isArray(items)" in code
		assert "[items.push(val), undefined][1]" in code

	def test_extend_runtime_check(self):
		@javascript
		def extend_items(items: list[Any], more: Iterable[Any]):
			items.extend(more)

		fn = extend_items.transpile()
		code = emit(fn)
		assert "Array.isArray(items)" in code
		assert "[items.push(...more), undefined][1]" in code

	def test_pop_no_index_has_set_check(self):
		"""pop() without index checks for Set to handle set.pop() semantics."""

		@javascript
		def remove_last(items: list[Any] | set[Any]):
			return items.pop()

		fn = remove_last.transpile()
		code = emit(fn)
		# Set.pop() requires special handling (get first value, delete it)
		assert "items instanceof Set" in code
		assert "items.pop()" in code

	def test_pop_with_index_runtime_check(self):
		"""pop(idx) -> splice(idx, 1)[0]"""

		@javascript
		def remove_at(items: list[Any], idx: int):
			return items.pop(idx)

		fn = remove_at.transpile()
		code = emit(fn)
		assert "Array.isArray(items)" in code
		assert "items.splice(idx, 1)[0]" in code

	def test_copy_runtime_check(self):
		@javascript
		def clone(items: list[Any] | dict[Any, Any] | set[Any]):
			return items.copy()

		fn = clone.transpile()
		code = emit(fn)
		# copy exists on List, Set, and Dict - should have all checks
		assert "Array.isArray(items)" in code
		assert "items.slice()" in code

	def test_index_runtime_check(self):
		@javascript
		def find_idx(items: list[Any], val: Any):
			return items.index(val)

		fn = find_idx.transpile()
		code = emit(fn)
		assert "Array.isArray(items)" in code
		assert "items.indexOf(val)" in code

	def test_count_runtime_check(self):
		@javascript
		def count_val(items: list[Any], val: Any):
			return items.count(val)

		fn = count_val.transpile()
		code = emit(fn)
		assert "Array.isArray(items)" in code
		assert "items.filter(v => v === val).length" in code

	def test_reverse_runtime_check(self):
		@javascript
		def rev(items: list[Any]):
			items.reverse()

		fn = rev.transpile()
		code = emit(fn)
		assert "Array.isArray(items)" in code
		# Uses [expr, undefined][1] pattern
		assert "[items.reverse(), undefined][1]" in code

	def test_sort_runtime_check(self):
		@javascript
		def sort_them(items: list[Any]):
			items.sort()

		fn = sort_them.transpile()
		code = emit(fn)
		assert "Array.isArray(items)" in code
		assert "[items.sort(), undefined][1]" in code


# =============================================================================
# Dict Methods - Known Type (new Map)
# =============================================================================


class TestDictMethodsKnownType:
	"""Dict methods on new Map() dispatch without runtime checks."""

	def test_keys_on_literal(self):
		@javascript
		def get_keys():
			return {"a": 1}.keys()

		fn = get_keys.transpile()
		code = emit(fn)
		# Dict literal becomes Map(...) call, but since it's a call (not JSNew),
		# the type isn't known at compile time, so runtime check is used
		assert "Map(" in code
		assert ".keys()" in code


# =============================================================================
# Dict Methods - Unknown Type (runtime check)
# =============================================================================


class TestDictMethodsUnknownType:
	def test_get_no_default_falls_through(self):
		"""get(key) without default needs no transformation."""

		@javascript
		def safe_get(d: dict[Any, Any], key: Any):
			return d.get(key)

		fn = safe_get.transpile()
		code = emit(fn)
		assert code == "function safe_get_1(d, key) {\nreturn d.get(key);\n}"

	def test_get_with_default_runtime_check(self):
		"""get(key, default) -> get(key) ?? default"""

		@javascript
		def safe_get(d: dict[Any, Any], key: Any, default: Any):
			return d.get(key, default)

		fn = safe_get.transpile()
		code = emit(fn)
		assert "d instanceof Map" in code
		assert "d.get(key) ?? default" in code

	def test_keys_runtime_check(self):
		@javascript
		def get_keys(d: dict[Any, Any]):
			return d.keys()

		fn = get_keys.transpile()
		code = emit(fn)
		assert "d instanceof Map" in code
		assert "[...d.keys()]" in code

	def test_values_runtime_check(self):
		@javascript
		def get_values(d: dict[Any, Any]):
			return d.values()

		fn = get_values.transpile()
		code = emit(fn)
		assert "d instanceof Map" in code
		assert "[...d.values()]" in code

	def test_items_runtime_check(self):
		@javascript
		def get_items(d: dict[Any, Any]):
			return d.items()

		fn = get_items.transpile()
		code = emit(fn)
		assert "d instanceof Map" in code
		assert "[...d.entries()]" in code

	def test_clear_has_array_check(self):
		"""clear() has special array handling (length = 0)."""

		@javascript
		def clear_dict(d: list[Any] | dict[Any, Any] | set[Any]):
			d.clear()

		fn = clear_dict.transpile()
		code = emit(fn)
		# Array.clear isn't standard JS so it uses length = 0
		assert "Array.isArray(d)" in code
		assert "d.length = 0" in code


# =============================================================================
# Set Methods
# =============================================================================


class TestSetMethods:
	def test_add_falls_through(self):
		"""add() is same in JS."""

		@javascript
		def add_item(s: set[Any], val: Any):
			s.add(val)

		fn = add_item.transpile()
		code = emit(fn)
		assert code == "function add_item_1(s, val) {\nreturn s.add(val);\n}"

	def test_remove_runtime_check(self):
		"""remove() -> delete()"""

		@javascript
		def remove_item(s: set[Any], val: Any):
			s.remove(val)

		fn = remove_item.transpile()
		code = emit(fn)
		assert "s instanceof Set" in code
		assert "s.delete(val)" in code

	def test_discard_runtime_check(self):
		"""discard() -> delete()"""

		@javascript
		def discard_item(s: set[Any], val: Any):
			s.discard(val)

		fn = discard_item.transpile()
		code = emit(fn)
		assert "s instanceof Set" in code
		assert "s.delete(val)" in code

	def test_clear_has_array_check(self):
		"""clear() has array handling."""

		@javascript
		def clear_set(s: list[Any] | set[Any]):
			s.clear()

		fn = clear_set.transpile()
		code = emit(fn)
		# Array special case comes first
		assert "Array.isArray(s)" in code


# =============================================================================
# Methods on Multiple Types - Runtime Dispatch
# =============================================================================


class TestMultiTypeMethodDispatch:
	"""Test methods that exist on multiple types generate proper ternary chains."""

	def test_copy_list_vs_dict_vs_set(self):
		"""copy() exists on list (slice), dict (new Map), and set (new Set)."""

		@javascript
		def clone(x: list[Any] | dict[Any, Any] | set[Any]):
			return x.copy()

		fn = clone.transpile()
		code = emit(fn)
		# Should check all types
		assert "Array.isArray(x)" in code
		assert "x instanceof Map" in code
		assert "x instanceof Set" in code
		# All transformations
		assert "x.slice()" in code
		assert "new Map(x.entries())" in code
		assert "new Set(x)" in code
		# Priority order: List (Array) checked first (outermost)
		assert code.index("Array.isArray") < code.index("instanceof Set")
		assert code.index("instanceof Set") < code.index("instanceof Map")

	def test_clear_array_vs_others(self):
		"""clear() has special array handling, then falls through."""

		@javascript
		def clear_it(x: list[Any] | dict[Any, Any] | set[Any]):
			x.clear()

		fn = clear_it.transpile()
		code = emit(fn)
		# Array.clear handled specially
		assert "Array.isArray(x)" in code
		assert "x.length = 0" in code

	def test_keys_is_dict_only(self):
		"""keys() only exists on dict, so only Map check."""

		@javascript
		def get_keys(x: dict[Any, Any]):
			return x.keys()

		fn = get_keys.transpile()
		code = emit(fn)
		assert "x instanceof Map" in code
		# No array type check
		assert "Array.isArray" not in code
		assert "typeof" not in code

	def test_pop_is_list_and_set(self):
		"""pop(idx) only on list, pop() also on set."""

		@javascript
		def remove(x: list[Any], idx: int):
			return x.pop(idx)

		fn = remove.transpile()
		code = emit(fn)
		assert "Array.isArray(x)" in code
		assert "x.splice(idx, 1)[0]" in code

	def test_upper_is_string_only(self):
		"""upper() only exists on string."""

		@javascript
		def up(x: str):
			return x.upper()

		fn = up.transpile()
		code = emit(fn)
		assert 'typeof x === "string"' in code
		assert "x.toUpperCase()" in code
		# No other type checks
		assert "Array.isArray" not in code


# =============================================================================
# Ternary Chain Priority Order
# =============================================================================


class TestTernaryPriority:
	"""Verify the priority order of ternary checks: String > List > Set > Dict."""

	def test_copy_priority_list_before_set_before_dict(self):
		"""List (Array) check comes before Set check, which comes before Dict (Map)."""

		@javascript
		def clone(x: list[Any] | dict[Any, Any] | set[Any]):
			return x.copy()

		fn = clone.transpile()
		code = emit(fn)
		# Array.isArray should be outermost (checked first)
		# instanceof Set in middle
		# instanceof Map innermost (fallback before final x.copy())
		array_pos = code.index("Array.isArray")
		set_pos = code.index("instanceof Set")
		map_pos = code.index("instanceof Map")
		assert array_pos < set_pos < map_pos

	def test_remove_set_only(self):
		"""remove/discard only exist on Set."""

		@javascript
		def rem(x: set[Any], v: Any):
			return x.remove(v)

		fn = rem.transpile()
		code = emit(fn)
		assert "x instanceof Set" in code
		assert "x.delete(v)" in code
		# Fallback is regular method call
		assert "x.remove(v)" in code
