import re

import pulse as ps


def test_javascript_decorator_attaches_metadata():
    @ps.javascript
    def fmt(x):
        return f"{x}"

    code = getattr(fmt, "__pulse_js__", None)
    n_args = getattr(fmt, "__pulse_js_n_args__", None)
    h = getattr(fmt, "__pulse_js_hash__", None)

    assert isinstance(code, str) and code.strip().startswith("function(")
    assert isinstance(n_args, int) and n_args == 1
    assert isinstance(h, str) and re.fullmatch(r"[0-9a-f]{16}", h)
