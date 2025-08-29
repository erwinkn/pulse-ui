from pulse.javascript import compile_python_to_js


def test_len():
    def f(a):
        return len(a)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a){
return a.length ?? Object.keys(a).length;
}"""
    )


def test_min():
    def f(a, b):
        return min(a, b)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return Math.min(a, b);
}"""
    )


def test_max():
    def f(a, b):
        return max(a, b)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return Math.max(a, b);
}"""
    )


def test_abs():
    def f(b):
        return abs(b)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(b){
return Math.abs(b);
}"""
    )


def test_int_parse_literal():
    def f():
        return int(3.2)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(){
return parseInt(3.2);
}"""
    )


def test_float_parse_literal():
    def f():
        return float("2.5")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(){
return parseFloat("2.5");
}"""
    )


def test_round_and_str():
    def f(x):
        return str(round(x))

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return String(Math.round(x));
}"""
    )


def test_round_with_ndigits():
    def f(x):
        return round(x, 2)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return Number(x).toFixed(2);
}"""
    )


def test_int_with_base16_keyword_args():
    def f(s: str):
        return int(s, 16)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return parseInt(s, 16);
}"""
    )
