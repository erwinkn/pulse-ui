"""
Tests for Node tree -> JavaScript code emission (nodes_v2.emit).

This module covers:
- Expression nodes (Literal, Identifier, Binary, etc.)
- Data nodes (ValueNode, ElementNode)
- Precedence and associativity
- JSX emission
- Edge cases (escaping, special characters)
"""

import datetime as dt

import pytest
from pulse.transpiler_v2.nodes import (
	EXPR_REGISTRY,
	UNDEFINED,
	Array,
	Arrow,
	Binary,
	Call,
	ElementNode,
	ExprNode,
	Identifier,
	Literal,
	Member,
	Object,
	PulseNode,
	Spread,
	Subscript,
	Template,
	Ternary,
	Unary,
	Undefined,
	ValueNode,
	emit,
)

# =============================================================================
# Literal Tests
# =============================================================================


class TestLiteralEmit:
	"""Test Literal node emission."""

	def test_null(self):
		assert emit(Literal(None)) == "null"

	def test_true(self):
		assert emit(Literal(True)) == "true"

	def test_false(self):
		assert emit(Literal(False)) == "false"

	def test_integer(self):
		assert emit(Literal(42)) == "42"
		assert emit(Literal(0)) == "0"
		assert emit(Literal(-123)) == "-123"

	def test_float(self):
		assert emit(Literal(3.14)) == "3.14"
		assert emit(Literal(-0.5)) == "-0.5"
		assert emit(Literal(1.0)) == "1.0"

	def test_string_simple(self):
		assert emit(Literal("hello")) == '"hello"'
		assert emit(Literal("")) == '""'

	def test_string_escaping(self):
		assert emit(Literal('say "hi"')) == '"say \\"hi\\""'
		assert emit(Literal("line1\nline2")) == '"line1\\nline2"'
		assert emit(Literal("tab\there")) == '"tab\\there"'
		assert emit(Literal("back\\slash")) == '"back\\\\slash"'

	def test_string_special_chars(self):
		assert emit(Literal("\r")) == '"\\r"'
		assert emit(Literal("\b")) == '"\\b"'
		assert emit(Literal("\f")) == '"\\f"'
		assert emit(Literal("\v")) == '"\\v"'
		assert emit(Literal("\x00")) == '"\\x00"'

	def test_string_unicode_line_separators(self):
		# These need escaping in JS strings
		assert emit(Literal("\u2028")) == '"\\u2028"'
		assert emit(Literal("\u2029")) == '"\\u2029"'


# =============================================================================
# Identifier Tests
# =============================================================================


class TestIdentifierEmit:
	"""Test Identifier node emission."""

	def test_simple(self):
		assert emit(Identifier("x")) == "x"
		assert emit(Identifier("myVar")) == "myVar"
		assert emit(Identifier("_private")) == "_private"
		assert emit(Identifier("$jquery")) == "$jquery"

	def test_reserved_words(self):
		# JS reserved words are still valid identifiers here
		assert emit(Identifier("class")) == "class"
		assert emit(Identifier("function")) == "function"


# =============================================================================
# Array Tests
# =============================================================================


class TestArrayEmit:
	"""Test Array node emission."""

	def test_empty(self):
		assert emit(Array([])) == "[]"

	def test_single_element(self):
		assert emit(Array([Literal(1)])) == "[1]"

	def test_multiple_elements(self):
		assert emit(Array([Literal(1), Literal(2), Literal(3)])) == "[1, 2, 3]"

	def test_mixed_types(self):
		arr = Array([Literal(1), Literal("hello"), Literal(True), Literal(None)])
		assert emit(arr) == '[1, "hello", true, null]'

	def test_nested_arrays(self):
		arr = Array([Array([Literal(1), Literal(2)]), Array([Literal(3)])])
		assert emit(arr) == "[[1, 2], [3]]"

	def test_with_expressions(self):
		arr = Array([Identifier("x"), Binary(Identifier("a"), "+", Identifier("b"))])
		assert emit(arr) == "[x, a + b]"


# =============================================================================
# Object Tests
# =============================================================================


