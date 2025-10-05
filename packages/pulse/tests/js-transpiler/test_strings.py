from pulse.javascript.transpiler import compile_python_to_js


def test_lower():
    def f(s):
        return s.lower()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.toLowerCase() : s.lower();
}"""
    )


def test_upper():
    def f(s):
        return s.upper()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.toUpperCase() : s.upper();
}"""
    )


def test_strip():
    def f(s):
        return s.strip()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.trim() : s.strip();
}"""
    )


def test_startswith():
    def f(s):
        return s.startswith("a")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.startsWith("a") : s.startswith("a");
}"""
    )


def test_endswith():
    def f(s):
        return s.endswith("b")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.endsWith("b") : s.endswith("b");
}"""
    )


def test_lstrip_and_rstrip():
    def f(s):
        return s.lstrip() + s.rstrip()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return (typeof s === "string" ? s.trimStart() : s.lstrip()) + (typeof s === "string" ? s.trimEnd() : s.rstrip());
}"""
    )


def test_replace_all():
    def f(s):
        return s.replace("a", "b")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.replaceAll("a", "b") : s.replace("a", "b");
}"""
    )


def test_capitalize():
    def f(s):
        return s.capitalize()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s.capitalize();
}"""
    )


def test_zfill():
    def f(s):
        return s.zfill(5)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return typeof s === "string" ? s.padStart(5, "0") : s.zfill(5);
}"""
    )


def test_string_split():
    def f(s):
        return s.split(",")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return s.split(",");
}"""
    )


def test_string_join():
    def f(xs):
        return ",".join(xs)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return xs.join(",");
}"""
    )


def test_membership_in_string():
    def f(s):
        return "x" in s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return Array.isArray(s) || typeof s === "string" ? s.includes("x") : s instanceof Set || s instanceof Map ? s.has("x") : "x" in s;
}"""
    )


def test_constant_string_escapes_quote_and_backslash():
    def f():
        return 'a"b\\c'

    code, _, _ = compile_python_to_js(f)
    assert code == (
        r"""function(){
return "a\"b\\c";
}"""
    )


def test_constant_string_escapes_control_chars():
    def f():
        return "a\nb\rc\t\b\f\v"

    code, _, _ = compile_python_to_js(f)
    assert code == (
        r"""function(){
return "a\nb\rc\t\b\f\v";
}"""
    )
