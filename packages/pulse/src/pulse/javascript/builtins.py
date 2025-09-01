from abc import ABC, abstractmethod
from typing import Callable, cast

from .nodes import (
    JSArray,
    JSArrowFunction,
    JSBinary,
    JSBlock,
    JSCall,
    JSComma,
    JSCompilationError,
    JSConstAssign,
    JSExpr,
    JSForOf,
    JSIdentifier,
    JSIf,
    JSLogicalChain,
    JSMember,
    JSMemberCall,
    JSNew,
    JSNumber,
    JSReturn,
    JSSingleStmt,
    JSSpread,
    JSString,
    JSSubscript,
    JSTertiary,
    JSUnary,
    JSUndefined,
)
from .utils import define_if_not_primary, iife, extract_constant_number
from .format_spec import _apply_format_spec


class Builtins:
    @staticmethod
    def print(*args):
        return JSMemberCall(JSIdentifier("console"), "log", args)

    @staticmethod
    def len(x: JSExpr):
        # - Length for strings and arrays.
        # - Size for sets and maps.
        # - Objects would be `Object.keys(x).length`, but we explicitly avoid it
        return JSBinary(JSMember(x, "length"), "??", JSMember(x, "size"))

    @staticmethod
    def min(*args):
        return JSMemberCall(JSIdentifier("Math"), "min", args)

    @staticmethod
    def max(*args):
        return JSMemberCall(JSIdentifier("Math"), "max", args)

    @staticmethod
    def abs(x):
        return JSMemberCall(JSIdentifier("Math"), "abs", [x])

    @staticmethod
    def round(number: JSExpr, ndigits: JSExpr | None = None):
        # One-argument form
        if ndigits is None:
            return JSCall(JSIdentifier("Math.round"), [cast(JSExpr, number)])

        # Two-argument form
        # Positive branch: Number(x).toFixed(n)
        num_e: JSExpr = cast(JSExpr, number)
        nd_e: JSExpr = cast(JSExpr, ndigits)
        pos_branch = JSMemberCall(
            JSCall(JSIdentifier("Number"), [num_e]), "toFixed", [nd_e]
        )

        # Negative branch: round(Number(x)/10^k)*10^k, with k = abs(n)
        # Try to resolve |n| statically

        nd_value = extract_constant_number(nd_e)
        print(f"nd_e = {nd_e}")
        print(f"Extract ndigits = {nd_value}")
        if nd_value is not None:
            k = JSNumber(abs(nd_value))
        else:
            k = JSMemberCall(JSIdentifier("Math"), "abs", [nd_e])
        factor = JSMemberCall(JSIdentifier("Math"), "pow", [JSNumber(10), k])
        neg_branch = JSBinary(
            JSMemberCall(
                JSIdentifier("Math"),
                "round",
                [JSBinary(JSCall(JSIdentifier("Number"), [num_e]), "/", factor)],
            ),
            "*",
            factor,
        )

        # Static pick if possible
        if nd_value is not None:
            return neg_branch if nd_value < 0 else pos_branch  # type: ignore[operator]

        # Runtime ternary when dynamic
        cond = JSBinary(nd_e, "<", JSNumber(0))
        return JSTertiary(cond, neg_branch, pos_branch)

    @staticmethod
    def str(x: JSExpr):
        return JSCall(JSIdentifier("String"), [x])

    @staticmethod
    def int(*args, **kwargs):
        if kwargs:
            num = kwargs.get("x")
            base = kwargs.get("base")
            if num is None:
                raise JSCompilationError("int() requires 'x' kw when using keywords")
            if base is None:
                return JSCall(JSIdentifier("parseInt"), [num])
            return JSCall(JSIdentifier("parseInt"), [num, base])
        if len(args) == 1:
            return JSCall(JSIdentifier("parseInt"), [args[0]])
        if len(args) == 2:
            return JSCall(JSIdentifier("parseInt"), [args[0], args[1]])
        raise JSCompilationError("int() expects one or two arguments")

    @staticmethod
    def float(x: JSExpr):
        return JSCall(JSIdentifier("parseFloat"), [x])

    @staticmethod
    def list(x: JSExpr):
        return x

    @staticmethod
    def bool(x: JSExpr):
        return JSCall(JSIdentifier("Boolean"), [x])

    @staticmethod
    def set(*args: JSExpr):
        if len(args) == 0:
            return JSNew(JSIdentifier("Set"), [])
        if len(args) == 1:
            return JSNew(JSIdentifier("Set"), [args[0]])
        raise JSCompilationError("set() expects at most one argument")

    @staticmethod
    def tuple(*args: JSExpr):
        if len(args) == 0:
            return JSArray([])
        if len(args) == 1:
            return JSCall(JSIdentifier("Array.from"), [args[0]])
        raise JSCompilationError("tuple() expects at most one argument")

    @staticmethod
    def filter(*args: JSExpr):
        if not (1 <= len(args) <= 2):
            raise JSCompilationError("filter() expects one or two arguments")
        if len(args) == 1:
            # filter(None, iterable) -> truthy filter
            iterable = args[0]
            predicate = JSArrowFunction("v", JSIdentifier("v"))
            return JSMemberCall(iterable, "filter", [predicate])
        func, iterable = args[0], args[1]
        # Python filter(None, it) means filter truthy
        if isinstance(func, JSUndefined):
            func = JSArrowFunction("v", JSIdentifier("v"))
        return JSMemberCall(iterable, "filter", [func])

    @staticmethod
    def map(func: JSExpr, iterable: JSExpr):
        return JSMemberCall(iterable, "map", [func])

    @staticmethod
    def reversed(iterable: JSExpr):
        return JSMemberCall(JSMemberCall(iterable, "slice", []), "reverse", [])

    @staticmethod
    def enumerate(iterable: JSExpr, start: JSExpr | None = None):
        base = JSNumber(0) if start is None else start
        return JSMemberCall(
            iterable,
            "map",
            [
                JSArrowFunction(
                    "(v, i)",
                    JSArray(
                        [JSBinary(JSIdentifier("i"), "+", base), JSIdentifier("v")]
                    ),
                )
            ],
        )

    @staticmethod
    def divmod(x: JSExpr, y: JSExpr):
        q = JSMemberCall(JSIdentifier("Math"), "floor", [JSBinary(x, "/", y)])
        r = JSBinary(x, "-", JSBinary(q, "*", y))
        return JSArray([q, r])

    @staticmethod
    def format(value: JSExpr, spec: JSExpr):
        if isinstance(spec, JSString):
            return _apply_format_spec(value, spec.value)
        raise JSCompilationError("format() spec must be a constant string")

    @staticmethod
    def range(*args: JSExpr):
        # range(stop) | range(start, stop[, step])
        if not (1 <= len(args) <= 3):
            raise JSCompilationError("range() expects 1 to 3 arguments")
        if len(args) == 1:
            stop = args[0]
            length = JSMemberCall(JSIdentifier("Math"), "max", [JSNumber(0), stop])
            return JSCall(
                JSIdentifier("Array.from"),
                [JSMemberCall(JSNew(JSIdentifier("Array"), [length]), "keys", [])],
            )
        start = args[0]
        stop = args[1]
        step = args[2] if len(args) == 3 else JSNumber(1)
        # count = max(0, ceil((stop - start) / step))
        diff = JSBinary(stop, "-", start)
        div = JSBinary(diff, "/", step)
        ceil = JSMemberCall(JSIdentifier("Math"), "ceil", [div])
        count = JSMemberCall(JSIdentifier("Math"), "max", [JSNumber(0), ceil])
        # Array.from(new Array(count).keys(), i => start + i * step)
        return JSCall(
            JSIdentifier("Array.from"),
            [
                JSMemberCall(JSNew(JSIdentifier("Array"), [count]), "keys", []),
                JSArrowFunction(
                    "i",
                    JSBinary(start, "+", JSBinary(JSIdentifier("i"), "*", step)),
                ),
            ],
        )

    @staticmethod
    def sorted(*args: JSExpr, **kwargs):
        # sorted(iterable, key=None, reverse=False)
        if len(args) != 1:
            raise JSCompilationError("sorted() expects exactly one positional argument")
        iterable = args[0]
        key = kwargs.get("key") if kwargs else None
        reverse = kwargs.get("reverse") if kwargs else None
        clone = JSMemberCall(iterable, "slice", [])
        # comparator: (a, b) => (a > b) - (a < b) or with key
        if key is None:
            cmp_expr = JSBinary(
                JSBinary(JSIdentifier("a"), ">", JSIdentifier("b")),
                "-",
                JSBinary(JSIdentifier("a"), "<", JSIdentifier("b")),
            )
        else:
            cmp_expr = JSBinary(
                JSBinary(
                    JSCall(key, [JSIdentifier("a")]),
                    ">",
                    JSCall(key, [JSIdentifier("b")]),
                ),
                "-",
                JSBinary(
                    JSCall(key, [JSIdentifier("a")]),
                    "<",
                    JSCall(key, [JSIdentifier("b")]),
                ),
            )
        sort_call = JSMemberCall(clone, "sort", [JSArrowFunction("(a, b)", cmp_expr)])
        if reverse is None:
            return sort_call
        return JSTertiary(reverse, JSMemberCall(sort_call, "reverse", []), sort_call)

    @staticmethod
    def zip(*args: JSExpr):
        if len(args) == 0:
            return JSArray([])

        # minLen = min(a.length, b.length, ...)
        def length_of(x: JSExpr) -> JSExpr:
            return JSMember(x, "length")

        min_len = length_of(args[0])
        for it in args[1:]:
            min_len = JSMemberCall(
                JSIdentifier("Math"), "min", [min_len, length_of(it)]
            )

        # Array.from(new Array(minLen).keys(), i => [a[i], b[i], ...])
        elems = [JSSubscript(arg, JSIdentifier("i")) for arg in args]
        make_pair = JSArrowFunction("i", JSArray(elems))
        return JSCall(
            JSIdentifier("Array.from"),
            [
                JSMemberCall(JSNew(JSIdentifier("Array"), [min_len]), "keys", []),
                make_pair,
            ],
        )

    @staticmethod
    def pow(*args: JSExpr):
        if len(args) != 2:
            raise JSCompilationError(
                "pow() expects exactly two arguments in this subset"
            )
        return JSMemberCall(JSIdentifier("Math"), "pow", [args[0], args[1]])

    @staticmethod
    def chr(x: JSExpr):
        return JSMemberCall(JSIdentifier("String"), "fromCharCode", [x])

    @staticmethod
    def ord(x: JSExpr):
        return JSMemberCall(x, "charCodeAt", [JSNumber(0)])

    @staticmethod
    def dict(*args: JSExpr, **kwargs):
        # dict(), dict(iterable), or dict(a=1, b=2)
        if len(args) > 1:
            raise JSCompilationError("dict() expects at most one positional argument")
        if len(args) == 1 and kwargs:
            raise JSCompilationError(
                "dict() with both positional and keyword args not supported"
            )
        if len(args) == 0 and not kwargs:
            return JSNew(JSIdentifier("Map"), [])
        if len(args) == 1:
            return JSNew(JSIdentifier("Map"), [args[0]])
        # kwargs-only: build entries array [["k", v], ...]
        entries: list[JSExpr] = []
        for k, v in kwargs.items():
            entries.append(JSArray([JSString(k), v]))
        return JSNew(JSIdentifier("Map"), [JSArray(entries)])

    @staticmethod
    def any(x: JSExpr):
        # any(iterable) or any(map(...)) -> some(predicate)
        if isinstance(x, JSMemberCall) and x.method == "map" and x.args:
            return JSMemberCall(x.obj, "some", [x.args[0]])
        return JSMemberCall(x, "some", [JSArrowFunction("v", JSIdentifier("v"))])

    @staticmethod
    def all(x: JSExpr):
        # all(iterable) or all(map(...)) -> every(predicate)
        if isinstance(x, JSMemberCall) and x.method == "map" and x.args:
            return JSMemberCall(x.obj, "every", [x.args[0]])
        return JSMemberCall(x, "every", [JSArrowFunction("v", JSIdentifier("v"))])

    @staticmethod
    def sum(*args: JSExpr):
        if not (1 <= len(args) <= 2):
            raise JSCompilationError("sum() expects one or two arguments")
        start = args[1] if len(args) == 2 else JSNumber(0)
        base = args[0]
        # Keep map chains intact, so we get ...map(...).reduce(...)
        if isinstance(base, JSMemberCall) and base.method == "map":
            base = JSMemberCall(base.obj, base.method, base.args)
        reducer = JSArrowFunction(
            "(a, b)", JSBinary(JSIdentifier("a"), "+", JSIdentifier("b"))
        )
        return JSMemberCall(base, "reduce", [reducer, start])


