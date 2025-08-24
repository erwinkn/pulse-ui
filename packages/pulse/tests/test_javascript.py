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


def test_compile_full_format_specifiers_numeric_and_string():
    def f(x):
        return f"{x:08.2f}"

    code, _, _ = compile_python_to_js(f)
    # zero-pad width 8, 2 decimals
    assert code == (
        """function(x){
return (((Number(x) < 0) ? `-` : ``) + (Number(Math.abs(Number(x))).toFixed(2)).padStart(8 - (((Number(x) < 0) ? `-` : ``)).length, `0`));
}"""
    )

    def g(x):
        return f"{x:+.1f}"

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(x){
return (((Number(x) < 0) ? `-` : `+`) + `` + Number(Math.abs(Number(x))).toFixed(1));
}"""
    )

    def h(x):
        return f"{x:#x}"

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(x){
return (((Number(x) < 0) ? `-` : ``) + `0x` + (Math.trunc(Math.abs(Number(x))).toString(16)));
}"""
    )

    def i(x):
        return f"{x:#X}"

    code4, _, _ = compile_python_to_js(i)
    assert code4 == (
        """function(x){
return (((Number(x) < 0) ? `-` : ``) + `0X` + ((Math.trunc(Math.abs(Number(x))).toString(16)).toUpperCase()));
}"""
    )

    def j(x):
        return f"{x:b}"

    code5, _, _ = compile_python_to_js(j)
    assert code5 == (
        """function(x){
return (((Number(x) < 0) ? `-` : ``) + `` + (Math.trunc(Math.abs(Number(x))).toString(2)));
}"""
    )

    def k(y):
        return f"{y:^7s}"

    code6, _, _ = compile_python_to_js(k)
    assert code6 == (
        """function(y){
return ((String(y)).padStart(Math.floor((7 + (String(y)).length)/2), ` `).padEnd(7, ` `));
}"""
    )


def test_format_spec_errors_and_unsupported():
    # Non-constant format spec should error
    def f(x, p):
        return f"{x:{p}}"

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for non-constant format spec"
    except JSCompilationError as e:
        assert "constant" in str(e)

    # Unsupported type
    def g(x):
        return f"{x:Z}"

    try:
        compile_python_to_js(g)
        assert False, "Expected JSCompilationError for unsupported type"
    except JSCompilationError as e:
        assert "Unsupported format type" in str(e)

    # Unsupported grouping '_'
    def h(x):
        return f"{x:_d}"

    try:
        compile_python_to_js(h)
        assert False, "Expected JSCompilationError for unsupported grouping"
    except JSCompilationError as e:
        assert "Unsupported grouping" in str(e)

    # '=' alignment not allowed for strings
    def i(s):
        return f"{s:=10s}"

    try:
        compile_python_to_js(i)
        assert False, "Expected JSCompilationError for '=' alignment on string"
    except JSCompilationError as e:
        assert "Alignment '=' is only supported for numeric types" in str(e)


def test_list_tuple_dict_literals_and_join_and_slice_step_error():
    def f():
        return [1, 2, 3]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(){
return [1, 2, 3];
}"""
    )

    def g(x):
        return (1, x)

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(x){
return [1, x];
}"""
    )

    def h(x):
        return (x,)

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(x){
return [x];
}"""
    )

    def i(x):
        return {"a": 1, "b": x}

    code4, _, _ = compile_python_to_js(i)
    assert code4 == (
        """function(x){
return ({"a": 1, "b": x});
}"""
    )

    def j(xs):
        return ",".join(xs)

    code5, _, _ = compile_python_to_js(j)
    assert code5 == (
        """function(xs){
return (xs.join(`,`));
}"""
    )

    def k(a):
        return a[::2]

    try:
        compile_python_to_js(k)
        assert False, "Expected JSCompilationError for slice step"
    except JSCompilationError as e:
        assert "slice step" in str(e).lower()

    def m(x):
        return {x: 1}

    try:
        compile_python_to_js(m)
        assert False, "Expected JSCompilationError for non-string dict key"
    except JSCompilationError as e:
        assert "dict keys" in str(e)


def test_dict_methods_and_string_split():
    def f(d):
        return d.get("x", 0)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return ((d["x"] ?? 0));
}"""
    )


def test_list_comprehensions_and_precedence_and_more_string_methods():
    def f(xs):
        return [x + 1 for x in xs]

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return (xs.map(x => (x + 1)));
}"""
    )

    def g(xs):
        return [x for x in xs if x > 0]

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(xs){
return (xs.filter(x => ((x > 0))));
}"""
    )

    def h(a, b, c):
        return (a and b) or c

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(a, b, c){
return ((a && b) || c);
}"""
    )

    def i(x):
        return 1 if x > 0 else 2 if x < -1 else 3

    code4, _, _ = compile_python_to_js(i)
    assert code4 == (
        """function(x){
return ((x > 0) ? 1 : ((x < -1) ? 2 : 3));
}"""
    )

    def j(s):
        return s.capitalize()

    code5, _, _ = compile_python_to_js(j)
    assert code5 == (
        """function(s){
return ((s.charAt(0).toUpperCase()) + (s.slice(1).toLowerCase()));
}"""
    )

    def k(s):
        return s.zfill(5)

    code6, _, _ = compile_python_to_js(k)
    assert code6 == (
        """function(s){
return (s.padStart(5, `0`));
}"""
    )

    def g(d):
        return d.get("y")

    code2, _, _ = compile_python_to_js(g)
    assert code2 == (
        """function(d){
return (d["y"] ?? null);
}"""
    )

    def h(s):
        return s.split(",")

    code3, _, _ = compile_python_to_js(h)
    assert code3 == (
        """function(s){
return (s.split(`,`));
}"""
    )

    def i(d):
        return list(d.keys())

    code4, _, _ = compile_python_to_js(i)
    assert code4 == (
        """function(d){
return (Object.keys(d));
}"""
    )

    def j(d):
        return list(d.values())

    code5, _, _ = compile_python_to_js(j)
    assert code5 == (
        """function(d){
return (Object.values(d));
}"""
    )

    def k(d):
        return list(d.items())

    code6, _, _ = compile_python_to_js(k)
    assert code6 == (
        """function(d){
return (Object.entries(d));
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