class TestObjectEmit:
	"""Test Object node emission."""

	def test_empty(self):
		assert emit(Object([])) == "{}"

	def test_single_prop(self):
		assert emit(Object([("key", Literal("value"))])) == '{"key": "value"}'

	def test_multiple_props(self):
		obj = Object([("a", Literal(1)), ("b", Literal(2))])
		assert emit(obj) == '{"a": 1, "b": 2}'

	def test_string_key_escaping(self):
		obj = Object([('say "hi"', Literal(1))])
		assert emit(obj) == '{"say \\"hi\\"": 1}'

	def test_nested_object(self):
		obj = Object([("outer", Object([("inner", Literal(42))]))])
		assert emit(obj) == '{"outer": {"inner": 42}}'


# =============================================================================
# Member Access Tests
# =============================================================================


class TestMemberEmit:
	"""Test Member node emission."""

	def test_simple(self):
		assert emit(Member(Identifier("obj"), "prop")) == "obj.prop"

	def test_chained(self):
		inner = Member(Identifier("a"), "b")
		outer = Member(inner, "c")
		assert emit(outer) == "a.b.c"

	def test_on_call_result(self):
		call = Call(Identifier("getObj"), [])
		assert emit(Member(call, "prop")) == "getObj().prop"

	def test_on_array(self):
		arr = Array([Literal(1), Literal(2)])
		assert emit(Member(arr, "length")) == "[1, 2].length"


# =============================================================================
# Subscript Access Tests
# =============================================================================


class TestSubscriptEmit:
	"""Test Subscript node emission."""

	def test_string_key(self):
		assert emit(Subscript(Identifier("obj"), Literal("key"))) == 'obj["key"]'

	def test_number_key(self):
		assert emit(Subscript(Identifier("arr"), Literal(0))) == "arr[0]"

	def test_expression_key(self):
		assert emit(Subscript(Identifier("arr"), Identifier("i"))) == "arr[i]"

	def test_chained(self):
		inner = Subscript(Identifier("a"), Literal(0))
		outer = Subscript(inner, Literal(1))
		assert emit(outer) == "a[0][1]"

	def test_mixed_with_member(self):
		member = Member(Identifier("obj"), "arr")
		subscript = Subscript(member, Literal(0))
		assert emit(subscript) == "obj.arr[0]"


# =============================================================================
# Call Expression Tests
# =============================================================================


class TestCallEmit:
	"""Test Call node emission."""

	def test_no_args(self):
		assert emit(Call(Identifier("fn"), [])) == "fn()"

	def test_single_arg(self):
		assert emit(Call(Identifier("fn"), [Literal(1)])) == "fn(1)"

	def test_multiple_args(self):
		call = Call(Identifier("fn"), [Literal(1), Literal("hello"), Identifier("x")])
		assert emit(call) == 'fn(1, "hello", x)'

	def test_method_call(self):
		member = Member(Identifier("obj"), "method")
		call = Call(member, [Literal(42)])
		assert emit(call) == "obj.method(42)"

	def test_chained_calls(self):
		inner = Call(Identifier("a"), [])
		outer = Call(inner, [Literal(1)])
		assert emit(outer) == "a()(1)"

	def test_call_on_array(self):
		arr = Array([Identifier("fn")])
		subscript = Subscript(arr, Literal(0))
		call = Call(subscript, [])
		assert emit(call) == "[fn][0]()"


# =============================================================================
# Unary Expression Tests
# =============================================================================


class TestUnaryEmit:
	"""Test Unary node emission."""

	def test_negation(self):
		assert emit(Unary("-", Identifier("x"))) == "-x"

	def test_positive(self):
		assert emit(Unary("+", Identifier("x"))) == "+x"

	def test_logical_not(self):
		assert emit(Unary("!", Identifier("x"))) == "!x"

	def test_double_not(self):
		inner = Unary("!", Identifier("x"))
		outer = Unary("!", inner)
		assert emit(outer) == "!!x"

	def test_typeof(self):
		assert emit(Unary("typeof", Identifier("x"))) == "typeof x"

	def test_await(self):
		assert emit(Unary("await", Identifier("promise"))) == "await promise"

	def test_void(self):
		assert emit(Unary("void", Literal(0))) == "void 0"

	def test_delete(self):
		member = Member(Identifier("obj"), "prop")
		assert emit(Unary("delete", member)) == "delete obj.prop"


# =============================================================================
# Binary Expression Tests
# =============================================================================


