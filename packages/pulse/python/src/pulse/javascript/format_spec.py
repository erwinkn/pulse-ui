import ast
from typing import TypedDict

from pulse.javascript.nodes import (
	JSBinary,
	JSCall,
	JSCompilationError,
	JSExpr,
	JSIdentifier,
	JSMember,
	JSMemberCall,
	JSNumber,
	JSString,
	JSTemplate,
	JSTertiary,
)


class FormatSpecInfo(TypedDict):
	fill: str | None
	align: str | None
	sign: str | None
	alt: bool
	zero: bool
	width: int | None
	grouping: str | None
	precision: int | None
	type: str | None


def _parse_format_spec(spec: str) -> FormatSpecInfo:
	"""Parse a Python format specification mini-language string.

	Returns a dict with keys: fill, align, sign, alt, zero, width, grouping,
	precision, type. Values may be None.
	"""
	i = 0
	n = len(spec)
	fill: str | None = None
	align: str | None = None
	sign: str | None = None
	alt: bool = False
	zero: bool = False
	width: int | None = None
	grouping: str | None = None
	precision: int | None = None
	typ: str | None = None

	# [fill][align]
	if n - i >= 2 and spec[i + 1] in "<>^=":
		fill = spec[i]
		align = spec[i + 1]
		i += 2
	elif i < n and spec[i] in "<>^=":
		align = spec[i]
		i += 1

	# [sign]
	if i < n and spec[i] in "+- ":
		sign = spec[i]
		i += 1

	# [#]
	if i < n and spec[i] == "#":
		alt = True
		i += 1

	# [0]
	if i < n and spec[i] == "0":
		zero = True
		i += 1

	# [width]
	start = i
	while i < n and spec[i].isdigit():
		i += 1
	if i > start:
		width = int(spec[start:i])

	# [grouping]
	if i < n and spec[i] in ",_":
		grouping = spec[i]
		i += 1

	# [.precision]
	if i < n and spec[i] == ".":
		i += 1
		start = i
		while i < n and spec[i].isdigit():
			i += 1
		if i > start:
			precision = int(spec[start:i])
		else:
			precision = 0

	# [type]
	if i < n:
		typ = spec[i]

	return {
		"fill": fill,
		"align": align,
		"sign": sign,
		"alt": alt,
		"zero": zero,
		"width": width,
		"grouping": grouping,
		"precision": precision,
		"type": typ,
	}


