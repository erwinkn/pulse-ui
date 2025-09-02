from typing import Any, cast
import pulse as ps
from pulse.javascript.function import JsFunction


def _emit(fn) -> str:
    return JsFunction(fn).emit().code


def test_basic_div_text_child():
    def f():
        return ps.div("hi")

    code = _emit(f)
    assert "return <div>hi</div>;" in code


def test_div_with_expr_child():
    def f(x):
        return ps.div(x)

    code = _emit(f)
    # Expression children are wrapped in JSX braces
    assert "return <div>{x}</div>;" in code


def test_div_with_props_and_children():
    def f():
        return ps.div("hello", id="g", className="c")

    code = _emit(f)
    assert '<div id="g" className="c">hello</div>' in code


def test_self_closing_img():
    def f():
        return ps.img(src="/a.png", alt="a")

    code = _emit(f)
    assert 'return <img src="/a.png" alt="a" />;' in code


def test_keywords_only_alias_del():
    def f():
        return ps.del_("x")

    code = _emit(f)
    assert "<del>x</del>" in code


def test_fragment_basic():
    def f():
        return ps.fragment("a", ps.div("b"))

    code = _emit(f)
    assert "return <>a<div>b</div></>;" in code


def test_fragment_empty():
    def f():
        return ps.fragment()

    code = _emit(f)
    assert "return <></>;" in code


def test_index_children_syntax_basic():
    def f():
        return ps.div(className="c", id="i")[ps.h2(className="h")["A"], ps.p("B")]

    code = _emit(f)
    assert '<div className="c" id="i"><h2 className="h">A</h2><p>B</p></div>' in code


def test_index_children_with_expr_and_call_child():
    def f(x):
        return ps.div("lead:", className="c")[x, ps.p("B")]

    code = _emit(f)
    assert '<div className="c">lead:{x}<p>B</p></div>' in code


def test_spread_props_and_named_ordering():
    def f(props):
        return ps.div(className="c", **props, id="i")[ps.p("B")]

    code = _emit(f)
    # Rendered props order: className first, then spread, then id
    assert '<div className="c" {...' in code or '<div className="c" {...' in code
    assert ' id="i"' in code


def test_nested_array_children_flatten_and_wrap():
    def f(x):
        return ps.div()[[ps.h2("A"), [x, ps.p("B")]]]

    code = _emit(f)
    assert "<div><h2>A</h2>{x}<p>B</p></div>" in code


def test_fragment_with_nested_arrays_and_vars():
    def f(x):
        return ps.fragment(cast(Any, [["a"], [ps.div("b"), x]]))

    code = _emit(f)
    assert "return <>a<div>b</div>{x}</>;" in code


def test_child_spread_iterable_passthrough():
    def f(arr):
        return ps.div()[*arr]

    code = _emit(f)
    # We expect React to handle iterables/arrays spread as children, so just a brace expression
    assert "return <div>{arr}</div>;" in code