class TestBinaryEmit:
	"""Test Binary node emission."""

	def test_addition(self):
		assert emit(Binary(Identifier("a"), "+", Identifier("b"))) == "a + b"

	def test_subtraction(self):
		assert emit(Binary(Identifier("a"), "-", Identifier("b"))) == "a - b"

	def test_multiplication(self):
		assert emit(Binary(Identifier("a"), "*", Identifier("b"))) == "a * b"

	def test_division(self):
		assert emit(Binary(Identifier("a"), "/", Identifier("b"))) == "a / b"

	def test_modulo(self):
		assert emit(Binary(Identifier("a"), "%", Identifier("b"))) == "a % b"

	def test_exponentiation(self):
		assert emit(Binary(Identifier("a"), "**", Identifier("b"))) == "a ** b"

	def test_comparison_operators(self):
		assert emit(Binary(Identifier("a"), "===", Identifier("b"))) == "a === b"
		assert emit(Binary(Identifier("a"), "!==", Identifier("b"))) == "a !== b"
		assert emit(Binary(Identifier("a"), "<", Identifier("b"))) == "a < b"
		assert emit(Binary(Identifier("a"), "<=", Identifier("b"))) == "a <= b"
		assert emit(Binary(Identifier("a"), ">", Identifier("b"))) == "a > b"
		assert emit(Binary(Identifier("a"), ">=", Identifier("b"))) == "a >= b"

	def test_logical_operators(self):
		assert emit(Binary(Identifier("a"), "&&", Identifier("b"))) == "a && b"
		assert emit(Binary(Identifier("a"), "||", Identifier("b"))) == "a || b"
		assert emit(Binary(Identifier("a"), "??", Identifier("b"))) == "a ?? b"

	def test_instanceof(self):
		assert emit(Binary(Identifier("x"), "instanceof", Identifier("Array"))) == (
			"x instanceof Array"
		)

	def test_in_operator(self):
		assert emit(Binary(Literal("key"), "in", Identifier("obj"))) == '"key" in obj'


# =============================================================================
# Precedence Tests
# =============================================================================


class TestPrecedenceEmit:
	"""Test operator precedence handling."""

	def test_add_then_multiply_needs_parens(self):
		# (a + b) * c - inner needs parens because + binds less than *
		add = Binary(Identifier("a"), "+", Identifier("b"))
		mult = Binary(add, "*", Identifier("c"))
		assert emit(mult) == "(a + b) * c"

	def test_multiply_then_add_no_parens(self):
		# a * b + c - no parens needed
		mult = Binary(Identifier("a"), "*", Identifier("b"))
		add = Binary(mult, "+", Identifier("c"))
		assert emit(add) == "a * b + c"

	def test_nested_same_precedence_left_assoc(self):
		# a + b + c - left associative, no parens needed
		inner = Binary(Identifier("a"), "+", Identifier("b"))
		outer = Binary(inner, "+", Identifier("c"))
		assert emit(outer) == "a + b + c"

	def test_nested_same_precedence_right_needs_parens(self):
		# a + (b + c) on the right - needs parens for clarity
		inner = Binary(Identifier("b"), "+", Identifier("c"))
		outer = Binary(Identifier("a"), "+", inner)
		assert emit(outer) == "a + (b + c)"

	def test_exponentiation_right_associative(self):
		# a ** (b ** c) - right associative, no parens on right
		inner = Binary(Identifier("b"), "**", Identifier("c"))
		outer = Binary(Identifier("a"), "**", inner)
		assert emit(outer) == "a ** b ** c"

	def test_exponentiation_left_needs_parens(self):
		# (a ** b) ** c - needs parens on left due to right-associativity
		inner = Binary(Identifier("a"), "**", Identifier("b"))
		outer = Binary(inner, "**", Identifier("c"))
		assert emit(outer) == "(a ** b) ** c"

	def test_exponentiation_with_unary_minus(self):
		# (-x) ** 2 - unary on left of ** needs parens
		unary = Unary("-", Identifier("x"))
		exp = Binary(unary, "**", Literal(2))
		assert emit(exp) == "(-x) ** 2"

	def test_unary_in_binary(self):
		# -a + b - unary doesn't need parens
		neg = Unary("-", Identifier("a"))
		add = Binary(neg, "+", Identifier("b"))
		assert emit(add) == "-a + b"

	def test_logical_precedence(self):
		# a || b && c - && binds tighter
		and_expr = Binary(Identifier("b"), "&&", Identifier("c"))
		or_expr = Binary(Identifier("a"), "||", and_expr)
		assert emit(or_expr) == "a || b && c"

		# (a || b) && c - needs parens
		or_expr2 = Binary(Identifier("a"), "||", Identifier("b"))
		and_expr2 = Binary(or_expr2, "&&", Identifier("c"))
		assert emit(and_expr2) == "(a || b) && c"


