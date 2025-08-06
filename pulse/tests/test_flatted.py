import pytest
from pulse.vendor.flatted import parse
from pulse.vendor.flatted import stringify as _stringify


@pytest.fixture
def stringify():
    def _shim(value):
        return _stringify(value, separators=(",", ":"))

    return _shim


def test_none(stringify):
    assert stringify([None, None]) == "[[null,null]]"


def test_empty(stringify):
    assert stringify([]) == "[[]]"
    assert stringify({}) == "[{}]"


def test_circular_references(stringify):
    a = []
    a.append(a)
    assert stringify(a) == '[["0"]]'

    o = {}
    o["o"] = o
    assert stringify(o) == '[{"o":"0"}]'


def test_parse_circular_list(stringify):
    a = []
    a.append(a)
    b = parse(stringify(a))
    assert isinstance(b, list)
    assert b[0] is b


@pytest.fixture
def mixed_data():
    a = []
    a.append(a)
    a.append(1)
    a.append("two")
    a.append(True)

    o = {}
    o["o"] = o
    o["one"] = 1
    o["two"] = "two"
    o["three"] = True
    return a, o


def test_mixed_types(stringify, mixed_data):
    a, o = mixed_data
    assert stringify(a) == '[["0",1,"1",true],"two"]'
    assert stringify(o) == '[{"o":"0","one":1,"two":"1","three":true},"two"]'


def test_nested_structures(stringify, mixed_data):
    a, o = mixed_data
    a.append(o)
    o["a"] = a

    assert (
        stringify(a)
        == '[["0",1,"1",true,"2"],"two",{"o":"2","one":1,"two":"1","three":true,"a":"0"}]'
    )
    assert (
        stringify(o)
        == '[{"o":"0","one":1,"two":"1","three":true,"a":"2"},"two",["2",1,"1",true,"0"]]'
    )


@pytest.fixture
def deeply_nested_data():
    a = []
    a.append(a)
    a.append(1)
    a.append("two")
    a.append(True)

    o = {}
    o["o"] = o
    o["one"] = 1
    o["two"] = "two"
    o["three"] = True

    a.append(o)
    o["a"] = a

    a.append({"test": "OK"})
    a.append([1, 2, 3])

    o["test"] = {"test": "OK"}
    o["array"] = [1, 2, 3]
    return a, o


def test_more_nesting(stringify, deeply_nested_data):
    a, o = deeply_nested_data
    assert (
        stringify(a)
        == '[["0",1,"1",true,"2","3","4"],"two",{"o":"2","one":1,"two":"1","three":true,"a":"0","test":"3","array":"4"},{"test":"5"},[1,2,3],"OK"]'
    )
    assert (
        stringify(o)
        == '[{"o":"0","one":1,"two":"1","three":true,"a":"2","test":"3","array":"4"},"two",["2",1,"1",true,"0","3","4"],{"test":"5"},[1,2,3],"OK"]'
    )


def test_parsing_complex_structures(stringify, deeply_nested_data):
    a, o = deeply_nested_data

    a2 = parse(stringify(a))
    o2 = parse(stringify(o))

    assert a2[0] is a2
    assert o2["o"] is o2

    assert a2[1] == 1
    assert a2[2] == "two"
    assert a2[3] is True
    assert isinstance(a2[4], dict)
    assert a2[4] is a2[4]["o"]
    assert a2 is a2[4]["o"]["a"]


def test_parse_from_string_1():
    # 'str' is a bad variable name, it shadows the builtin. The test file uses it. I will rename it.
    parsed = parse(
        '[{"prop":"1","a":"2","b":"3"},{"value":123},["4","5"],{"e":"6","t":"7","p":4},{},{"b":"8"},"f",{"a":"9"},["10"],"sup",{"a":1,"d":2,"c":"7","z":"11","h":1},{"g":2,"a":"7","b":"12","f":6},{"r":4,"u":"7","c":5}]'
    )
    assert parsed["b"]["t"]["a"] == "sup"
    assert parsed["a"][1]["b"][0]["c"] is parsed["b"]["t"]


def test_parse_from_string_2():
    oo = parse(
        '[{"a":"1","b":"0","c":"2"},{"aa":"3"},{"ca":"4","cb":"5","cc":"6","cd":"7","ce":"8","cf":"9"},{"aaa":"10"},{"caa":"4"},{"cba":"5"},{"cca":"2"},{"cda":"4"},"value2","value3","value1"]'
    )
    assert oo["a"]["aa"]["aaa"] == "value1"
    assert oo is oo["b"]
    assert oo["c"]["ca"]["caa"] is oo["c"]["ca"]


def test_datetime(stringify):
    import datetime

    now = datetime.datetime.now()
    data = {"time": now}
    stringified = stringify(data)
    parsed = parse(stringified)
    assert parsed["time"] == now
