from pulse.javascript import compile_python_to_js


def test_lower():
    def f(s):
        return s.lower()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.toLowerCase();
}"""
    )


def test_upper():
    def f(s):
        return s.upper()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.toUpperCase();
}"""
    )


def test_strip():
    def f(s):
        return s.strip()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.trim();
}"""
    )


def test_startswith():
    def f(s):
        return s.startswith("a")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.startsWith(`a`);
}"""
    )


def test_endswith():
    def f(s):
        return s.endswith("b")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.endsWith(`b`);
}"""
    )


def test_lstrip_and_rstrip():
    def f(s):
        return s.lstrip() + s.rstrip()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.trimStart() + s.trimEnd();
}"""
    )


def test_replace_all():
    def f(s):
        return s.replace("a", "b")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.replaceAll(`a`, `b`);
}"""
    )


def test_capitalize():
    def f(s):
        return s.capitalize()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}"""
    )


def test_zfill():
    def f(s):
        return s.zfill(5)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.padStart(5, `0`);
}"""
    )


def test_string_split():
    def f(s):
        return s.split(",")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.split(`,`);
}"""
    )


def test_string_join():
    def f(xs):
        return ",".join(xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.join(`,`);
}"""
    )


def test_membership_in_string():
    def f(s):
        return "x" in s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return ((Array.isArray(s) || typeof s === "string") ? s.includes(`x`) : (s && typeof s === "object" && Object.hasOwn(s, `x`)));
}"""
    )


def test_constant_string_escapes_backtick_and_dollar_brace():
    def f():
        return "a`b${c}d"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        r"""function(){
return `a\`b\${c}d`;
}"""
    )