# =============================================================================
# Ternary Expression Tests
# =============================================================================


class TestTernaryEmit:
	"""Test Ternary node emission."""

	def test_simple(self):
		tern = Ternary(Identifier("cond"), Literal(1), Literal(2))
		assert emit(tern) == "cond ? 1 : 2"

	def test_with_expressions(self):
		cond = Binary(Identifier("x"), ">", Literal(0))
		then = Literal("positive")
		else_ = Literal("non-positive")
		tern = Ternary(cond, then, else_)
		assert emit(tern) == 'x > 0 ? "positive" : "non-positive"'

	def test_nested_in_binary_gets_parens(self):
		# When ternary is operand of binary, it needs parens
		tern = Ternary(Identifier("c"), Literal(1), Literal(2))
		add = Binary(tern, "+", Literal(3))
		assert emit(add) == "(c ? 1 : 2) + 3"

	def test_ternary_in_member_access(self):
		tern = Ternary(Identifier("c"), Identifier("a"), Identifier("b"))
		member = Member(tern, "prop")
		assert emit(member) == "(c ? a : b).prop"


# =============================================================================
# Arrow Function Tests
# =============================================================================


class TestArrowEmit:
	"""Test Arrow node emission."""

	def test_no_params(self):
		arrow = Arrow([], Literal(42))
		assert emit(arrow) == "() => 42"

	def test_single_param(self):
		arrow = Arrow(["x"], Identifier("x"))
		assert emit(arrow) == "x => x"

	def test_multiple_params(self):
		arrow = Arrow(["x", "y"], Binary(Identifier("x"), "+", Identifier("y")))
		assert emit(arrow) == "(x, y) => x + y"

	def test_expression_body(self):
		body = Object([("x", Identifier("x"))])
		arrow = Arrow(["x"], body)
		# Object literal body works because emit just outputs the object
		assert emit(arrow) == 'x => {"x": x}'

	def test_nested_arrow(self):
		inner = Arrow(["y"], Identifier("y"))
		outer = Arrow(["x"], inner)
		assert emit(outer) == "x => y => y"


# =============================================================================
# Template Literal Tests
# =============================================================================


class TestTemplateEmit:
	"""Test Template node emission."""

	def test_no_interpolation(self):
		tmpl = Template(["hello world"])
		assert emit(tmpl) == "`hello world`"

	def test_simple_interpolation(self):
		tmpl = Template(["Hello ", Identifier("name"), "!"])
		assert emit(tmpl) == "`Hello ${name}!`"

	def test_multiple_interpolations(self):
		tmpl = Template(
			["", Identifier("a"), " + ", Identifier("b"), " = ", Identifier("c"), ""]
		)
		assert emit(tmpl) == "`${a} + ${b} = ${c}`"

	def test_expression_interpolation(self):
		expr = Binary(Identifier("x"), "+", Literal(1))
		tmpl = Template(["Result: ", expr, ""])
		assert emit(tmpl) == "`Result: ${x + 1}`"

	def test_escaping_backticks(self):
		tmpl = Template(["code: `console.log()`"])
		assert emit(tmpl) == "`code: \\`console.log()\\``"

	def test_escaping_dollar_brace(self):
		tmpl = Template(["literal: ${notInterpolated}"])
		assert emit(tmpl) == "`literal: \\${notInterpolated}`"

	def test_newlines(self):
		tmpl = Template(["line1\nline2"])
		assert emit(tmpl) == "`line1\\nline2`"


# =============================================================================
# Spread Operator Tests
# =============================================================================


class TestSpreadEmit:
	"""Test Spread node emission."""

	def test_spread_identifier(self):
		assert emit(Spread(Identifier("arr"))) == "...arr"

	def test_spread_in_array(self):
		arr = Array([Literal(1), Spread(Identifier("rest")), Literal(2)])
		assert emit(arr) == "[1, ...rest, 2]"

	def test_spread_call_result(self):
		call = Call(Identifier("getItems"), [])
		spread = Spread(call)
		assert emit(spread) == "...getItems()"


# =============================================================================
# ValueNode Tests
# =============================================================================