def apply_format_spec(value_expr: JSExpr, spec: str) -> JSExpr:
	spec_info = _parse_format_spec(spec)
	fill = spec_info["fill"] or " "
	align = spec_info["align"]
	sign = spec_info["sign"]
	alt = bool(spec_info["alt"])  # bool
	zero = bool(spec_info["zero"])  # bool
	width = spec_info["width"]
	grouping = spec_info["grouping"]
	precision = spec_info["precision"]
	typ = spec_info["type"]

	# Validate support
	allowed_types = {
		None,
		"s",
		"c",
		"d",
		"b",
		"o",
		"x",
		"X",
		"f",
		"F",
		"e",
		"E",
		"g",
		"G",
		"n",
		"%",
	}
	if typ not in allowed_types:
		raise JSCompilationError(f"Unsupported format type: {typ}")
	if grouping == "_":
		raise JSCompilationError("Unsupported grouping separator '_' in format spec")
	if align == "=" and typ in {None, "s"}:
		raise JSCompilationError("Alignment '=' is only supported for numeric types")

	# Escape backtick in fill if present
	fill_expr = JSString(fill)

	# Special-case minimal 'f' with only precision (no width/align/sign/etc.)
	if (
		typ in {"f", "F"}
		and precision is not None
		and align is None
		and sign is None
		and not alt
		and not zero
		and width is None
		and grouping is None
	):
		# Match prior behavior: x.toFixed(p)
		return JSMemberCall(value_expr, "toFixed", [JSNumber(precision)])
	# Build numeric/string representations
	base_expr: JSExpr
	prefix_expr: JSExpr = JSString("")
	if typ is None:
		# Default to string conversion
		base_expr = JSCall(JSIdentifier("String"), [value_expr])
	elif typ == "s":
		base_expr = JSCall(JSIdentifier("String"), [value_expr])
		if precision is not None:
			base_expr = JSMemberCall(
				base_expr, "slice", [JSNumber(0), JSNumber(precision)]
			)
	elif typ == "c":
		base_expr = JSCall(
			JSIdentifier("String.fromCharCode"),
			[JSCall(JSIdentifier("Number"), [value_expr])],
		)
	elif typ in {"d", "b", "o", "x", "X"}:
		num = JSCall(JSIdentifier("Number"), [value_expr])
		abs_num = JSCall(JSIdentifier("Math.abs"), [num])
		if typ == "d":
			digits: JSExpr = JSCall(
				JSIdentifier("String"),
				[JSCall(JSIdentifier("Math.trunc"), [abs_num])],
			)
		else:
			base_map = {"b": 2, "o": 8, "x": 16, "X": 16}
			digits = JSMemberCall(
				JSCall(JSIdentifier("Math.trunc"), [abs_num]),
				"toString",
				[JSNumber((base_map[typ]))],
			)
			if typ == "X":
				digits = JSMemberCall(digits, "toUpperCase", [])
		if alt and typ in {"b", "o", "x", "X"}:
			prefix = {"b": "0b", "o": "0o", "x": "0x", "X": "0X"}[typ]
			prefix_expr = JSString(prefix)
		# Apply grouping for decimal with comma
		if grouping == "," and typ == "d":
			# Use locale formatting for thousands separators
			digits = JSMemberCall(
				JSCall(JSIdentifier("Math.trunc"), [abs_num]),
				"toLocaleString",
				[JSString("en-US")],
			)
		base_expr = digits
	elif typ in {"f", "F", "e", "E", "g", "G", "n", "%"}:
		num = JSCall(JSIdentifier("Number"), [value_expr])
		abs_num = JSCall(JSIdentifier("Math.abs"), [num])
		if typ in {"f", "F"}:
			p = precision if precision is not None else 6
			if grouping == ",":
				s = JSMemberCall(
					abs_num,
					"toLocaleString",
					[
						JSString("en-US"),
						JSIdentifier(
							f"{{minimumFractionDigits: {p}, maximumFractionDigits: {p}}}"
						),
					],
				)
			else:
				s = JSMemberCall(abs_num, "toFixed", [JSNumber(p)])
		elif typ in {"e", "E"}:
			p = precision if precision is not None else 6
			s = JSMemberCall(abs_num, "toExponential", [JSNumber(p)])
			if typ == "E":
				s = JSMemberCall(s, "toUpperCase", [])
		elif typ in {"g", "G"}:
			p = precision if precision is not None else 6
			s = JSMemberCall(abs_num, "toPrecision", [JSNumber(p)])
			if typ == "G":
				s = JSMemberCall(s, "toUpperCase", [])
		elif typ == "n":
			if precision is None:
				s = JSMemberCall(abs_num, "toLocaleString", [JSString("en-US")])
			else:
				s = JSMemberCall(
					abs_num,
					"toLocaleString",
					[
						JSString("en-US"),
						JSIdentifier(
							f"{{minimumFractionDigits: {precision}, maximumFractionDigits: {precision}}}"
						),
					],
				)
		else:  # '%'
			p = precision if precision is not None else 6
			s = JSBinary(
				left=JSMemberCall(
					JSBinary(abs_num, "*", JSNumber(100)),
					"toFixed",
					[JSNumber(p)],
				),
				op="+",
				right=JSString("%"),
			)
		base_expr = s
	else:
		# Fallback to String conversion
		base_expr = JSCall(JSIdentifier("String"), [value_expr])

	# Apply sign for numeric types
	if typ in {"d", "b", "o", "x", "X", "f", "F", "e", "E", "g", "G", "n", "%"}:
		num = JSCall(JSIdentifier("Number"), [value_expr])
		cond = JSBinary(num, "<", JSNumber(0))
		if sign == "+":
			sign_expr = JSTertiary(cond, JSString("-"), JSString("+"))
		elif sign == " ":
			sign_expr = JSTertiary(cond, JSString("-"), JSString(" "))
		else:
			sign_expr = JSTertiary(cond, JSString("-"), JSString(""))
	else:
		sign_expr = JSString("")

	# Combine sign/prefix with base while avoiding unnecessary "" + chains
	def _is_empty_template(e: JSExpr) -> bool:
		return isinstance(e, JSTemplate) and len(e.parts) == 0

	def _is_empty_string(e: JSExpr) -> bool:
		return isinstance(e, JSString) and e.value == ""

	head: JSExpr | None = None
	# Prefer to include sign when present (numeric types), then prefix if non-empty
	if not _is_empty_template(sign_expr) and not _is_empty_string(sign_expr):
		head = sign_expr
	if not _is_empty_template(prefix_expr) and not _is_empty_string(prefix_expr):
		head = prefix_expr if head is None else JSBinary(head, "+", prefix_expr)

	combined: JSExpr
	if head is not None:
		combined = JSBinary(head, "+", base_expr)
	else:
		combined = base_expr

	# Width, alignment and zero-padding
	if width is not None and width > 0:
		if align == "^":
			# padStart to center: floor((width + len) / 2)
			half = JSCall(
				JSIdentifier("Math.floor"),
				[
					JSBinary(
						JSBinary(
							JSNumber(width),
							"+",
							JSMember(combined, "length"),
						),
						"/",
						JSNumber(2),
					)
				],
			)
			combined = JSMemberCall(
				JSMemberCall(combined, "padStart", [half, fill_expr]),
				"padEnd",
				[JSNumber(width), fill_expr],
			)
		elif align == "<":
			combined = JSMemberCall(combined, "padEnd", [JSNumber(width), fill_expr])
		elif align == "=":
			if typ in {
				"d",
				"b",
				"o",
				"x",
				"X",
				"f",
				"F",
				"e",
				"E",
				"g",
				"G",
				"n",
				"%",
			}:
				# Width should be like: width - ((head).length)
				# Prefer sign only for length when prefix is empty
				use_prefix_in_len = not _is_empty_template(
					prefix_expr
				) and not _is_empty_string(prefix_expr)
				head_for_len: JSExpr = (
					sign_expr
					if not use_prefix_in_len
					else JSBinary(sign_expr, "+", prefix_expr)
				)
				# Avoid double parentheses around sign template
				width_arg = JSIdentifier(f"{width} - ({head_for_len.emit()}).length")
				tail = base_expr
				combined = JSBinary(
					JSBinary(sign_expr, "+", prefix_expr),
					"+",
					JSMemberCall(
						tail,
						"padStart",
						[
							width_arg,
							fill_expr,
						],
					),
				)
			else:
				combined = JSMemberCall(
					combined, "padStart", [JSNumber(width), fill_expr]
				)
		else:
			pad_fill = fill_expr if not zero else JSString("0")
			if (
				zero
				and align is None
				and typ in {"d", "f", "F", "e", "E", "g", "G", "n", "%"}
			):
				head_only_sign: JSExpr = sign_expr
				tail = base_expr
				zero_padded = JSBinary(
					head_only_sign,
					"+",
					JSMemberCall(
						tail,
						"padStart",
						[
							JSBinary(
								JSNumber(width), "-", JSMember(head_only_sign, "length")
							),
							JSString("0"),
						],
					),
				)
				if not _is_empty_template(prefix_expr) and not _is_empty_string(
					prefix_expr
				):
					head_with_prefix = JSBinary(head_only_sign, "+", prefix_expr)
					zero_padded = JSBinary(
						head_with_prefix,
						"+",
						JSMemberCall(
							tail,
							"padStart",
							[
								JSBinary(
									JSNumber(width),
									"-",
									JSMember(head_with_prefix, "length"),
								),
								JSString("0"),
							],
						),
					)
				combined = zero_padded
			else:
				combined = JSMemberCall(
					combined, "padStart", [JSNumber(width), pad_fill]
				)

	return combined


def extract_formatspec(node: ast.AST):
	"""Return the literal string of a format spec if it is constant-only.

	For f-strings, ast.FormattedValue.format_spec can be a JoinedStr. We
	only support cases where the format spec is entirely constant text.
	"""
	if isinstance(node, ast.Constant) and isinstance(node.value, str):
		return node.value
	if isinstance(node, ast.JoinedStr):
		parts: list[str] = []
		for v in node.values:
			if isinstance(v, ast.Constant) and isinstance(v.value, str):
				parts.append(v.value)
			else:
				raise JSCompilationError("Format spec must be a constant string")
		return "".join(parts)
	raise JSCompilationError(
		f"Unexpected format spec: {ast.dump(node, include_attributes=False)}"
	)
