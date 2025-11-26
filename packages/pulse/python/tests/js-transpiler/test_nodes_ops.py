from pulse.javascript.nodes import (
	JSBinary,
	JSComma,
	JSIdentifier,
	JSMemberCall,
	JSString,
	JSUnary,
	JSUndefined,
)


def test_js_instanceof_basic():
	expr = JSBinary(JSIdentifier("a"), "instanceof", JSIdentifier("Map"))
	assert expr.emit() == "a instanceof Map"


def test_js_instanceof_with_logical_and():
	# a && b instanceof Map → no extra parens required
	expr = JSBinary(
		JSIdentifier("a"),
		"&&",
		JSBinary(JSIdentifier("b"), "instanceof", JSIdentifier("Map")),
	)
	assert expr.emit() == "a && b instanceof Map"


def test_js_typeof_basic():
	expr = JSUnary("typeof", JSIdentifier("x"))
	assert expr.emit() == "typeof x"


def test_js_typeof_in_comparison():
	# typeof x === "string" → unary binds tighter than comparison
	expr = JSBinary(JSUnary("typeof", JSIdentifier("x")), "===", JSString("string"))
	assert expr.emit() == 'typeof x === "string"'


def test_js_comma_expression_parenthesized():
	expr = JSComma([JSMemberCall(JSIdentifier("lst"), "reverse", []), JSUndefined()])
	assert expr.emit() == "(lst.reverse(), undefined)"


def test_js_in_basic():
	expr = JSBinary(JSIdentifier("key"), "in", JSIdentifier("obj"))
	assert expr.emit() == "key in obj"


def test_js_in_with_logical_and():
	# a && key in obj → no extra parens required
	expr = JSBinary(
		JSIdentifier("a"),
		"&&",
		JSBinary(JSIdentifier("key"), "in", JSIdentifier("obj")),
	)
	assert expr.emit() == "a && key in obj"


def test_js_in_with_typeof_comparison():
	# typeof x === "string" && key in obj
	expr = JSBinary(
		JSBinary(JSUnary("typeof", JSIdentifier("x")), "===", JSString("string")),
		"&&",
		JSBinary(JSIdentifier("key"), "in", JSIdentifier("obj")),
	)
	assert expr.emit() == 'typeof x === "string" && key in obj'