BuiltinArgs = tuple[JSExpr, ...]
Builtin = Callable[..., JSExpr]
# Expose only callable static methods from Builtins
BUILTINS: dict[str, Builtin] = {
    name: getattr(Builtins, name)
    for name in dir(Builtins)
    if not name.startswith("_") and callable(getattr(Builtins, name))
}


class BuiltinMethods(ABC):
    def __init__(self, obj: JSExpr) -> None:
        self.this = obj

    @classmethod
    @abstractmethod
    def __runtime_check__(cls, expr: JSExpr) -> JSExpr: ...

    @classmethod
    @abstractmethod
    def __methods__(cls) -> set[str]: ...


class ListMethods(BuiltinMethods):
    @classmethod
    def __runtime_check__(cls, expr: JSExpr):
        return JSMemberCall(JSIdentifier("Array"), "isArray", [expr])

    @classmethod
    def __methods__(cls) -> set[str]:
        return LIST_METHODS

    def append(self, value: JSExpr):
        return JSComma([JSMemberCall(self.this, "push", [value]), JSUndefined()])

    def extend(self, value: JSExpr):
        return JSMemberCall(self.this, "extend", [JSSpread(value)])

    def insert(self, index: JSExpr, value: JSExpr):
        return JSArrowFunction(
            "",
            JSBlock(
                [
                    JSSingleStmt(
                        JSMemberCall(self.this, "splice", [index, JSNumber(0), value])
                    )
                ]
            ),
        )

    def remove(self, value: JSExpr):
        x_expr, x_stmt = define_if_not_primary("$x", self.this)
        return iife(
            [
                x_stmt,
                JSConstAssign("$i", JSMemberCall(x_expr, "indexOf", [value])),
                JSIf(
                    JSBinary(JSIdentifier("$i"), ">=", JSNumber(0)),
                    [
                        JSSingleStmt(
                            JSMemberCall(
                                x_expr, "splice", [JSIdentifier("$i"), JSNumber(1)]
                            )
                        )
                    ],
                    [],
                ),
                JSReturn(JSUndefined()),
            ]
        )

    def reverse(self):
        return JSComma([JSMemberCall(self.this, "reverse", []), JSUndefined()])

    def sort(self):
        return JSComma([JSMemberCall(self.this, "sort", []), JSUndefined()])

    def pop(self, idx: JSExpr | None = None):
        if idx is None:
            return None  # fall through to the regular .pop()
        else:
            return JSSubscript(
                JSMemberCall(self.this, "splice", [idx, JSNumber(1)]), JSNumber(0)
            )

    def copy(self):
        return JSMemberCall(self.this, "slice", [])

    def count(self, value: JSExpr):
        return JSMember(
            JSMemberCall(
                self.this,
                "filter",
                [JSArrowFunction("v", JSBinary(JSIdentifier("v"), "===", value))],
            ),
            "length",
        )

    def index(self, value: JSExpr):
        return JSMemberCall(self.this, "indexOf", [value])


