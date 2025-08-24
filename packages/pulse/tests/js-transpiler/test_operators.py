import warnings
import pytest
from pulse.javascript import compile_python_to_js


def test_assign_and_return():
    def f(x):
        y = x + 1
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = x + 1;
return y;
}"""
    )


def test_annassign_and_return():
    def f(x: int):
        y: int = x
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = x;
return y;
}"""
    )


def test_reassignment_without_let():
    def f(x):
        y = x + 1
        y = y + 2
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = x + 1;
y = y + 2;
return y;
}"""
    )


def test_param_reassignment():
    def f(x):
        x = x + 1
        return x

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
x = x + 1;
return x;
}"""
    )


def test_augassign():
    def f(x):
        y = 1
        y += x
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = 1;
y += x;
return y;
}"""
    )


def test_is_none():
    def f(x):
        return x is None

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x == null;
}"""
    )


def test_is_not_none():
    def f(x):
        return x is not None

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x != null;
}"""
    )


def test_simple_addition():
    def f(a, b):
        return a + b

    code, n_args, h = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return a + b;
}"""
    )


def test_is_with_value():
    def f(x):
        y = 5
        return x is y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = 5;
return x === y;
}"""
    )


def test_is_not_with_string():
    warnings.simplefilter("ignore", SyntaxWarning)

    def f(s):
        a = "a"
        return s is not a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
let a = `a`;
return s !== a;
}"""
    )


def test_constants_arithmetic_comparisons_boolean_ops():
    def f(x):
        return (x * 2 + 3) > 0 and not (x == 5)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return (x * 2 + 3 > 0) && !(x === 5);
}"""
    )


def test_unary_minus():
    def f(x):
        return -x

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return -x;
}"""
    )


def test_compare_chaining():
    def f(x):
        return 0 < x < 10

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return 0 < x && x < 10;
}"""
    )


def test_pow_with_negative_base_parenthesized():
    def f():
        return (-2) ** 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(){
return (-2) ** 2;
}"""
    )
