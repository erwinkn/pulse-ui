"""Python re module transpilation to JavaScript RegExp.

This module provides transpilation from Python's `re` module to JavaScript's RegExp.
For direct JavaScript RegExp bindings, use `pulse.js.regexp` instead.

Supported features:
- re.match, re.search, re.fullmatch, re.sub, re.split, re.findall, re.compile
- Flags: re.I, re.M, re.S, re.U (re.VERBOSE/re.X is NOT supported)
- Named groups: (?P<name>...) → (?<name>...)
- Named backrefs: (?P=name) → \\k<name>
- Replacement backrefs: \\g<name> → $<name>, \\1 → $1

Limitations:
- re.VERBOSE (re.X) is not supported - no JS equivalent
- Conditional patterns (?(id)yes|no) are not supported
- \\A and \\Z have different semantics with multiline mode
"""

# pyright: reportUnannotatedClassAttribute=false

import re as re_module

from pulse.transpiler.constants import jsify
from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.nodes import (
	JSArray,
	JSArrowFunction,
	JSExpr,
	JSIdentifier,
	JSMemberCall,
	JSNew,
	JSNumber,
	JSSpread,
	JSString,
	JSSubscript,
)
from pulse.transpiler.py_module import PyModule


def _convert_pattern(pattern: str) -> str:
	"""Convert Python regex syntax to JavaScript regex syntax.

	Handles:
	- (?P<name>...) → (?<name>...)
	- (?P=name) → \\k<name>
	"""
	import re

	# Convert named groups: (?P<name>...) → (?<name>...)
	result = re.sub(r"\(\?P<([^>]+)>", r"(?<\1>", pattern)

	# Convert named backreferences: (?P=name) → \k<name>
	result = re.sub(r"\(\?P=([^)]+)\)", r"\\k<\1>", result)

	return result


def _convert_replacement(replacement: str) -> str:
	"""Convert Python replacement string syntax to JavaScript.

	Handles:
	- \\g<name> → $<name>
	- \\g<0>, \\g<1>, etc. → $0, $1, etc.
	- \\1, \\2, etc. → $1, $2, etc. (already handled by JS)
	"""
	import re

	# Convert named group references: \g<name> → $<name>
	result = re.sub(r"\\g<([^>]+)>", r"$<\1>", replacement)

	# Convert numeric group references: \1 → $1 (for replacement strings)
	# Note: In Python replacement, \1 means group 1. In JS, it's $1.
	result = re.sub(r"\\([1-9][0-9]*)", r"$\1", result)

	return result


def _get_pattern_string(pattern: JSExpr) -> str | None:
	"""Extract the string value from a JSString pattern, or None if dynamic."""
	if isinstance(pattern, JSString):
		return pattern.value
	return None


def _make_regexp(
	pattern: JSExpr,
	flags: str = "",
	*,
	anchor_start: bool = False,
	anchor_both: bool = False,
) -> JSExpr:
	"""Create a new RegExp expression, optionally converting the pattern."""
	pattern_str = _get_pattern_string(pattern)

	if pattern_str is not None:
		# Static pattern - convert at transpile time
		converted = _convert_pattern(pattern_str)
		if anchor_start and not converted.startswith("^"):
			converted = "^" + converted
		if anchor_both:
			if not converted.startswith("^"):
				converted = "^" + converted
			if not converted.endswith("$"):
				converted = converted + "$"
		pattern = JSString(converted)

	args: list[JSExpr] = [pattern]
	if flags:
		args.append(JSString(flags))

	return JSNew(JSIdentifier("RegExp"), args)


# Flag constants - these emit their JS equivalent flag character
class _FlagExpr(JSExpr):
	"""A regex flag that emits as a string character."""

	def __init__(self, flag: str, name: str):
		self.flag = flag
		self.name = name

	def emit(self) -> str:  # pyright: ignore[reportImplicitOverride]
		return f'"{self.flag}"'


