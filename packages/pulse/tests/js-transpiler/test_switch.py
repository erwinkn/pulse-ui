from pulse.javascript import compile_python_to_js, JSCompilationError


def test_match_simple_numbers():
    def f(x):
        match x:
            case 1:
                return 10
            case 2:
                return 20
            case _:
                return 0

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
switch (x){
case 1:
return 10;
break;
case 2:
return 20;
break;
default:
return 0;
}
}"""
    )


def test_match_or_pattern():
    def f(x):
        match x:
            case 1 | 2:
                return 12
            case 3:
                return 3
            case _:
                return -1

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
switch (x){
case 1:
case 2:
return 12;
break;
case 3:
return 3;
break;
default:
return -1;
}
}"""
    )


def test_match_strings():
    def f(s):
        match s:
            case "a":
                return 1
            case "b" | "c":
                return 2
            case _:
                return 0

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(s){
switch (s){
case `a`:
return 1;
break;
case `b`:
case `c`:
return 2;
break;
default:
return 0;
}
}"""
    )


def test_match_guard_unsupported():
    def f(x):
        match x:
            case 1 if x > 0:
                return 1
            case _:
                return 0

    try:
        compile_python_to_js(f)
        assert False, "Expected JSCompilationError for guard in match"
    except JSCompilationError as e:
        assert "guard" in str(e).lower()
