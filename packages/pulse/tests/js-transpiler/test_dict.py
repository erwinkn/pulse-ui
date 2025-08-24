from pulse.javascript import compile_python_to_js


def test_keys():
    def f(d):
        return list(d.keys())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Object.keys(d);
}"""
    )


def test_values():
    def f(d):
        return list(d.values())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Object.values(d);
}"""
    )


def test_items():
    def f(d):
        return list(d.items())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Object.entries(d);
}"""
    )


def test_dict_get_with_default():
    def f(d):
        return d.get("x", 0)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d["x"] ?? 0;
}"""
    )


def test_dict_get_without_default():
    def f(d):
        return d.get("y")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d["y"] ?? null;
}"""
    )


def test_dict_comprehension_simple():
    def f(xs):
        return {x: x + 1 for x in xs}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return Object.fromEntries(xs.map(x => [String(x), x + 1]));
}"""
    )


def test_dict_literal():
    def f(x):
        return {"a": 1, "b": x}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return {"a": 1, "b": x};
}"""
    )


def test_dict_comprehension_filter():
    def f(pairs):
        return {k: v for (k, v) in pairs if v > 0}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(pairs){
return Object.fromEntries(pairs.filter(([k, v]) => (v > 0)).map(([k, v]) => [String(k), v]));
}"""
    )


def test_len_on_dict_counts_keys():
    def f(d):
        return len(d)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return (d?.length ?? Object.keys(d).length);
}"""
    )


def test_membership_in_object_or_array_uses_runtime_branch():
    def f(d):
        return "a" in d

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return ((Array.isArray(d) || typeof d === "string") ? d.includes(`a`) : (d && typeof d === "object" && Object.hasOwn(d, `a`)));
}"""
    )
