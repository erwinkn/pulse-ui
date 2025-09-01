from pulse.javascript.transpiler import compile_python_to_js


def test_keys():
    def f(d):
        return list(d.keys())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d instanceof Map ? [...d.keys()] : d.keys();
}"""
    )


def test_values():
    def f(d):
        return list(d.values())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d instanceof Map ? [...d.values()] : d.values();
}"""
    )


def test_items():
    def f(d):
        return list(d.items())

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d instanceof Map ? [...d.entries()] : d.items();
}"""
    )


def test_dict_get_with_default():
    def f(d):
        return d.get("x", 0)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d instanceof Map ? d.get("x") ?? 0 : d.get("x", 0);
}"""
    )


def test_dict_get_without_default():
    def f(d):
        return d.get("y")

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d.get("y");
}"""
    )


def test_dict_comprehension_simple():
    def f(xs):
        return {x: x + 1 for x in xs}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(xs){
return new Map(xs.map(x => [x, x + 1]));
}"""
    )


def test_dict_literal():
    def f(x):
        return {"a": 1, "b": x}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(x){
return new Map([["a", 1], ["b", x]]);
}"""
    )


def test_dynamic_dict_key():
    def f(k, v):
        return {k: v}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(k, v){
return new Map([[k, v]]);
}"""
    )


def test_dict_unpacking():
    def f(a, b):
        return {"x": 1, **a, **b, "y": 2}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(a, b){
return new Map([["x", 1], ...a instanceof Map ? a.entries() : Object.entries(a), ...b instanceof Map ? b.entries() : Object.entries(b), ["y", 2]]);
}"""
    )


def test_dict_copy():
    def f(d):
        return d.copy()

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return Array.isArray(d) ? d.slice() : d instanceof Map ? new Map(d.entries()) : d.copy();
}"""
    )


def test_dict_pop():
    def f(d):
        return d.pop("a")

    code, _, _ = compile_python_to_js(f)
    print(code)
    assert code == (
        """function(d){
return Array.isArray(d) ? d.splice("a", 1)[0] : d instanceof Map ? (() => {
if (d.has("a")){
const $v = d.get("a");
d.delete("a");
return $v;
} else {
return undefined;
}
})() : d.pop("a");
}"""
    )


def test_dict_pop_missing_with_default():
    def f(d):
        return d.pop("a", 0)

    code, _, _ = compile_python_to_js(f)
    print(code)
    assert code == (
        """function(d){
return d instanceof Map ? (() => {
if (d.has("a")){
const $v = d.get("a");
d.delete("a");
return $v;
} else {
return 0;
}
})() : d.pop("a", 0);
}"""
    )


def test_dict_popitem():
    def f(d):
        return d.popitem()

    code, _, _ = compile_python_to_js(f)
    print(code)
    assert code == (
        """function(d){
return d instanceof Map ? (() => {
const $k = d.keys().next();
if ($k.done){
return undefined;
} else {
const $v = d.get($k.value);
d.delete($k);
return [$k, $v];
}
})() : d.popitem();
}"""
    )


def test_dict_setdefault_missing():
    def f(d):
        return d.setdefault("a", 1)

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(d){
return d instanceof Map ? d.has("a") ? d.get("a") : (d.set("a", 1), 1) : d.setdefault("a", 1);
}"""
    )


def test_dict_setdefault_existing():
    def f(d):
        return d.setdefault("a")

    code, _, _ = compile_python_to_js(f)
    print(code)
    assert code == (
        """function(d){
return d instanceof Map ? d.has("a") ? d.get("a") : (d.set("a", undefined), undefined) : d.setdefault("a");
}"""
    )


def test_dict_update_and_clear():
    def f(d, o):
        d.update(o)
        d.clear()
        return d

    code, _, _ = compile_python_to_js(f)
    print(code)
    assert code == (
        """function(d, o){
d instanceof Map ? (() => {
if (o instanceof Map){
for (const [k, v] of o){
d.set(k, v);
}
} else {
if (o && typeof o === "object"){
for (const k of Object.keys(o)){
if (Object.hasOwn(o, k)){
d.set(k, o[k]);
}
}
}
}
})() : d.update(o);
d.clear();
return d;
}"""
    )


def test_dict_comprehension_filter():
    def f(pairs):
        return {k: v for (k, v) in pairs if v > 0}

    code, _, _ = compile_python_to_js(f)
    assert code == (
        """function(pairs){
return new Map(pairs.filter(([k, v]) => v > 0).map(([k, v]) => [k, v]));
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
    print(code)
    assert code == (
        """function(d){
return Array.isArray(d) || typeof d === "string" ? d.includes("a") : d instanceof Set || d instanceof Map ? d.has("a") : "a" in d;
}"""
    )
