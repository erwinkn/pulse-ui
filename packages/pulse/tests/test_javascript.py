import re

import pulse as ps
from pulse.javascript import compile_python_to_js, JSCompilationError


def test_javascript_decorator_attaches_metadata():
    @ps.javascript
    def fmt(x):
        return f"{x}"

    code = getattr(fmt, "__pulse_js__", None)
    n_args = getattr(fmt, "__pulse_js_n_args__", None)
    h = getattr(fmt, "__pulse_js_hash__", None)

    assert isinstance(code, str) and code.strip().startswith("function(")
    assert isinstance(n_args, int) and n_args == 1
    assert isinstance(h, str) and re.fullmatch(r"[0-9a-f]{16}", h)


# ============================
# compile_python_to_js tests
# ============================


def test_compile_simple_addition_exact_code():
    def f(a, b):
        return a + b

    code, n_args, h = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return (a + b);
}"""
    )
    assert n_args == 2
    assert len(h) == 16 and all(c in "0123456789abcdef" for c in h)


def test_compile_constants_arithmetic_comparisons_boolean_ops_exact():
    def f(x):
        return (x * 2 + 3) > 0 and not (x == 5)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((((x * 2) + 3) > 0) && (!(x === 5)));
}"""
    )


def test_compile_if_else_statement_exact():
    def f(x):
        if x > 0:
            return 1
        else:
            return 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
if ((x > 0)){
return 1;
} else {
return 2;
}
}"""
    )


def test_compile_if_expression_exact():
    def f(x):
        return 1 if x > 0 else 2

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((x > 0) ? 1 : 2);
}"""
    )


def test_compile_whitelisted_builtins_exact():
    def f(a, b):
        return len(a) + min(a, b) + max(a, b) + abs(b) + int(3.2) + float("2.5")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return ((((((a?.length ?? 0) + Math.min(a, b)) + Math.max(a, b)) + Math.abs(b)) + parseInt(3.2)) + parseFloat(`2.5`));
}"""
    )


def test_compile_round_and_str_exact():
    def f(x):
        return str(round(x))

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return String(Math.round(x));
}"""
    )

    def g(x):
        return round(x, 2)

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(x){
return (Number(x).toFixed(2));
}"""
    )


def test_compile_attribute_and_subscript_exact():
    def f(obj):
        return obj.value

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(obj){
return (obj.value);
}"""
    )

    def g(arr):
        return arr[0]

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(arr){
return (arr[0]);
}"""
    )


def test_compile_fstring_to_template_literal_exact():
    def f(x):
        return f"value={x}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return `value=${x}`;
}"""
    )


def test_compile_string_methods_lower_upper_strip_exact():
    def f(s):
        return s.lower() + s.upper() + s.strip()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return (((s.toLowerCase()) + (s.toUpperCase())) + (s.trim()));
}"""
    )


def test_compile_assign_and_annassign_exact():
    def f(x):
        y = x + 1
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = (x + 1);
return y;
}"""
    )

    def g(x: int):
        y: int = x
        return y

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(x){
let y = x;
return y;
}"""
    )


def test_compile_reassignment_without_let_exact():
    def f(x):
        y = x + 1
        y = y + 2
        return y

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
let y = (x + 1);
y = (y + 2);
return y;
}"""
    )


def test_compile_param_reassignment_without_let_exact():
    def f(x):
        x = x + 1
        return x

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
x = (x + 1);
return x;
}"""
    )

def test_compile_unary_ops_exact():
    def f(x):
        return -x

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return (-x);
}"""
    )

def test_compile_format_strings_exact():
    def f(n):
        return f"{n:.2f}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(n){
return n.toFixed(2);
}"""
    )


def test_compile_compare_chaining_exact():
    def f(x):
        return 0 < x < 10

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((0 < x) && (x < 10));
}"""
    )


def test_compile_is_none_and_is_not_none_exact():
    def f(x):
        return x is None

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return (x === null);
}"""
    )

    def g(x):
        return x is not None

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(x){
return (x !== null);
}"""
    )


def test_compile_membership_in_not_in_exact():
    def f(a):
        return 2 in a

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return (a.includes(2));
}"""
    )

    def g(s):
        return "x" in s

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(s){
return (s.includes(`x`));
}"""
    )

    def h(a):
        return 3 not in a

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(a){
return (!(a.includes(3)));
}"""
    )


def test_compile_slicing_and_negative_indices_exact():
    def f(a):
        return a[1:3]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return (a.slice(1, 3));
}"""
    )

    def g(a):
        return a[:2]

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(a){
return (a.slice(0, 2));
}"""
    )

    def h(a):
        return a[2:]

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(a){
return (a.slice(2));
}"""
    )

    def i(a):
        return a[-2:]

    code4, _, _ = compile_python_to_js(i)
    assert code4 == (
        """function(a){
return (a.slice(-2));
}"""
    )

    def j(a):
        return a[:-1]

    code5, _, _ = compile_python_to_js(j)
    assert code5 == (
        """function(a){
return (a.slice(0, -1));
}"""
    )

    def k(a):
        return a[-1]

    code6, _, _ = compile_python_to_js(k)
    assert code6 == (
        """function(a){
return (a.at(-1));
}"""
    )


def test_compile_augassign_exact():
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


def test_compile_keyword_args_round_and_int_exact():
    def f(x):
        return round(number=x)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return Math.round(x);
}"""
    )

    def g(x):
        return round(number=x, ndigits=2)

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(x){
return (Number(x).toFixed(2));
}"""
    )

    def h(s):
        return int(x=s, base=16)

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(s){
return parseInt(s, 16);
}"""
    )


def test_compile_extended_string_methods_exact():
    def f(s):
        return s.startswith("a")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return (s.startsWith(`a`));
}"""
    )

    def g(s):
        return s.endswith("b")

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(s){
return (s.endsWith(`b`));
}"""
    )

    def h(s):
        return s.lstrip() + s.rstrip()

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(s){
return ((s.trimStart()) + (s.trimEnd()));
}"""
    )

    def i(s):
        return s.replace("a", "b")

    code4, _, _ = compile_python_to_js(i)
    assert code4 == (
        """function(s){
return (s.replaceAll(`a`, `b`));
}"""
    )


def test_compile_raises_on_freevars():
    y = 5

    def f(x):
        return x + y

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for free variable"
    except JSCompilationError as e:
        assert "free variables" in str(e)


def test_compile_raises_on_unsupported_statement_for_loop():
    def f(xs):
        s = 0
        for i in xs:
            s = s + i
        return s

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for unsupported statement"
    except JSCompilationError as e:
        assert "Unsupported statement" in str(e)