LIST_METHODS = {k for k in ListMethods.__dict__.keys() if not k.startswith("__")}


class StringMethods(BuiltinMethods):
    @classmethod
    def __runtime_check__(cls, expr: JSExpr):
        return JSBinary(JSUnary("typeof", expr), "===", JSString("string"))

    @classmethod
    def __methods__(cls) -> set[str]:
        return STR_METHODS

    def lower(self):
        return JSMemberCall(self.this, "toLowerCase", [])

    def upper(self):
        return JSMemberCall(self.this, "toUpperCase", [])

    def strip(self):
        return JSMemberCall(self.this, "trim", [])

    def lstrip(self):
        return JSMemberCall(self.this, "trimStart", [])

    def rstrip(self):
        return JSMemberCall(self.this, "trimEnd", [])

    def zfill(self, width: JSExpr):
        return JSMemberCall(self.this, "padStart", [width, JSString("0")])

    def startswith(self, prefix: JSExpr):
        return JSMemberCall(self.this, "startsWith", [prefix])

    def endswith(self, suffix: JSExpr):
        return JSMemberCall(self.this, "endsWith", [suffix])

    def replace(self, a: JSExpr, b: JSExpr):
        return JSMemberCall(self.this, "replaceAll", [a, b])

    def capitalize(self):
        left = JSMemberCall(
            JSMemberCall(self.this, "charAt", [JSNumber(0)]), "toUpperCase", []
        )
        right = JSMemberCall(
            JSMemberCall(self.this, "slice", [JSNumber(1)]), "toLowerCase", []
        )
        return JSBinary(left, "+", right)

    # `split` doesn't require any transformation
    def split(self, sep: JSExpr):
        return None

    def join(self, arr: JSExpr):
        return JSMemberCall(arr, "join", [self.this])


