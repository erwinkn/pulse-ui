from pulse.javascript import JSCompilationError, compile_python_to_js


def test_fstring_to_template_literal():
    def f(x):
        return f"value={x}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return `value=${x}`;
}"""
    )

def test_simple_format_fixed_2():
    def f(n):
        return f"{n:.2f}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(n){
return n.toFixed(2);
}"""
    )


def test_numeric_format_zero_pad_width_8_two_decimals():
    def f(x):
        return f"{x:08.2f}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((Number(x) < 0) ? `-` : ``) + (Number(Math.abs(Number(x))).toFixed(2)).padStart(8 - ((Number(x) < 0) ? `-` : ``).length, `0`);
}"""
    )


def test_numeric_format_signed_plus_one_decimal():
    def f(x):
        return f"{x:+.1f}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((Number(x) < 0) ? `-` : `+`) + `` + Number(Math.abs(Number(x))).toFixed(1);
}"""
    )


def test_numeric_format_alt_hex_lowercase():
    def f(x):
        return f"{x:#x}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((Number(x) < 0) ? `-` : ``) + `0x` + Math.trunc(Math.abs(Number(x))).toString(16);
}"""
    )


def test_numeric_format_alt_hex_uppercase():
    def f(x):
        return f"{x:#X}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((Number(x) < 0) ? `-` : ``) + `0X` + Math.trunc(Math.abs(Number(x))).toString(16).toUpperCase();
}"""
    )


def test_numeric_format_binary():
    def f(x):
        return f"{x:b}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return ((Number(x) < 0) ? `-` : ``) + `` + Math.trunc(Math.abs(Number(x))).toString(2);
}"""
    )


def test_string_format_center_width_7():
    def f(y):
        return f"{y:^7s}"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(y){
return String(y).padStart(Math.floor((7 + String(y).length) / 2), ` `).padEnd(7, ` `);
}"""
    )


def test_format_spec_errors():
    def non_const_format(x, p):
        return f"{x:{p}}"

    try:
        compile_python_to_js(non_const_format)
        assert False, "Expected JSCompilationError for non-constant format spec"
    except JSCompilationError as e:
        assert "constant" in str(e)

    def unsupported_type(x):
        return f"{x:Z}"

    try:
        compile_python_to_js(unsupported_type)
        assert False, "Expected JSCompilationError for unsupported type"
    except JSCompilationError as e:
        assert "Unsupported format type" in str(e)

    def unsupported_grouping(x):
        return f"{x:_d}"

    try:
        compile_python_to_js(unsupported_grouping)
        assert False, "Expected JSCompilationError for unsupported grouping"
    except JSCompilationError as e:
        assert "Unsupported grouping" in str(e)

    def eq_align_on_string(s):
        return f"{s:=10s}"

    try:
        compile_python_to_js(eq_align_on_string)
        assert False, "Expected JSCompilationError for '=' alignment on string"
    except JSCompilationError as e:
        assert "Alignment '=' is only supported for numeric types" in str(e)
