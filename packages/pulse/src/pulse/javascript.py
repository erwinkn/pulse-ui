from __future__ import annotations

"""
Minimal AST-to-JS transpiler for a restricted, pure subset of Python used to
define synchronous JavaScript callbacks in the Pulse UI runtime.

The goal is to translate small, side-effect-free Python functions into compact
JavaScript function expressions that can be inlined on the client where a sync
callback is required (e.g., chart formatters, sorters, small mappers).

Design constraints:
- Only a strict subset of Python is supported.
- No side effects, I/O, or global mutation.
- Only local variables and parameters may be referenced; free variables are
  rejected to avoid shipping ambient server state.
- A small whitelist of builtins is supported (min, max, abs, round, len, str,
  int, float) and simple attribute/subscript access.

The `@javascript` decorator compiles a function at definition-time and stores
metadata on the Python callable so the reconciler can send the compiled code to
the client.
"""

import ast
import hashlib
import inspect
import textwrap
from typing import Any, Callable


class JSCompilationError(Exception):
    pass


ALLOWED_BINOPS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Mod: "%",
    ast.Pow: "**",
}

ALLOWED_CMPOPS: dict[type[ast.cmpop], str] = {
    ast.Eq: "===",
    ast.NotEq: "!==",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}


def _mangle_identifier(name: str) -> str:
    # Keep simple characters; this can be expanded later if needed
    return name