STR_METHODS = {k for k in StringMethods.__dict__.keys() if not k.startswith("__")}


class SetMethods(BuiltinMethods):
    @classmethod
    def __runtime_check__(cls, expr: JSExpr):
        return JSBinary(expr, "instanceof", JSIdentifier("Set"))

    @classmethod
    def __methods__(cls):
        return SET_METHODS

    # `add` doesn't require any modifications
    def add(self, value: JSExpr):
        return None

    # `clear` doesn't require any modifications
    def clear(self):
        return None

    def pop(self):
        # JS Set.prototype.pop doesn't exist; emulate by taking first value
        x_expr, x_stmt = define_if_not_primary("$x", self.this)
        return iife(
            [
                x_stmt,
                JSConstAssign("$it", JSMemberCall(x_expr, "values", [])),
                JSConstAssign("$r", JSMemberCall(JSIdentifier("$it"), "next", [])),
                JSIf(
                    JSUnary("!", JSMember(JSIdentifier("$r"), "done")),
                    [
                        JSConstAssign("$v", JSMember(JSIdentifier("$r"), "value")),
                        JSSingleStmt(
                            JSMemberCall(x_expr, "delete", [JSIdentifier("$v")])
                        ),
                        JSReturn(JSIdentifier("$v")),
                    ],
                    [],
                ),
            ]
        )

    def remove(self, value: JSExpr):
        # Python remove errors when missing; here we just call delete()
        return JSMemberCall(self.this, "delete", [value])


