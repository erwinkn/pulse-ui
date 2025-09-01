from pulse.javascript.nodes import (
    JSBinary,
    JSIdentifier,
    JSLogicalChain,
    JSMemberCall,
    JSNumber,
    JSString,
)
from pulse.javascript.transpiler import compile_python_to_js


def test_exponentiation_right_associative():
    def f(a, b, c):
        return a**b**c

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b, c){
return a ** b ** c;
}"""
    )


def test_exponentiation_with_unary_left_operand_parenthesized():
    def f(x):
        return (-x) ** 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return (-x) ** 2;
}"""
    )


def test_multiplicative_additive_precedence():
    def f(x, y, z):
        return x + y * z

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x, y, z){
return x + y * z;
}"""
    )


def test_additive_multiplicative_precedence_other_order():
    def f(x, y, z):
        return x * y + z

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x, y, z){
return x * y + z;
}"""
    )


def test_subtraction_left_associative():
    def f(a, b, c):
        return a - b - c

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b, c){
return a - b - c;
}"""
    )


def test_logical_and_or_precedence():
    def f(a, b, c):
        return a and b or c

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b, c){
return a && b || c;
}"""
    )


def test_or_and_precedence():
    def f(a, b, c):
        return a or b and c

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b, c){
return a || b && c;
}"""
    )


def test_nullish_with_or_requires_parens_on_nullish_side():
    code = JSLogicalChain(
        "||",
        [
            JSBinary(
                JSMemberCall(JSIdentifier("d"), "get", [JSString("k")]),
                "??",
                JSNumber(0),
            ),
            JSIdentifier("b"),
        ],
    ).emit()
    assert code == '(d.get("k") ?? 0) || b'


def test_ternary_parenthesized_in_binary_context():
    def f(a, b, c, x):
        return x + (b if a else c)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b, c, x){
return x + (a ? b : c);
}"""
    )


def test_member_access_parens_on_complex_receiver():
    def f(a, b):
        return (a + b).x

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return (a + b).x;
}"""
    )


def test_subscript_parens_on_complex_receiver():
    def f(a, b):
        return (a + b)[0]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return (a + b)[0];
}"""
    )


def test_call_parens_on_complex_callee():
    def f(a, b):
        return (a + b)(1)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return (a + b)(1);
}"""
    )


def test_new_expression_in_member_call_no_extra_parens():
    def f(xs):
        return ({x for x in xs}).has(1)  # type: ignore

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return new Set(xs.map(x => x)).has(1);
}"""
    )


def test_new_expression_in_logical_or_chain():
    def f(xs):
        return ({x for x in xs}) or []

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return new Set(xs.map(x => x)) || [];
}"""
    )


def test_new_expression_as_return_value():
    def f(xs):
        return {x for x in xs}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return new Set(xs.map(x => x));
}"""
    )