class TestValueNodeEmit:
	"""Test ValueNode emission (Python values to JS literals)."""

	def test_none(self):
		assert emit(ValueNode(None)) == "null"

	def test_bool(self):
		assert emit(ValueNode(True)) == "true"
		assert emit(ValueNode(False)) == "false"

	def test_numbers(self):
		assert emit(ValueNode(42)) == "42"
		assert emit(ValueNode(3.14)) == "3.14"

	def test_string(self):
		assert emit(ValueNode("hello")) == '"hello"'
		assert emit(ValueNode('say "hi"')) == '"say \\"hi\\""'

	def test_list(self):
		assert emit(ValueNode([1, 2, 3])) == "[1, 2, 3]"
		assert emit(ValueNode(["a", "b"])) == '["a", "b"]'

	def test_nested_list(self):
		assert emit(ValueNode([[1, 2], [3, 4]])) == "[[1, 2], [3, 4]]"

	def test_dict(self):
		assert emit(ValueNode({"a": 1, "b": 2})) == '{"a": 1, "b": 2}'

	def test_nested_dict(self):
		assert emit(ValueNode({"outer": {"inner": 42}})) == '{"outer": {"inner": 42}}'

	def test_mixed_structures(self):
		value = {"items": [1, 2, 3], "config": {"enabled": True}}
		assert (
			emit(ValueNode(value))
			== '{"items": [1, 2, 3], "config": {"enabled": true}}'
		)

	def test_datetime(self):
		# 2024-01-15 12:30:00 UTC
		dt_value = dt.datetime(2024, 1, 15, 12, 30, 0, tzinfo=dt.timezone.utc)
		result = emit(ValueNode(dt_value))
		assert result.startswith("new Date(")
		assert result.endswith(")")

	def test_set(self):
		# Sets become new Set([...])
		result = emit(ValueNode({1, 2, 3}))
		assert result.startswith("new Set([")
		assert result.endswith("])")

	def test_unsupported_type_raises(self):
		class CustomClass:
			pass

		with pytest.raises(TypeError, match="Cannot emit CustomClass"):
			emit(ValueNode(CustomClass()))


# =============================================================================
# ElementNode (JSX) Tests
# =============================================================================


class TestElementNodeEmit:
	"""Test ElementNode JSX emission."""

	def test_self_closing_no_props(self):
		elem = ElementNode("div")
		assert emit(elem) == "<div />"

	def test_self_closing_with_props(self):
		elem = ElementNode("img", {"src": "/img.png", "alt": "Image"})
		result = emit(elem)
		assert 'src="/img.png"' in result
		assert 'alt="Image"' in result
		assert result.endswith(" />")

	def test_with_text_child(self):
		elem = ElementNode("p", children=["Hello world"])
		assert emit(elem) == "<p>Hello world</p>"

	def test_with_nested_element(self):
		child = ElementNode("span", children=["inner"])
		parent = ElementNode("div", children=[child])
		assert emit(parent) == "<div><span>inner</span></div>"

	def test_with_multiple_children(self):
		elem = ElementNode(
			"div", children=["Hello ", ElementNode("strong", children=["world"])]
		)
		assert emit(elem) == "<div>Hello <strong>world</strong></div>"

	def test_with_key(self):
		elem = ElementNode("li", key="item-1", children=["Item 1"])
		result = emit(elem)
		assert 'key="item-1"' in result
		assert result.startswith("<li")

	def test_props_with_primitives(self):
		elem = ElementNode(
			"input",
			{"disabled": True, "value": 42, "hidden": False, "placeholder": None},
		)
		result = emit(elem)
		assert "disabled={true}" in result
		assert "value={42}" in result
		assert "hidden={false}" in result
		assert "placeholder={null}" in result

	def test_props_with_expression(self):
		elem = ElementNode("button", {"onClick": Identifier("handleClick")})
		result = emit(elem)
		assert "onClick={handleClick}" in result

	def test_props_with_value_node(self):
		elem = ElementNode("div", {"data": ValueNode({"a": 1, "b": 2})})
		result = emit(elem)
		assert 'data={{"a": 1, "b": 2}}' in result

	def test_jsx_text_escaping(self):
		elem = ElementNode("p", children=["<script>alert('xss')</script>"])
		result = emit(elem)
		assert "&lt;script&gt;" in result
		assert "&lt;/script&gt;" in result

	def test_jsx_attribute_escaping(self):
		elem = ElementNode("div", {"title": 'say "hello"'})
		result = emit(elem)
		assert 'title="say &quot;hello&quot;"' in result

	def test_child_number(self):
		elem = ElementNode("span", children=[42])
		assert emit(elem) == "<span>{42}</span>"

	def test_child_expression(self):
		elem = ElementNode("span", children=[Identifier("count")])
		assert emit(elem) == "<span>{count}</span>"

	def test_child_none_and_bool_ignored(self):
		elem = ElementNode("div", children=[None, True, False, "visible"])
		assert emit(elem) == "<div>visible</div>"


