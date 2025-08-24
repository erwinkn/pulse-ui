from pulse.javascript import compile_python_to_js


def test_round_keyword_only_number():
    def f(x):
        return round(number=x)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return Math.round(x);
}"""
    )


def test_round_keyword_ndigits():
    def f(x):
        return round(number=x, ndigits=2)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return Number(x).toFixed(2);
}"""
    )


def test_int_keyword_base16():
    def f(s: str):
        return int(s, 16)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
return parseInt(s, 16);
}"""
    )