class PyRe(PyModule):
	"""Provides transpilation for Python re functions to JavaScript RegExp."""

	# Flag constants
	I = _FlagExpr("i", "IGNORECASE")  # noqa: E741
	IGNORECASE = _FlagExpr("i", "IGNORECASE")
	M = _FlagExpr("m", "MULTILINE")
	MULTILINE = _FlagExpr("m", "MULTILINE")
	S = _FlagExpr("s", "DOTALL")
	DOTALL = _FlagExpr("s", "DOTALL")
	U = _FlagExpr("u", "UNICODE")
	UNICODE = _FlagExpr("u", "UNICODE")

	# Unsupported flags - will error at transpile time
	@staticmethod
	def _unsupported_flag(name: str) -> JSExpr:
		raise JSCompilationError(
			f"re.{name} (VERBOSE) flag is not supported - no JavaScript equivalent"
		)

	X = property(lambda self: PyRe._unsupported_flag("X"))
	VERBOSE = property(lambda self: PyRe._unsupported_flag("VERBOSE"))
	A = property(lambda self: PyRe._unsupported_flag("A"))
	ASCII = property(lambda self: PyRe._unsupported_flag("ASCII"))

	@staticmethod
	def compile(
		pattern: str | JSExpr,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Compile a pattern into a RegExp object.

		re.compile(pattern) → new RegExp(pattern)
		re.compile(pattern, re.I) → new RegExp(pattern, "i")
		"""
		pattern_expr = jsify(pattern)
		flag_str = ""

		if isinstance(flags, _FlagExpr):
			flag_str = flags.flag
		elif isinstance(flags, int) and flags != 0:
			# Handle Python flag integers at transpile time
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"
			if flags & re_module.UNICODE:
				flag_str += "u"
			if flags & re_module.VERBOSE:
				raise JSCompilationError(
					"re.VERBOSE flag is not supported - no JavaScript equivalent"
				)
			if flags & re_module.ASCII:
				raise JSCompilationError(
					"re.ASCII flag is not supported in JavaScript RegExp"
				)

		return _make_regexp(pattern_expr, flag_str)

	@staticmethod
	def match(
		pattern: str | JSExpr,
		string: str | JSExpr,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Match pattern at the beginning of string.

		re.match(pattern, string) → string.match(new RegExp("^" + pattern))

		Returns match array or null.
		"""
		pattern_expr = jsify(pattern)
		string_expr = jsify(string)

		flag_str = ""
		if isinstance(flags, _FlagExpr):
			flag_str = flags.flag
		elif isinstance(flags, int) and flags != 0:
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"

		regexp = _make_regexp(pattern_expr, flag_str, anchor_start=True)
		return JSMemberCall(string_expr, "match", [regexp])

	@staticmethod
	def fullmatch(
		pattern: str | JSExpr,
		string: str | JSExpr,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Match pattern against the entire string.

		re.fullmatch(pattern, string) → string.match(new RegExp("^pattern$"))
		"""
		pattern_expr = jsify(pattern)
		string_expr = jsify(string)

		flag_str = ""
		if isinstance(flags, _FlagExpr):
			flag_str = flags.flag
		elif isinstance(flags, int) and flags != 0:
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"

		regexp = _make_regexp(pattern_expr, flag_str, anchor_both=True)
		return JSMemberCall(string_expr, "match", [regexp])

	@staticmethod
	def search(
		pattern: str | JSExpr,
		string: str | JSExpr,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Search for pattern anywhere in string.

		re.search(pattern, string) → new RegExp(pattern).exec(string)

		Returns match array or null.
		"""
		pattern_expr = jsify(pattern)
		string_expr = jsify(string)

		flag_str = ""
		if isinstance(flags, _FlagExpr):
			flag_str = flags.flag
		elif isinstance(flags, int) and flags != 0:
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"

		regexp = _make_regexp(pattern_expr, flag_str)
		return JSMemberCall(regexp, "exec", [string_expr])

	@staticmethod
	def sub(
		pattern: str | JSExpr,
		repl: str | JSExpr,
		string: str | JSExpr,
		count: int | JSExpr = 0,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Replace occurrences of pattern in string.

		re.sub(pattern, repl, string) → string.replace(new RegExp(pattern, "g"), repl)
		re.sub(pattern, repl, string, count=1) → string.replace(new RegExp(pattern), repl)
		"""
		pattern_expr = jsify(pattern)
		string_expr = jsify(string)
		repl_expr = jsify(repl)

		# Convert replacement string if it's a literal
		if isinstance(repl_expr, JSString):
			repl_expr = JSString(_convert_replacement(repl_expr.value))

		# Determine flags
		flag_str = ""
		if isinstance(flags, _FlagExpr):
			flag_str = flags.flag
		elif isinstance(flags, int) and flags != 0:
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"

		# Handle count parameter
		use_global = True
		count_val: int | None = None
		if isinstance(count, int):
			count_val = count
		elif isinstance(count, JSNumber) and isinstance(count.value, int):
			count_val = count.value

		if count_val is not None:
			if count_val == 1:
				use_global = False
			elif count_val > 1:
				raise JSCompilationError(
					"re.sub with count > 1 is not directly supported in JavaScript. Use count=0 (replace all) or count=1 (replace first)."
				)
		elif isinstance(count, JSExpr):
			# Dynamic count - need runtime handling
			raise JSCompilationError(
				"Dynamic count in re.sub is not supported. Use literal 0 or 1."
			)

		if use_global and "g" not in flag_str:
			flag_str = "g" + flag_str

		regexp = _make_regexp(pattern_expr, flag_str)
		return JSMemberCall(string_expr, "replace", [regexp, repl_expr])

	@staticmethod
	def split(
		pattern: str | JSExpr,
		string: str | JSExpr,
		maxsplit: int | JSExpr = 0,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Split string by pattern.

		re.split(pattern, string) → string.split(new RegExp(pattern))

		Note: maxsplit > 0 requires runtime handling and is limited.
		"""
		pattern_expr = jsify(pattern)
		string_expr = jsify(string)

		flag_str = ""
		if isinstance(flags, _FlagExpr):
			flag_str = flags.flag
		elif isinstance(flags, int) and flags != 0:
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"

		regexp = _make_regexp(pattern_expr, flag_str)

		# Extract maxsplit value
		maxsplit_val: int | None = None
		if isinstance(maxsplit, int):
			maxsplit_val = maxsplit
		elif isinstance(maxsplit, JSNumber) and isinstance(maxsplit.value, int):
			maxsplit_val = maxsplit.value

		if maxsplit_val is not None:
			if maxsplit_val == 0:
				# No limit
				return JSMemberCall(string_expr, "split", [regexp])
			elif maxsplit_val > 0:
				# JS split limit is different from Python's maxsplit
				# Python: maxsplit=2 means at most 2 splits, resulting in 3 parts
				# JS: limit=3 means at most 3 parts
				# So we add 1 to convert
				return JSMemberCall(
					string_expr, "split", [regexp, JSNumber(maxsplit_val + 1)]
				)

		raise JSCompilationError(
			"Dynamic maxsplit in re.split is not supported. Use literal value."
		)

	@staticmethod
	def findall(
		pattern: str | JSExpr,
		string: str | JSExpr,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Find all matches of pattern in string.

		re.findall(pattern, string) → [...string.matchAll(new RegExp(pattern, "g"))].map(m => m[0])

		Note: Returns array of matched strings (not groups).
		For patterns with groups, this returns the full match, not the groups.
		"""
		pattern_expr = jsify(pattern)
		string_expr = jsify(string)

		flag_str = "g"  # Always need global for matchAll
		if isinstance(flags, _FlagExpr):
			flag_str += flags.flag
		elif isinstance(flags, int) and flags != 0:
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"

		regexp = _make_regexp(pattern_expr, flag_str)

		# [...string.matchAll(regexp)].map(m => m[0])
		match_all = JSMemberCall(string_expr, "matchAll", [regexp])
		spread_array = JSArray([JSSpread(match_all)])
		# Arrow: m => m[0]
		arrow = JSArrowFunction("m", JSSubscript(JSIdentifier("m"), JSNumber(0)))
		return JSMemberCall(spread_array, "map", [arrow])

	@staticmethod
	def test(
		pattern: str | JSExpr,
		string: str | JSExpr,
		flags: int | JSExpr = 0,
	) -> JSExpr:
		"""Test if pattern matches anywhere in string.

		This is a convenience method (not in Python's re module) that maps to RegExp.test().

		re.test(pattern, string) → new RegExp(pattern).test(string)

		Returns boolean.
		"""
		pattern_expr = jsify(pattern)
		string_expr = jsify(string)

		flag_str = ""
		if isinstance(flags, _FlagExpr):
			flag_str = flags.flag
		elif isinstance(flags, int) and flags != 0:
			if flags & re_module.IGNORECASE:
				flag_str += "i"
			if flags & re_module.MULTILINE:
				flag_str += "m"
			if flags & re_module.DOTALL:
				flag_str += "s"

		regexp = _make_regexp(pattern_expr, flag_str)
		return JSMemberCall(regexp, "test", [string_expr])

	@staticmethod
	def escape(pattern: str | JSExpr) -> JSExpr:
		"""Escape special regex characters in pattern.

		re.escape(string) → string.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")
		"""
		pattern_expr = jsify(pattern)

		# The escape regex pattern for JS
		escape_regexp = JSNew(
			JSIdentifier("RegExp"),
			[JSString("[.*+?^${}()|[\\]\\\\]"), JSString("g")],
		)

		return JSMemberCall(pattern_expr, "replace", [escape_regexp, JSString("\\$&")])