class TestElementNodeWithChildren:
	"""Test ElementNode.with_children method."""

	def test_with_children_simple(self):
		div = ElementNode("div")
		result = div.with_children(["hello"])
		assert emit(result) == "<div>hello</div>"

	def test_with_children_preserves_tag(self):
		span = ElementNode("span")
		result = span.with_children(["text"])
		assert emit(result) == "<span>text</span>"

	def test_with_children_preserves_props(self):
		div = ElementNode("div", props={"class": Literal("foo")})
		result = div.with_children(["content"])
		assert emit(result) == '<div class="foo">content</div>'

	def test_with_children_preserves_key(self):
		li = ElementNode("li", key="item-1")
		result = li.with_children(["text"])
		output = emit(result)
		assert 'key="item-1"' in output
		assert "text" in output

	def test_with_children_multiple(self):
		div = ElementNode("div")
		result = div.with_children(["a", "b", "c"])
		assert emit(result) == "<div>abc</div>"

	def test_with_children_nested_elements(self):
		div = ElementNode("div")
		span = ElementNode("span", children=["inner"])
		result = div.with_children([span])
		assert emit(result) == "<div><span>inner</span></div>"

	def test_with_children_expression_nodes(self):
		div = ElementNode("div")
		result = div.with_children([Identifier("x"), Literal(42)])
		assert emit(result) == "<div>{x}{42}</div>"

	def test_with_children_errors_if_children_exist(self):
		div = ElementNode("div", children=["existing"])
		with pytest.raises(ValueError, match="already has children"):
			div.with_children(["more"])

	def test_with_children_returns_new_element(self):
		original = ElementNode("div")
		modified = original.with_children(["child"])
		# Original unchanged
		assert original.children is None
		# New element has children
		assert modified.children == ["child"]

	def test_with_children_empty_list_allowed(self):
		div = ElementNode("div")
		result = div.with_children([])
		# Empty children list is still set (but emits as self-closing)
		assert result.children == []
		assert emit(result) == "<div />"


# =============================================================================
# Fragment Tests
# =============================================================================


class TestFragmentEmit:
	"""Test Fragment (empty tag) emission."""

	def test_empty_fragment(self):
		frag = ElementNode("", children=[])
		assert emit(frag) == "<></>"

	def test_fragment_with_children(self):
		frag = ElementNode(
			"",
			children=[
				ElementNode("p", children=["First"]),
				ElementNode("p", children=["Second"]),
			],
		)
		assert emit(frag) == "<><p>First</p><p>Second</p></>"

	def test_fragment_with_key(self):
		frag = ElementNode(
			"", key="frag-1", children=[ElementNode("span", children=["content"])]
		)
		result = emit(frag)
		assert result.startswith('<Fragment key="frag-1">')
		assert result.endswith("</Fragment>")


# =============================================================================
# Client Component Tests
# =============================================================================


class TestClientComponentEmit:
	"""Test client component ($$ prefix) emission."""

	def test_client_component_tag(self):
		elem = ElementNode("$$MyComponent")
		assert emit(elem) == "<MyComponent />"

	def test_client_component_with_props(self):
		elem = ElementNode("$$Button", {"variant": "primary", "size": "lg"})
		result = emit(elem)
		assert result.startswith("<Button ")
		assert 'variant="primary"' in result
		assert 'size="lg"' in result

	def test_client_component_with_children(self):
		elem = ElementNode(
			"$$Card", children=[ElementNode("p", children=["Card content"])]
		)
		assert emit(elem) == "<Card><p>Card content</p></Card>"


# =============================================================================
# Spread Props Tests
# =============================================================================


class TestSpreadPropsEmit:
	"""Test spread props in JSX."""

	def test_spread_in_props(self):
		elem = ElementNode("div", {"spreadProps": Spread(Identifier("props"))})
		result = emit(elem)
		assert "{...props}" in result

	def test_spread_call_in_props(self):
		call = Call(Identifier("getProps"), [])
		elem = ElementNode("div", {"spreadCall": Spread(call)})
		result = emit(elem)
		assert "{...getProps()}" in result


# =============================================================================
# PulseNode Error Tests
# =============================================================================