SET_METHODS = {k for k in SetMethods.__dict__.keys() if not k.startswith("__")}


class DictMethods(BuiltinMethods):
    @classmethod
    def __runtime_check__(cls, expr: JSExpr):
        return JSBinary(expr, "instanceof", JSIdentifier("Map"))

    @classmethod
    def __methods__(cls):
        return DICT_METHODS

    def get(self, key: JSExpr, default: JSExpr | None = None):
        if default is None:
            return None  # Fall through to just calling .get()
        return JSBinary(
            JSMemberCall(self.this, "get", [key]),
            "??",
            default or JSUndefined(),
        )

    def keys(self):
        return JSArray([JSSpread(JSMemberCall(self.this, "keys", []))])

    def values(self):
        return JSArray([JSSpread(JSMemberCall(self.this, "values", []))])

    def items(self):
        return JSArray([JSSpread(JSMemberCall(self.this, "entries", []))])

    def copy(self):
        return JSNew(
            JSIdentifier("Map"),
            [JSMemberCall(self.this, "entries", [])],
        )

    def pop(self, key: JSExpr, default: JSExpr | None = None):
        # Map pop: get then delete, else return default/undefined
        x_expr, x_stmt = define_if_not_primary("$x", self.this)
        k_expr, k_stmt = define_if_not_primary("$k", key)
        return iife(
            [
                x_stmt,
                k_stmt,
                JSIf(
                    JSMemberCall(x_expr, "has", [k_expr]),
                    [
                        JSConstAssign("$v", JSMemberCall(x_expr, "get", [k_expr])),
                        JSSingleStmt(JSMemberCall(x_expr, "delete", [k_expr])),
                        JSReturn(JSIdentifier("$v")),
                    ],
                    [JSReturn(default or JSUndefined())],
                ),
            ]
        )

    def popitem(self):
        x_expr, x_stmt = define_if_not_primary("$x", self.this)
        return iife(
            [
                x_stmt,
                JSConstAssign(
                    "$k", JSMemberCall(JSMemberCall(x_expr, "keys", []), "next", [])
                ),
                JSIf(
                    JSMember(JSIdentifier("$k"), "done"),
                    [JSReturn(JSUndefined())],
                    [
                        JSConstAssign(
                            "$v",
                            JSMemberCall(
                                x_expr, "get", [JSMember(JSIdentifier("$k"), "value")]
                            ),
                        ),
                        JSSingleStmt(
                            JSMemberCall(x_expr, "delete", [JSIdentifier("$k")])
                        ),
                        JSReturn(JSArray([JSIdentifier("$k"), JSIdentifier("$v")])),
                    ],
                ),
            ]
        )

    def setdefault(self, key: JSExpr, default: JSExpr | None = None):
        default_expr = default if default is not None else JSUndefined()
        x_expr, x_stmt = define_if_not_primary("$x", self.this)
        k_expr, k_stmt = define_if_not_primary("$k", key)
        # Optimization
        core_expr = JSTertiary(
            JSMemberCall(x_expr, "has", [k_expr]),
            JSMemberCall(x_expr, "get", [k_expr]),
            JSComma(
                [
                    JSMemberCall(x_expr, "set", [k_expr, default_expr]),
                    default_expr,
                ]
            ),
        )
        if x_stmt is None and k_stmt is None:
            return core_expr
        return iife(
            [
                x_stmt,
                k_stmt,
                JSReturn(core_expr),
            ]
        )

    def update(self, other: JSExpr):
        # For maps, accept either Map or object and merge
        x, x_def = define_if_not_primary("$x", self.this)
        o, o_def = define_if_not_primary("$o", other)
        return iife(
            [
                x_def,
                o_def,
                JSIf(
                    JSBinary(o, "instanceof", JSIdentifier("Map")),
                    [
                        JSForOf(
                            ["k", "v"],
                            o,
                            [
                                JSSingleStmt(
                                    JSMemberCall(
                                        x,
                                        "set",
                                        [JSIdentifier("k"), JSIdentifier("v")],
                                    )
                                )
                            ],
                        )
                    ],
                    [
                        JSIf(
                            JSLogicalChain(
                                "&&",
                                [
                                    o,
                                    JSBinary(
                                        JSUnary("typeof", o),
                                        "===",
                                        JSString("object"),
                                    ),
                                ],
                            ),
                            [
                                JSForOf(
                                    "k",
                                    JSMemberCall(JSIdentifier("Object"), "keys", [o]),
                                    [
                                        JSIf(
                                            JSCall(
                                                JSMember(
                                                    JSIdentifier("Object"), "hasOwn"
                                                ),
                                                [o, JSIdentifier("k")],
                                            ),
                                            [
                                                JSSingleStmt(
                                                    JSMemberCall(
                                                        x,
                                                        "set",
                                                        [
                                                            JSIdentifier("k"),
                                                            JSSubscript(
                                                                o, JSIdentifier("k")
                                                            ),
                                                        ],
                                                    )
                                                )
                                            ],
                                            [],
                                        )
                                    ],
                                )
                            ],
                            [],
                        )
                    ],
                ),
            ]
        )

    # `clear` doesn't require any modifications
    def clear(self):
        return None


DICT_METHODS = {k for k in DictMethods.__dict__.keys() if not k.startswith("__")}
