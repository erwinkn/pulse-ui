from pulse.javascript.transpiler import compile_python_to_js, JSCompilationError


def test_if_else_statement():
    def f(x):
        if x > 0:
            return 1
        else:
            return 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
if (x > 0){
return 1;
} else {
return 2;
}
}"""
    )


def test_conditional_expression():
    def f(x):
        return 1 if x > 0 else 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x > 0 ? 1 : 2;
}"""
    )


def test_boolean_precedence_or():
    def f(a, b, c):
        return (a and b) or c

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b, c){
return a && b || c;
}"""
    )


def test_nested_ternary():
    def f(x):
        return 1 if x > 0 else 2 if x < -1 else 3

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return x > 0 ? 1 : x < -1 ? 2 : 3;
}"""
    )


def test_unpack_tuple_assignment():
    def f(t):
        a, b = t
        return a + b

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(t){
const $tmp0 = t;
let a = $tmp0[0];
let b = $tmp0[1];
return a + b;
}"""
    )


def test_print_single_and_multiple_args():
    def f(a, b):
        print("x")
        print(a, b)
        return 0

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
console.log("x");
console.log(a, b);
return 0;
}"""
    )


def test_unpack_list_assignment_literal_rhs():
    def f():
        a, b = [1, 2]
        return a * b

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(){
const $tmp0 = [1, 2];
let a = $tmp0[0];
let b = $tmp0[1];
return a * b;
}"""
    )


def test_unpack_tuple_reassignment_no_let():
    def f(t):
        a, b = t
        a, b = t
        return a - b

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(t){
const $tmp0 = t;
let a = $tmp0[0];
let b = $tmp0[1];
const $tmp1 = t;
a = $tmp1[0];
b = $tmp1[1];
return a - b;
}"""
    )


def test_unpack_nested_unsupported():
    def f(t):
        (a, (b, c)) = t
        return a

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for nested unpacking"
    except JSCompilationError as e:
        assert "unpacking" in str(e).lower()