class TestPulseNodeEmitError:
	"""Test that PulseNode emission raises appropriate errors."""

	def test_pulse_node_in_emit_raises(self):
		def my_component():
			pass

		node = PulseNode(fn=my_component)
		with pytest.raises(TypeError, match="Cannot transpile PulseNode"):
			emit(node)

	def test_pulse_node_as_child_raises(self):
		def child_component():
			pass

		pulse_child = PulseNode(fn=child_component)
		elem = ElementNode("div", children=[pulse_child])
		with pytest.raises(TypeError, match="Cannot transpile PulseNode"):
			emit(elem)


# =============================================================================
# Nested Element Prop Tests
# =============================================================================


class TestNestedElementPropEmit:
	"""Test ElementNode as prop value (render props)."""

	def test_element_as_prop(self):
		icon = ElementNode("Icon", {"name": "check"})
		elem = ElementNode("Button", {"icon": icon})
		result = emit(elem)
		assert "icon={<Icon" in result


# =============================================================================
# Callable Prop Error Tests
# =============================================================================


class TestCallablePropError:
	"""Test that callable props raise appropriate errors."""

	def test_callable_prop_raises(self):
		def handler():
			pass

		elem = ElementNode("button", {"onClick": handler})  # pyright: ignore[reportArgumentType]
		with pytest.raises(TypeError, match="Cannot emit callable"):
			emit(elem)


# =============================================================================
# Complex Expression Tests
# =============================================================================


class TestComplexExpressionEmit:
	"""Test complex nested expressions."""

	def test_chained_method_calls(self):
		# arr.filter(x => x > 0).map(x => x * 2)
		filter_arrow = Arrow(["x"], Binary(Identifier("x"), ">", Literal(0)))
		filter_call = Call(Member(Identifier("arr"), "filter"), [filter_arrow])
		map_arrow = Arrow(["x"], Binary(Identifier("x"), "*", Literal(2)))
		map_call = Call(Member(filter_call, "map"), [map_arrow])
		assert emit(map_call) == "arr.filter(x => x > 0).map(x => x * 2)"

	def test_ternary_in_template(self):
		tern = Ternary(Identifier("isAdmin"), Literal("Admin"), Literal("User"))
		tmpl = Template(["Role: ", tern, ""])
		assert emit(tmpl) == '`Role: ${isAdmin ? "Admin" : "User"}`'

	def test_call_with_spread_and_regular_args(self):
		call = Call(
			Identifier("fn"),
			[Literal(1), Spread(Identifier("args")), Literal(2)],
		)
		assert emit(call) == "fn(1, ...args, 2)"

	def test_binary_in_subscript(self):
		idx = Binary(Identifier("i"), "+", Literal(1))
		sub = Subscript(Identifier("arr"), idx)
		assert emit(sub) == "arr[i + 1]"

	def test_deeply_nested_jsx(self):
		inner = ElementNode("span", {"className": "inner"}, ["Deep"])
		middle = ElementNode("div", {"className": "middle"}, [inner])
		outer = ElementNode("section", {"className": "outer"}, [middle])
		result = emit(outer)
		assert '<section className="outer">' in result
		assert '<div className="middle">' in result
		assert '<span className="inner">Deep</span>' in result


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCasesEmit:
	"""Test edge cases and boundary conditions."""

	def test_empty_string_literal(self):
		assert emit(Literal("")) == '""'

	def test_zero_values(self):
		assert emit(Literal(0)) == "0"
		assert emit(Literal(0.0)) == "0.0"

	def test_negative_numbers(self):
		assert emit(Literal(-42)) == "-42"
		assert emit(Literal(-3.14)) == "-3.14"

	def test_scientific_notation(self):
		# Python's str() handles this
		assert emit(Literal(1e10)) == "10000000000.0"

	def test_unicode_in_string(self):
		assert emit(Literal("こんにちは")) == '"こんにちは"'
		assert emit(Literal("emoji: 🎉")) == '"emoji: 🎉"'

	def test_long_identifier(self):
		long_name = "x" * 100
		assert emit(Identifier(long_name)) == long_name

	def test_many_array_elements(self):
		elements = [Literal(i) for i in range(10)]
		arr = Array(elements)
		assert emit(arr) == "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]"

	def test_datetime_child(self):
		dt_value = dt.datetime(2024, 1, 15, 12, 30, 0, tzinfo=dt.timezone.utc)
		elem = ElementNode("span", children=[dt_value])
		result = emit(elem)
		assert "{new Date(" in result


