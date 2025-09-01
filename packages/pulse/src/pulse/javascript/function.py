from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from dataclasses import dataclass, field
from typing import (
    Callable,
    Generic,
    NamedTuple,
    TypeVar,
    TypeVarTuple,
)

from .nodes import (
    JSArray,
    JSBoolean,
    JSCompilationError,
    JSExpr,
    JSFunctionDef,
    JSIdentifier,
    JSImport,
    JSNew,
    JSNumber,
    JSObjectExpr,
    JSProp,
    JSString,
)
from .reftable import ReferenceTable
from .transpiler import JsTranspiler

R = TypeVar("R")
Args = TypeVarTuple("Args")


class JsFunctionCode(NamedTuple):
    code: str
    hash: str


_JS_FUNCTION_CACHE: dict[Callable[..., object], "JsFunction"] = {}


def _const_to_js_expr(value: object) -> JSExpr:
    if value is None:
        # Represent None as undefined for our JS subset
        return JSIdentifier("undefined")
    if isinstance(value, bool):
        return JSBoolean(value)
    if isinstance(value, (int, float)):
        return JSNumber(value)
    if isinstance(value, str):
        return JSString(value)
    if isinstance(value, (list, tuple)):
        return JSArray([_const_to_js_expr(v) for v in value])
    if isinstance(value, (set, frozenset)):
        return JSNew(
            JSIdentifier("Set"), [JSArray([_const_to_js_expr(v) for v in value])]
        )
    if isinstance(value, dict):
        props: list[JSProp] = []
        for k, v in value.items():
            if not isinstance(k, str):
                raise JSCompilationError("Only string keys supported in constant dicts")
            props.append(JSProp(JSString(k), _const_to_js_expr(v)))
        return JSObjectExpr(props)
    raise JSCompilationError(f"Unsupported global constant: {type(value).__name__}")


@dataclass
class JsFunction(Generic[*Args, R]):
    fn: Callable[[*Args], R]
    expr: JSFunctionDef
    imports: list[JSImport] = field(default_factory=list)
    dependencies: list[JsFunction] = field(default_factory=list)
    js_name: str = ""

    def __init__(
        self,
        fn: Callable[[*Args], R],
        *,
        predeclared: set[str] | None = None,
        ref_table: dict[str, JSExpr] | None = None,
    ) -> None:
        self.fn = fn
        try:
            src = inspect.getsource(fn)
        except OSError as e:
            raise JSCompilationError(f"Cannot retrieve source for {fn}: {e}")

        src = textwrap.dedent(src)
        module = ast.parse(src)
        fndefs = [n for n in module.body if isinstance(n, ast.FunctionDef)]
        if not fndefs:
            raise JSCompilationError("No function definition found in source")
        # Choose the last function def in the block (common for decorators)
        fndef = fndefs[-1]

        arg_names = [arg.arg for arg in fndef.args.args]

        # Choose a stable JS name for this function
        try:
            own_src = inspect.getsource(fn)
        except OSError:
            own_src = fn.__name__
        h = hashlib.sha256(textwrap.dedent(own_src).encode("utf-8")).hexdigest()[:8]
        self.js_name = f"{fn.__name__}${h}"

        # Analyze closure
        closure = inspect.getclosurevars(fn)
        if closure.unbound:
            missing = ", ".join(sorted(closure.unbound))
            raise JSCompilationError(
                f"Unsupported free variables referenced: {missing}. Only parameters and local variables are allowed."
            )
        if closure.nonlocals:
            nonlocals = ", ".join(sorted(closure.nonlocals))
            raise JSCompilationError(
                f"Unsupported nonlocals referenced: {nonlocals}. Only parameters and local variables are allowed."
            )

        # Build refs and dependencies
        refs: dict[str, JSExpr] = {} if ref_table is None else dict(ref_table)
        deps: list[JsFunction] = []
        for name, val in closure.globals.items():
            if inspect.isfunction(val):
                jf = _JS_FUNCTION_CACHE.get(val)
                if jf is None:
                    jf = JsFunction(val)
                    _JS_FUNCTION_CACHE[val] = jf
                deps.append(jf)
                refs[name] = JSIdentifier(jf.js_name)
            else:
                # Permit certain well-known modules to be renamed (e.g., math -> Math)
                if getattr(val, "__name__", None) == "math":
                    refs[name] = JSIdentifier("Math")
                else:
                    refs[name] = _const_to_js_expr(val)

        # Predeclared identifiers are handled by the PyToJS constructor now

        ref = ReferenceTable(rename=refs, replace_function={}, replace_method={})
        visitor = JsTranspiler(
            fndef,
            arg_names,
            list(closure.globals.keys()),
            ref,
        )
        self.expr = visitor.transpile(fndef.body)
        self.dependencies = deps

    def emit(self):
        output: list[str] = []
        # Imports first
        output.extend(imp.emit() for imp in self.imports)
        output.append("\n")
        # Emit dependencies as const bindings
        for dep in self.dependencies:
            dep_code = dep.emit().code
            output.append(f"const {dep.js_name} = {dep_code};")
        output.append("\n")
        # Emit this function expression last
        output.append(self.expr.emit())

        # Combine all code
        code = "\n".join(output)

        h = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
        return JsFunctionCode(code, h)

    def __call__(self, *args: *Args) -> R:
        return self.fn(*args)


class ExternalJsFunction(Generic[*Args, R]):
    def __init__(
        self, name: str, src: str, is_default: bool, hint: Callable[[*Args], R]
    ) -> None:
        self.name = name
        self.src = src
        self.is_default = is_default
        self.hint = hint

    def __call__(self, *args: *Args) -> R: ...


def external_javascript(name: str, src: str, is_default=False):
    def decorator(fn: Callable[[*Args], R]):
        return ExternalJsFunction(name=name, src=src, is_default=is_default, hint=fn)

    return decorator


def javascript(fn: Callable[[*Args], R]):
    """Decorator that compiles a Python function into JavaScript and stores
    metadata on the function object for the reconciler.

    Usage:
        @javascript
        def formatter(x):
            return f"{x:.2f}"
    """

    def decorator(inner: Callable[[*Args], R]):
        return JsFunction(inner)

    if fn is not None:
        return decorator(fn)
    return decorator
