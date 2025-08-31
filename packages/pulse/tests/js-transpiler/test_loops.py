from pulse.javascript.transpiler import compile_python_to_js


def test_simple_for_over_list():
    def f(xs):
        s = 0
        for x in xs:
            s = s + x
        return s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
let s = 0;
for (const x of xs){
s = s + x;
}
return s;
}"""
    )


def test_for_with_break():
    def f(xs):
        s = 0
        for x in xs:
            if x > 10:
                break
            s = s + x
        return s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
let s = 0;
for (const x of xs){
if (x > 10){
break;
}
s = s + x;
}
return s;
}"""
    )


def test_for_with_continue():
    def f(xs):
        s = 0
        for x in xs:
            if x % 2 == 0:
                continue
            s = s + x
        return s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
let s = 0;
for (const x of xs){
if (x % 2 === 0){
continue;
}
s = s + x;
}
return s;
}"""
    )


def test_while_loop():
    def f(n):
        i = 0
        s = 0
        while i < n:
            s = s + i
            i = i + 1
        return s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(n){
let i = 0;
let s = 0;
while (i < n){
s = s + i;
i = i + 1;
}
return s;
}"""
    )


def test_while_with_break_continue():
    def f(n):
        i = 0
        s = 0
        while True:
            i = i + 1
            if i > n:
                break
            if i % 2 == 0:
                continue
            s = s + i
        return s

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(n){
let i = 0;
let s = 0;
while (true){
i = i + 1;
if (i > n){
break;
}
if (i % 2 === 0){
continue;
}
s = s + i;
}
return s;
}"""
    )
