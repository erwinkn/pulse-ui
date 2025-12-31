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

	def test_min_iterable(self):
		@javascript
		def get_min(items: Iterable[int | float]):
			return min(items)

		fn = get_min.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_min_1(items) {\nreturn Math.min(...Array.from(items));\n}"
		)

	def test_max_two_args(self):
		@javascript
		def get_max(a: int | float, b: int | float):
			return max(a, b)

		fn = get_max.transpile()
		code = emit(fn)
		assert code == "function get_max_1(a, b) {\nreturn Math.max(a, b);\n}"

	def test_max_iterable(self):
		@javascript
		def get_max(items: Iterable[int | float]):
			return max(items)

		fn = get_max.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_max_1(items) {\nreturn Math.max(...Array.from(items));\n}"
		)

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
		assert (
			code
			== "function get_range_1(start, stop) {\nreturn Array.from(new Array(Math.max(0, Math.ceil((stop - start) / 1))).keys(), i => start + i * 1);\n}"
		)

	def test_range_with_step(self):
		@javascript
		def get_range(start: int, stop: int, step: int):
			return range(start, stop, step)

		fn = get_range.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_range_1(start, stop, step) {\nreturn Array.from(new Array(Math.max(0, Math.ceil((stop - start) / step))).keys(), i => start + i * step);\n}"
		)


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
		assert (
			code
			== "function combine_1(a, b) {\nreturn Array.from(new Array(Math.min(a.length, b.length)).keys(), i => [a[i], b[i]]);\n}"
		)

	def test_zip_three_arrays(self):
		@javascript
		def combine(a: Iterable[Any], b: Iterable[Any], c: Iterable[Any]):
			return zip(a, b, c)  # noqa: B905

		fn = combine.transpile()
		code = emit(fn)
		assert (
			code
			== "function combine_1(a, b, c) {\nreturn Array.from(new Array(Math.min(Math.min(a.length, b.length), c.length)).keys(), i => [a[i], b[i], c[i]]);\n}"
		)


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
		assert (
			code
			== "function round_it_1(x, n) {\nreturn Number(Number(x).toFixed(n));\n}"
		)

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
		assert (
			code
			== "function divmod_it_1(x, y) {\nreturn [Math.floor(x / y), x - Math.floor(x / y) * y];\n}"
		)


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
		assert (
			code
			== "function sort_items_1(items) {\nreturn items.slice().sort((a, b) => (a > b) - (a < b));\n}"
		)

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
		assert (
			code
			== 'function cap_1(s) {\nreturn typeof s === "string" ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s.capitalize();\n}'
		)

	def test_zfill_runtime_check(self):
		@javascript
		def pad(s: str, width: int):
			return s.zfill(width)

		fn = pad.transpile()
		code = emit(fn)
		assert (
			code
			== 'function pad_1(s, width) {\nreturn typeof s === "string" ? s.padStart(width, "0") : s.zfill(width);\n}'
		)

	def test_join_runtime_check(self):
		"""join is reversed: sep.join(items) -> items.join(sep)"""

		@javascript
		def join_them(sep: str, items: Iterable[str]):
			return sep.join(items)

		fn = join_them.transpile()
		code = emit(fn)
		assert (
			code
			== 'function join_them_1(sep, items) {\nreturn typeof sep === "string" ? items.join(sep) : sep.join(items);\n}'
		)

	def test_split_with_separator(self):
		"""split with separator falls through to default."""

		@javascript
		def split_it(s: str):
			return s.split(",")

		fn = split_it.transpile()
		code = emit(fn)
		# split falls through to default, no ternary needed
		assert code == 'function split_it_1(s) {\nreturn s.split(",");\n}'

	def test_split_without_args_uses_whitespace_semantics(self):
		"""split() without args should use Python whitespace semantics.

		Python: "a  b".split() -> ["a", "b"] (splits on whitespace, removes empty)
		JS: "a  b".split() -> ["a  b"] (returns whole string)

		Fix: str.trim().split(/\\s+/)
		"""

		@javascript
		def split_whitespace(s: str):
			return s.split()

		fn = split_whitespace.transpile()
		code = emit(fn)
		assert (
			code
			== 'function split_whitespace_1(s) {\nreturn typeof s === "string" ? s.trim().split(/\\s+/) : s.split();\n}'
		)


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
		assert (
			code
			== "function add_item_1(items, val) {\nreturn Array.isArray(items) ? [items.push(val), undefined][1] : items.append(val);\n}"
		)

	def test_extend_runtime_check(self):
		@javascript
		def extend_items(items: list[Any], more: Iterable[Any]):
			items.extend(more)

		fn = extend_items.transpile()
		code = emit(fn)
		assert (
			code
			== "function extend_items_1(items, more) {\nreturn Array.isArray(items) ? [items.push(...more), undefined][1] : items.extend(more);\n}"
		)

	def test_pop_no_index_has_set_check(self):
		"""pop() without index checks for Set to handle set.pop() semantics."""

		@javascript
		def remove_last(items: list[Any] | set[Any]):
			return items.pop()

		fn = remove_last.transpile()
		code = emit(fn)
		assert (
			code
			== "function remove_last_1(items) {\nreturn items instanceof Set ? ($v => [items.delete($v), $v][1])(items.values().next().value) : items.pop();\n}"
		)

	def test_pop_with_index_runtime_check(self):
		"""pop(idx) -> splice(idx, 1)[0]"""

		@javascript
		def remove_at(items: list[Any], idx: int):
			return items.pop(idx)

		fn = remove_at.transpile()
		code = emit(fn)
		assert (
			code
			== "function remove_at_1(items, idx) {\nreturn Array.isArray(items) ? items.splice(idx, 1)[0] : items instanceof Map ? ($v => [items.delete(idx), $v][1])(items.get(idx)) : items.pop(idx);\n}"
		)

	def test_copy_runtime_check(self):
		@javascript
		def clone(items: list[Any] | dict[Any, Any] | set[Any]):
			return items.copy()

		fn = clone.transpile()
		code = emit(fn)
		assert (
			code
			== "function clone_1(items) {\nreturn Array.isArray(items) ? items.slice() : items instanceof Set ? new Set(items) : items instanceof Map ? new Map(items.entries()) : items.copy();\n}"
		)

	def test_index_runtime_check(self):
		@javascript
		def find_idx(items: list[Any], val: Any):
			return items.index(val)

		fn = find_idx.transpile()
		code = emit(fn)
		assert (
			code
			== "function find_idx_1(items, val) {\nreturn Array.isArray(items) ? items.indexOf(val) : items.index(val);\n}"
		)

	def test_count_runtime_check(self):
		@javascript
		def count_val(items: list[Any], val: Any):
			return items.count(val)

		fn = count_val.transpile()
		code = emit(fn)
		assert (
			code
			== 'function count_val_1(items, val) {\nreturn typeof items === "string" ? items.split(val).length - 1 : Array.isArray(items) ? items.filter(v => v === val).length : items.count(val);\n}'
		)

	def test_reverse_runtime_check(self):
		@javascript
		def rev(items: list[Any]):
			items.reverse()

		fn = rev.transpile()
		code = emit(fn)
		assert (
			code
			== "function rev_1(items) {\nreturn Array.isArray(items) ? [items.reverse(), undefined][1] : items.reverse();\n}"
		)

	def test_sort_runtime_check(self):
		@javascript
		def sort_them(items: list[Any]):
			items.sort()

		fn = sort_them.transpile()
		code = emit(fn)
		assert (
			code
			== "function sort_them_1(items) {\nreturn Array.isArray(items) ? [items.sort(), undefined][1] : items.sort();\n}"
		)

	def test_remove_throws_when_not_found(self):
		"""list.remove(value) should throw error when value not found.

		Python raises ValueError if value not in list. The JS implementation
		must check indexOf result and throw, not silently remove last element.
		"""

		@javascript
		def remove_item(items: list[Any], val: Any):
			items.remove(val)

		fn = remove_item.transpile()
		code = emit(fn)
		assert (
			code
			== 'function remove_item_1(items, val) {\nreturn Array.isArray(items) ? ($i => $i < 0 ? (() => { throw new Error("list.remove(x): x not in list"); })() : items.splice($i, 1))(items.indexOf(val)) : items instanceof Set ? items.delete(val) : items.remove(val);\n}'
		)


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
		assert (
			code
			== 'function get_keys_1() {\nreturn Map([["a", 1]]) instanceof Map ? [...Map([["a", 1]]).keys()] : Map([["a", 1]]).keys();\n}'
		)


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
		assert (
			code
			== "function safe_get_1(d, key, default) {\nreturn d instanceof Map ? d.get(key) ?? default : d.get(key, default);\n}"
		)

	def test_keys_runtime_check(self):
		@javascript
		def get_keys(d: dict[Any, Any]):
			return d.keys()

		fn = get_keys.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_keys_1(d) {\nreturn d instanceof Map ? [...d.keys()] : d.keys();\n}"
		)

	def test_values_runtime_check(self):
		@javascript
		def get_values(d: dict[Any, Any]):
			return d.values()

		fn = get_values.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_values_1(d) {\nreturn d instanceof Map ? [...d.values()] : d.values();\n}"
		)

	def test_items_runtime_check(self):
		@javascript
		def get_items(d: dict[Any, Any]):
			return d.items()

		fn = get_items.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_items_1(d) {\nreturn d instanceof Map ? [...d.entries()] : d.items();\n}"
		)

	def test_clear_has_array_check(self):
		"""clear() has special array handling (length = 0)."""

		@javascript
		def clear_dict(d: list[Any] | dict[Any, Any] | set[Any]):
			d.clear()

		fn = clear_dict.transpile()
		code = emit(fn)
		assert (
			code
			== "function clear_dict_1(d) {\nreturn Array.isArray(d) ? [d.length = 0, undefined][1] : d.clear();\n}"
		)


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
		assert (
			code
			== 'function remove_item_1(s, val) {\nreturn Array.isArray(s) ? ($i => $i < 0 ? (() => { throw new Error("list.remove(x): x not in list"); })() : s.splice($i, 1))(s.indexOf(val)) : s instanceof Set ? s.delete(val) : s.remove(val);\n}'
		)

	def test_discard_runtime_check(self):
		"""discard() -> delete()"""

		@javascript
		def discard_item(s: set[Any], val: Any):
			s.discard(val)

		fn = discard_item.transpile()
		code = emit(fn)
		assert (
			code
			== "function discard_item_1(s, val) {\nreturn s instanceof Set ? s.delete(val) : s.discard(val);\n}"
		)

	def test_clear_has_array_check(self):
		"""clear() has array handling."""

		@javascript
		def clear_set(s: list[Any] | set[Any]):
			s.clear()

		fn = clear_set.transpile()
		code = emit(fn)
		assert (
			code
			== "function clear_set_1(s) {\nreturn Array.isArray(s) ? [s.length = 0, undefined][1] : s.clear();\n}"
		)


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
		assert (
			code
			== "function clone_1(x) {\nreturn Array.isArray(x) ? x.slice() : x instanceof Set ? new Set(x) : x instanceof Map ? new Map(x.entries()) : x.copy();\n}"
		)

	def test_clear_array_vs_others(self):
		"""clear() has special array handling, then falls through."""

		@javascript
		def clear_it(x: list[Any] | dict[Any, Any] | set[Any]):
			x.clear()

		fn = clear_it.transpile()
		code = emit(fn)
		assert (
			code
			== "function clear_it_1(x) {\nreturn Array.isArray(x) ? [x.length = 0, undefined][1] : x.clear();\n}"
		)

	def test_keys_is_dict_only(self):
		"""keys() only exists on dict, so only Map check."""

		@javascript
		def get_keys(x: dict[Any, Any]):
			return x.keys()

		fn = get_keys.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_keys_1(x) {\nreturn x instanceof Map ? [...x.keys()] : x.keys();\n}"
		)

	def test_pop_is_list_and_set(self):
		"""pop(idx) only on list, pop() also on set."""

		@javascript
		def remove(x: list[Any], idx: int):
			return x.pop(idx)

		fn = remove.transpile()
		code = emit(fn)
		assert (
			code
			== "function remove_1(x, idx) {\nreturn Array.isArray(x) ? x.splice(idx, 1)[0] : x instanceof Map ? ($v => [x.delete(idx), $v][1])(x.get(idx)) : x.pop(idx);\n}"
		)

	def test_upper_is_string_only(self):
		"""upper() only exists on string."""

		@javascript
		def up(x: str):
			return x.upper()

		fn = up.transpile()
		code = emit(fn)
		assert (
			code
			== 'function up_1(x) {\nreturn typeof x === "string" ? x.toUpperCase() : x.upper();\n}'
		)


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
		assert (
			code
			== "function clone_1(x) {\nreturn Array.isArray(x) ? x.slice() : x instanceof Set ? new Set(x) : x instanceof Map ? new Map(x.entries()) : x.copy();\n}"
		)

	def test_remove_set_only(self):
		"""remove/discard only exist on Set."""

		@javascript
		def rem(x: set[Any], v: Any):
			return x.remove(v)

		fn = rem.transpile()
		code = emit(fn)
		assert (
			code
			== 'function rem_1(x, v) {\nreturn Array.isArray(x) ? ($i => $i < 0 ? (() => { throw new Error("list.remove(x): x not in list"); })() : x.splice($i, 1))(x.indexOf(v)) : x instanceof Set ? x.delete(v) : x.remove(v);\n}'
		)