class PyToJS(ast.NodeVisitor):
    """AST visitor that emits JavaScript from a restricted Python subset."""

    def __init__(self, fn_name: str, arg_names: list[str]) -> None:
        self.fn_name = fn_name
        self.arg_names = arg_names
        self.locals: set[str] = set(arg_names)
        self.freevars: set[str] = set()
        self._lines: list[str] = []

    def _const_joinedstr_to_str(self, node: ast.AST) -> str | None:
        """Return the literal string of a format spec if it is constant-only.

        For f-strings, ast.FormattedValue.format_spec can be a JoinedStr. We
        only support cases where the format spec is entirely constant text.
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    return None
            return "".join(parts)
        return None

    # --- Entrypoints ---------------------------------------------------------
    def emit_function(self, body: list[ast.stmt]) -> str:
        stmts = [self.emit_stmt(stmt) for stmt in body]
        body_code = "\n".join(s for s in stmts if s)
        # Validate that we did not reference free variables
        if self.freevars:
            names = ", ".join(sorted(self.freevars))
            raise JSCompilationError(
                f"Unsupported free variables referenced: {names}. "
                "Only parameters and local variables are allowed."
            )
        # Function expression with same parameter list
        params = ", ".join(self.arg_names)
        return f"function({params}){{\n{body_code}\n}}"

    # --- Statements ----------------------------------------------------------
    def emit_stmt(self, node: ast.stmt) -> str:
        if isinstance(node, ast.Return):
            expr = "null" if node.value is None else self.emit_expr(node.value)
            return f"return {expr};"
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise JSCompilationError(
                    "Only simple assignments to local names are supported."
                )
            target = node.targets[0].id
            target_ident = _mangle_identifier(target)
            value_code = self.emit_expr(node.value)
            # Use 'let' only on first assignment to a local name. Parameters
            # are considered locals from the start and thus won't be re-declared.
            if target in self.locals:
                return f"{target_ident} = {value_code};"
            else:
                self.locals.add(target)
                return f"let {target_ident} = {value_code};"
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                raise JSCompilationError("Only simple annotated assignments supported.")
            target = node.target.id
            target_ident = _mangle_identifier(target)
            value = "null" if node.value is None else self.emit_expr(node.value)
            if target in self.locals:
                return f"{target_ident} = {value};"
            else:
                self.locals.add(target)
                return f"let {target_ident} = {value};"
        if isinstance(node, ast.If):
            test = self.emit_expr(node.test)
            body = "\n".join(self.emit_stmt(s) for s in node.body)
            orelse = (
                "\n".join(self.emit_stmt(s) for s in node.orelse) if node.orelse else ""
            )
            if orelse:
                return f"if ({test}){{\n{body}\n}} else {{\n{orelse}\n}}"
            else:
                return f"if ({test}){{\n{body}\n}}"
        raise JSCompilationError(
            f"Unsupported statement: {ast.dump(node, include_attributes=False)}"
        )

    # --- Expressions ---------------------------------------------------------
    def emit_expr(self, node: ast.expr) -> str:
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, str):
                s = v.replace("\\", "\\\\").replace("`", "\\`")
                return f"`{s}`"  # prefer template literal for simplicity
            if v is None:
                return "null"
            if v is True:
                return "true"
            if v is False:
                return "false"
            return repr(v)
        if isinstance(node, ast.Name):
            ident = node.id
            if ident not in self.locals:
                # Track potential freevar usage
                self.freevars.add(ident)
            return _mangle_identifier(ident)
        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op not in ALLOWED_BINOPS:
                raise JSCompilationError(f"Operator not allowed: {op.__name__}")
            left = self.emit_expr(node.left)
            right = self.emit_expr(node.right)
            return f"({left} {ALLOWED_BINOPS[op]} {right})"
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return f"(-{self.emit_expr(node.operand)})"
            if isinstance(node.op, ast.UAdd):
                return f"(+{self.emit_expr(node.operand)})"
            if isinstance(node.op, ast.Not):
                return f"(!{self.emit_expr(node.operand)})"
            raise JSCompilationError("Unsupported unary op")
        if isinstance(node, ast.BoolOp):
            op = "&&" if isinstance(node.op, ast.And) else "||"
            return f"({f' {op} '.join(self.emit_expr(v) for v in node.values)})"
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise JSCompilationError("Only simple comparisons supported")
            op = type(node.ops[0])
            if op not in ALLOWED_CMPOPS:
                raise JSCompilationError("Comparison not allowed")
            left = self.emit_expr(node.left)
            right = self.emit_expr(node.comparators[0])
            return f"({left} {ALLOWED_CMPOPS[op]} {right})"
        if isinstance(node, ast.IfExp):
            test = self.emit_expr(node.test)
            body = self.emit_expr(node.body)
            orelse = self.emit_expr(node.orelse)
            return f"({test} ? {body} : {orelse})"
        if isinstance(node, ast.Call):
            # Whitelisted builtins and attribute calls
            if isinstance(node.func, ast.Name):
                fname = node.func.id
                args = [self.emit_expr(a) for a in node.args]
                if fname == "len" and len(args) == 1:
                    return f"({args[0]}?.length ?? 0)"
                if fname in {"min", "max"}:
                    return f"Math.{fname}({', '.join(args)})"
                if fname == "abs" and len(args) == 1:
                    return f"Math.abs({args[0]})"
                if fname == "round" and (1 <= len(args) <= 2):
                    # round(x) -> Math.round(x); round(x, n) -> Number(x).toFixed(n)
                    if len(args) == 1:
                        return f"Math.round({args[0]})"
                    return f"(Number({args[0]}).toFixed({args[1]}))"
                if fname == "str" and len(args) == 1:
                    return f"String({args[0]})"
                if fname == "int" and len(args) in (1, 2):
                    return f"parseInt({args[0]})"
                if fname == "float" and len(args) == 1:
                    return f"parseFloat({args[0]})"
                raise JSCompilationError(f"Call to unsupported function: {fname}()")
            if isinstance(node.func, ast.Attribute):
                obj = self.emit_expr(node.func.value)
                attr = node.func.attr
                args = [self.emit_expr(a) for a in node.args]
                # Allow common string methods
                if attr in {"lower", "upper", "strip"} and len(args) == 0:
                    mapping = {
                        "lower": "toLowerCase",
                        "upper": "toUpperCase",
                        "strip": "trim",
                    }
                    return f"({obj}.{mapping[attr]}())"
                return f"({obj}.{attr}({', '.join(args)}))"
        if isinstance(node, ast.Attribute):
            value = self.emit_expr(node.value)
            return f"({value}.{node.attr})"
        if isinstance(node, ast.Subscript):
            value = self.emit_expr(node.value)
            index = self.emit_expr(
                node.slice
                if not isinstance(node.slice, ast.Slice)
                else node.slice.lower or ast.Constant(0)
            )
            return f"({value}[{index}])"
        if isinstance(node, ast.JoinedStr):
            # Special-case a single formatted value like f"{x:.2f}" -> x.toFixed(2)
            if len(node.values) == 1 and isinstance(node.values[0], ast.FormattedValue):
                fv = node.values[0]
                if fv.format_spec is not None:
                    spec_str = self._const_joinedstr_to_str(fv.format_spec)
                    if (
                        spec_str is not None
                        and spec_str.startswith(".")
                        and spec_str.endswith("f")
                        and spec_str[1:-1].isdigit()
                    ):
                        precision = spec_str[1:-1]
                        inner = self.emit_expr(fv.value)
                        return f"{inner}.toFixed({precision})"

            # General f-strings -> backtick template
            parts: list[str] = []
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    s = part.value.replace("\\", "\\\\").replace("`", "\\`")
                    parts.append(s)
                elif isinstance(part, ast.FormattedValue):
                    expr_inner = self.emit_expr(part.value)
                    # Handle precision format like .2f within template literals
                    if part.format_spec is not None:
                        spec_str = self._const_joinedstr_to_str(part.format_spec)
                        if (
                            spec_str is not None
                            and spec_str.startswith(".")
                            and spec_str.endswith("f")
                            and spec_str[1:-1].isdigit()
                        ):
                            expr_inner = f"({expr_inner}).toFixed({spec_str[1:-1]})"
                    parts.append(f"${{{expr_inner}}}")
                else:
                    raise JSCompilationError("Unsupported f-string component")
            return "`" + "".join(parts) + "`"
        raise JSCompilationError(
            f"Unsupported expression: {ast.dump(node, include_attributes=False)}"
        )


def compile_python_to_js(fn: Callable[..., Any]) -> tuple[str, int, str]:
    """Compile a Python function to a JavaScript function expression.

    Returns (code, n_args, hash_prefix).
    """
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
    visitor = PyToJS(fn.__name__, arg_names)
    js_fn_expr = visitor.emit_function(fndef.body)
    n_args = len(arg_names)
    h = hashlib.sha256(js_fn_expr.encode("utf-8")).hexdigest()[:16]
    return js_fn_expr, n_args, h


def javascript(fn: Callable[..., Any] | None = None):
    """Decorator that compiles a Python function into JavaScript and stores
    metadata on the function object for the reconciler.

    Usage:
        @javascript
        def formatter(x):
            return f"{x:.2f}"
    """

    def decorator(inner: Callable[..., Any]):
        code, n_args, h = compile_python_to_js(inner)
        setattr(inner, "__pulse_js__", code)
        setattr(inner, "__pulse_js_n_args__", n_args)
        setattr(inner, "__pulse_js_hash__", h)
        return inner

    if fn is not None:
        return decorator(fn)
    return decorator
