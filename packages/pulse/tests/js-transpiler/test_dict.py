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
return d["y"] ?? undefined;
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


def test_dynamic_dict_key():
    def f(k, v):
        return {k: v}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(k, v){
return {[String(k)]: v};
}"""
    )


def test_dict_unpacking():
    def f(a, b):
        return {"x": 1, **a, **b, "y": 2}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return {"x": 1, ...a, ...b, "y": 2};
}"""
    )


def test_dict_copy():
    def f(d):
        return d.copy()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Array.isArray(d) ? d.slice() : {...d};
}"""
    )


def test_dict_pop_existing():
    def f(d):
        return d.pop("a")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return (() => {const __k="a"; if (Object.hasOwn(d, __k)) { const __v = d[__k]; delete d[__k]; return __v; } })();
}"""
    )


def test_dict_pop_missing_with_default():
    def f(d):
        return d.pop("a", 0)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return (() => {const __k="a"; if (Object.hasOwn(d, __k)) { const __v = d[__k]; delete d[__k]; return __v; } return 0; })();
}"""
    )


def test_dict_pop_missing_returns_null():
    def f(d):
        return d.pop("a")

    code, _, _ = compile_python_to_js(f)
    assert 'return (() => {const __k="a";' in code


def test_dict_popitem():
    def f(d):
        return d.popitem()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return (() => {const __ks = Object.keys(d); if (__ks.length === 0) { return; } const __k = __ks[__ks.length-1]; const __v = d[__k]; delete d[__k]; return [__k, __v]; })();
}"""
    )


def test_dict_setdefault_missing():
    def f(d):
        return d.setdefault("a", 1)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return (() => {const __k="a"; if (!Object.hasOwn(d, __k)) { d[__k] = 1; return 1; } return d[__k]; })();
}"""
    )


def test_dict_setdefault_existing():
    def f(d):
        return d.setdefault("a")

    code, _, _ = compile_python_to_js(f)
    # The logic for setdefault produces `return undefined` here. This is fine,
    # minimizers will handle it anyways.
    assert code == (
        """function(d){
return (() => {const __k="a"; if (!Object.hasOwn(d, __k)) { d[__k] = undefined; return undefined; } return d[__k]; })();
}"""
    )


def test_dict_update_and_clear():
    def f(d, o):
        d.update(o)
        d.clear()
        return d

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d, o){
(() => {Object.assign(d, o); })();
(() => {if (Array.isArray(d)) { d.length = 0; return; } if (d && typeof d === "object") { for (const __k in d){ if (Object.hasOwn(d, __k)) delete d[__k]; } return; } return d.clear(); })();
return d;
}"""
    )


def test_dict_comprehension_filter():
    def f(pairs):
        return {k: v for (k, v) in pairs if v > 0}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(pairs){
return Object.fromEntries(pairs.filter(([k, v]) => v > 0).map(([k, v]) => [String(k), v]));
}"""
    )


def test_len_on_dict_counts_keys():
    def f(d):
        return len(d)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d.length ?? Object.keys(d).length;
}"""
    )


def test_membership_in_object_or_array_uses_runtime_branch():
    def f(d):
        return "a" in d

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return ((Array.isArray(d) || typeof d === "string") ? d.includes("a") : (d && typeof d === "object" && Object.hasOwn(d, "a")));
}"""
    )