# =============================================================================
# Undefined Tests
# =============================================================================


class TestUndefinedEmit:
	"""Test Undefined node emission."""

	def test_undefined(self):
		assert emit(Undefined()) == "undefined"

	def test_undefined_singleton(self):
		assert emit(UNDEFINED) == "undefined"

	def test_undefined_in_array(self):
		arr = Array([Literal(1), Undefined(), Literal(3)])
		assert emit(arr) == "[1, undefined, 3]"

	def test_undefined_vs_null(self):
		"""Undefined and Literal(None) emit differently."""
		assert emit(Undefined()) == "undefined"
		assert emit(Literal(None)) == "null"


# =============================================================================
# ExprNode.of / ExprNode.register Tests
# =============================================================================


class TestExprNodeOf:
	"""Test ExprNode.of() conversion."""

	def test_passthrough_expr_node(self):
		"""ExprNode.of returns ExprNode as-is."""
		lit = Literal(42)
		assert ExprNode.of(lit) is lit

	def test_string(self):
		"""ExprNode.of converts string to Literal."""
		result = ExprNode.of("hello")
		assert isinstance(result, Literal)
		assert result.value == "hello"

	def test_int(self):
		result = ExprNode.of(42)
		assert isinstance(result, Literal)
		assert result.value == 42

	def test_float(self):
		result = ExprNode.of(3.14)
		assert isinstance(result, Literal)
		assert result.value == 3.14

	def test_bool_true(self):
		result = ExprNode.of(True)
		assert isinstance(result, Literal)
		assert result.value is True

	def test_bool_false(self):
		result = ExprNode.of(False)
		assert isinstance(result, Literal)
		assert result.value is False

	def test_none(self):
		result = ExprNode.of(None)
		assert isinstance(result, Literal)
		assert result.value is None

	def test_list(self):
		result = ExprNode.of([1, 2, 3])
		assert isinstance(result, Array)
		assert len(result.elements) == 3
		assert all(isinstance(e, Literal) for e in result.elements)

	def test_tuple(self):
		result = ExprNode.of((1, 2))
		assert isinstance(result, Array)
		assert len(result.elements) == 2

	def test_dict(self):
		result = ExprNode.of({"a": 1, "b": 2})
		assert isinstance(result, Object)
		assert len(result.props) == 2

	def test_set(self):
		from pulse.transpiler_v2.nodes import New

		result = ExprNode.of({1, 2})
		assert isinstance(result, New)
		assert emit(result).startswith("new Set(")

	def test_nested_collections(self):
		result = ExprNode.of({"items": [1, 2], "count": 2})
		assert isinstance(result, Object)

	def test_invalid_type_raises(self):
		with pytest.raises(TypeError, match="Cannot convert"):
			ExprNode.of(object())


class TestExprNodeRegister:
	"""Test ExprNode.register() and registry lookup."""

	def test_register_expr_node(self):
		"""Register an ExprNode directly."""
		prev_registry = dict(EXPR_REGISTRY)
		try:
			EXPR_REGISTRY.clear()
			val = object()
			expr = Identifier("test")
			ExprNode.register(val, expr)
			assert ExprNode.of(val) is expr
		finally:
			EXPR_REGISTRY.clear()
			EXPR_REGISTRY.update(prev_registry)

	def test_register_callable(self):
		"""Register a callable - wraps in Transformer."""
		from pulse.transpiler_v2.nodes import Transformer

		prev_registry = dict(EXPR_REGISTRY)
		try:
			EXPR_REGISTRY.clear()
			val = object()
			ExprNode.register(val, lambda x, ctx: Literal(1))  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
			result = EXPR_REGISTRY.get(id(val))
			assert isinstance(result, Transformer)
		finally:
			EXPR_REGISTRY.clear()
			EXPR_REGISTRY.update(prev_registry)

	def test_registered_takes_priority(self):
		"""Registered values take priority over type conversion."""
		prev_registry = dict(EXPR_REGISTRY)
		try:
			EXPR_REGISTRY.clear()
			# Register the string "hello" to return a specific identifier
			hello = "hello"
			custom = Identifier("custom")
			ExprNode.register(hello, custom)
			# Since strings are interned, this should find it
			assert ExprNode.of(hello) is custom
		finally:
			EXPR_REGISTRY.clear()
			EXPR_REGISTRY.update(prev_registry)
