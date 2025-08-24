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
from dataclasses import dataclass
from typing import Any, Callable, List, Sequence, Tuple, Union


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


###############################################################################
# JS AST
###############################################################################


class JSNode:
    def emit(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


class JSExpr(JSNode):
    pass


class JSStmt(JSNode):
    pass


@dataclass
class JSIdentifier(JSExpr):
    name: str

    def emit(self) -> str:
        return self.name


@dataclass
class JSString(JSExpr):
    value: str

    def emit(self) -> str:
        s = self.value.replace("\\", "\\\\").replace("`", "\\`")
        return f"`{s}`"


@dataclass
class JSNumber(JSExpr):
    raw: str

    def emit(self) -> str:
        return self.raw


@dataclass
class JSBoolean(JSExpr):
    value: bool

    def emit(self) -> str:
        return "true" if self.value else "false"


class JSNull(JSExpr):
    def emit(self) -> str:
        return "null"


@dataclass
class JSArray(JSExpr):
    elements: Sequence[JSExpr]

    def emit(self) -> str:
        inner = ", ".join(e.emit() for e in self.elements)
        return f"[{inner}]"


@dataclass
class JSObject(JSExpr):
    # pairs are (string_key_already_escaped, value_expr)
    pairs: Sequence[Tuple[str, JSExpr]]

    def emit(self) -> str:
        inner = ", ".join(f'"{k}": {v.emit()}' for k, v in self.pairs)
        return "(" + "{" + inner + "}" + ")"


@dataclass
class JSParen(JSExpr):
    inner: JSExpr

    def emit(self) -> str:
        return f"({self.inner.emit()})"


@dataclass
class JSUnary(JSExpr):
    op: str  # '-', '+', '!'
    operand: JSExpr

    def emit(self) -> str:
        return f"({self.op}{self.operand.emit()})"


@dataclass
class JSBinary(JSExpr):
    left: JSExpr
    op: str
    right: JSExpr

    def emit(self) -> str:
        return f"({self.left.emit()} {self.op} {self.right.emit()})"


@dataclass
class JSLogicalChain(JSExpr):
    op: str  # '&&' or '||'
    values: Sequence[JSExpr]

    def emit(self) -> str:
        inner = f" {self.op} ".join(v.emit() for v in self.values)
        return f"({inner})"


@dataclass
class JSConditional(JSExpr):
    test: JSExpr
    if_true: JSExpr
    if_false: JSExpr

    def emit(self) -> str:
        return f"({self.test.emit()} ? {self.if_true.emit()} : {self.if_false.emit()})"


@dataclass
class JSTemplate(JSExpr):
    # parts are either raw strings (literal text) or JSExpr instances which are
    # emitted inside ${...}
    parts: Sequence[Union[str, JSExpr]]

    def emit(self) -> str:
        out: List[str] = ["`"]
        for p in self.parts:
            if isinstance(p, str):
                out.append(p.replace("\\", "\\\\").replace("`", "\\`"))
            else:
                out.append("${" + p.emit() + "}")
        out.append("`")
        return "".join(out)


@dataclass
class JSMember(JSExpr):
    obj: JSExpr
    prop: str
    wrap: bool = True

    def emit(self) -> str:
        code = f"{self.obj.emit()}.{self.prop}"
        return f"({code})" if self.wrap else code


@dataclass
class JSSubscript(JSExpr):
    obj: JSExpr
    index: JSExpr
    wrap: bool = True

    def emit(self) -> str:
        code = f"{self.obj.emit()}[{self.index.emit()}]"
        return f"({code})" if self.wrap else code


@dataclass
class JSCall(JSExpr):
    callee: JSExpr  # typically JSIdentifier
    args: Sequence[JSExpr]
    wrap: bool = False

    def emit(self) -> str:
        code = f"{self.callee.emit()}({', '.join(a.emit() for a in self.args)})"
        return f"({code})" if self.wrap else code


@dataclass
class JSMemberCall(JSExpr):
    obj: JSExpr
    method: str
    args: Sequence[JSExpr]
    wrap: bool = True

    def emit(self) -> str:
        code = f"{self.obj.emit()}.{self.method}({', '.join(a.emit() for a in self.args)})"
        return f"({code})" if self.wrap else code


@dataclass
class JSArrowFunction(JSExpr):
    params_code: str  # already formatted e.g. 'x' or '(a, b)' or '([k, v])'
    body: JSExpr

    def emit(self) -> str:
        return f"{self.params_code} => {self.body.emit()}"


@dataclass
class JSNullishCoalesce(JSExpr):
    left: JSExpr
    right: JSExpr

    def emit(self) -> str:
        return f"({self.left.emit()} ?? {self.right.emit()})"


@dataclass
class JSOptionalLength(JSExpr):
    expr: JSExpr

    def emit(self) -> str:
        return f"({self.expr.emit()}?.length ?? 0)"


@dataclass
class JSReturn(JSStmt):
    value: Union[JSExpr, None]

    def emit(self) -> str:
        return f"return {(self.value.emit() if self.value is not None else 'null')};"


@dataclass
class JSAssign(JSStmt):
    name: str
    value: JSExpr
    declare: bool = False  # when True emit 'let name = ...'

    def emit(self) -> str:
        if self.declare:
            return f"let {self.name} = {self.value.emit()};"
        return f"{self.name} = {self.value.emit()};"


@dataclass
class JSAugAssign(JSStmt):
    name: str
    op: str
    value: JSExpr

    def emit(self) -> str:
        return f"{self.name} {self.op}= {self.value.emit()};"


@dataclass
class JSIf(JSStmt):
    test: JSExpr
    body: Sequence[JSStmt]
    orelse: Sequence[JSStmt]

    def emit(self) -> str:
        body_code = "\n".join(s.emit() for s in self.body)
        if not self.orelse:
            return f"if ({self.test.emit()}){{\n{body_code}\n}}"
        else_code = "\n".join(s.emit() for s in self.orelse)
        return f"if ({self.test.emit()}){{\n{body_code}\n}} else {{\n{else_code}\n}}"


@dataclass
class JSFunctionExpr(JSExpr):
    params: Sequence[str]
    body: Sequence[JSStmt]

    def emit(self) -> str:
        params = ", ".join(self.params)
        body_code = "\n".join(s.emit() for s in self.body)
        return f"function({params}){{\n{body_code}\n}}"


###############################################################################
# Python AST -> JS AST
###############################################################################


class PyToJS(ast.NodeVisitor):
    """AST visitor that builds a JS AST from a restricted Python subset."""

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

    def _parse_format_spec(self, spec: str) -> dict[str, object]:
        """Parse a Python format specification mini-language string.

        Returns a dict with keys: fill, align, sign, alt, zero, width, grouping,
        precision, type. Values may be None.
        """
        i = 0
        n = len(spec)
        fill: str | None = None
        align: str | None = None
        sign: str | None = None
        alt: bool = False
        zero: bool = False
        width: int | None = None
        grouping: str | None = None
        precision: int | None = None
        typ: str | None = None

        # [fill][align]
        if n - i >= 2 and spec[i + 1] in "<>^=":
            fill = spec[i]
            align = spec[i + 1]
            i += 2
        elif i < n and spec[i] in "<>^=":
            align = spec[i]
            i += 1

        # [sign]
        if i < n and spec[i] in "+- ":
            sign = spec[i]
            i += 1

        # [#]
        if i < n and spec[i] == "#":
            alt = True
            i += 1

        # [0]
        if i < n and spec[i] == "0":
            zero = True
            i += 1

        # [width]
        start = i
        while i < n and spec[i].isdigit():
            i += 1
        if i > start:
            width = int(spec[start:i])

        # [grouping]
        if i < n and spec[i] in ",_":
            grouping = spec[i]
            i += 1

        # [.precision]
        if i < n and spec[i] == ".":
            i += 1
            start = i
            while i < n and spec[i].isdigit():
                i += 1
            if i > start:
                precision = int(spec[start:i])
            else:
                precision = 0

        # [type]
        if i < n:
            typ = spec[i]

        return {
            "fill": fill,
            "align": align,
            "sign": sign,
            "alt": alt,
            "zero": zero,
            "width": width,
            "grouping": grouping,
            "precision": precision,
            "type": typ,
        }

    def _arrow_param_from_target(self, target: ast.expr) -> tuple[str, list[str]]:
        if isinstance(target, ast.Name):
            return target.id, [target.id]
        if isinstance(target, ast.Tuple) and all(
            isinstance(e, ast.Name) for e in target.elts
        ):
            names = [e.id for e in target.elts]
            return f"([{', '.join(names)}])", names
        raise JSCompilationError(
            "Only name or 2-tuple targets supported in comprehensions"
        )

    def _build_comp_chain(
        self, gen: ast.comprehension, pred_nodes: list[ast.expr]
    ) -> tuple[JSExpr, str, list[str]]:
        iter_expr = self.emit_expr(gen.iter)
        param_str, name_list = self._arrow_param_from_target(gen.target)
        chain: JSExpr = iter_expr
        if pred_nodes:
            old_locals = set(self.locals)
            for n in name_list:
                self.locals.add(n)
            if len(pred_nodes) == 1:
                pred = self.emit_expr(pred_nodes[0])
            else:
                pred = JSLogicalChain(
                    op="&&", values=[self.emit_expr(cond) for cond in pred_nodes]
                )
            self.locals = old_locals
            chain = JSMemberCall(
                iter_expr,
                "filter",
                [JSArrowFunction(param_str, JSParen(pred))],
                wrap=False,
            )
        return chain, param_str, name_list

    def _apply_format_spec(
        self, value_expr: JSExpr, value_node: ast.expr, spec: str
    ) -> JSExpr:
        spec_info = self._parse_format_spec(spec)
        fill = spec_info["fill"] or " "
        align = spec_info["align"]  # may be None
        sign = spec_info["sign"]  # '+', '-', ' ', or None
        alt = bool(spec_info["alt"])  # bool
        zero = bool(spec_info["zero"])  # bool
        width = spec_info["width"]  # int | None
        grouping = spec_info["grouping"]  # ',', '_' or None
        precision = spec_info["precision"]  # int | None
        typ = spec_info["type"]  # str | None

        # Validate support
        allowed_types = {
            None,
            "s",
            "c",
            "d",
            "b",
            "o",
            "x",
            "X",
            "f",
            "F",
            "e",
            "E",
            "g",
            "G",
            "n",
            "%",
        }
        if typ not in allowed_types:
            raise JSCompilationError(f"Unsupported format type: {typ}")
        if grouping == "_":
            raise JSCompilationError(
                "Unsupported grouping separator '_' in format spec"
            )
        if align == "=" and typ in {None, "s"}:
            raise JSCompilationError(
                "Alignment '=' is only supported for numeric types"
            )

        # Escape backtick in fill if present
        fill_js = fill.replace("\\", "\\\\").replace("`", "\\`")
        fill_lit = JSString(fill_js)

        # Special-case minimal 'f' with only precision (no width/align/sign/etc.)
        if (
            typ in {"f", "F"}
            and precision is not None
            and align is None
            and sign is None
            and not alt
            and not zero
            and width is None
            and grouping is None
        ):
            # Match prior behavior: x.toFixed(p)
            return JSMemberCall(value_expr, "toFixed", [JSNumber(str(precision))], wrap=False)
        # Build numeric/string representations
        base_expr: JSExpr
        prefix_expr: JSExpr = JSTemplate([])  # empty template literal ``
        if typ is None:
            # Default to string conversion
            base_expr = JSCall(JSIdentifier("String"), [value_expr])
        elif typ == "s":
            base_expr = JSCall(JSIdentifier("String"), [value_expr])
            if precision is not None:
                base_expr = JSParen(
                    JSCall(JSMember(base_expr, "slice"), [JSNumber(str(precision))])
                )
        elif typ == "c":
            base_expr = JSCall(
                JSIdentifier("String.fromCharCode"),
                [JSCall(JSIdentifier("Number"), [value_expr])],
            )
        elif typ in {"d", "b", "o", "x", "X"}:
            num = JSCall(JSIdentifier("Number"), [value_expr])
            abs_num = JSCall(JSIdentifier("Math.abs"), [num])
            if typ == "d":
                digits: JSExpr = JSCall(
                    JSIdentifier("String"), [JSCall(JSIdentifier("Math.trunc"), [abs_num])]
                )
            else:
                base_map = {"b": 2, "o": 8, "x": 16, "X": 16}
                digits = JSParen(
                    JSMemberCall(
                        JSCall(JSIdentifier("Math.trunc"), [abs_num]),
                        "toString",
                        [JSNumber(str(base_map[typ]))],
                    )
                )
                if typ == "X":
                    digits = JSParen(JSMemberCall(digits, "toUpperCase", []))
            if alt and typ in {"b", "o", "x", "X"}:
                prefix = {"b": "0b", "o": "0o", "x": "0x", "X": "0X"}[typ]
                prefix_expr = JSString(prefix)
            # Apply grouping for decimal with comma
            if grouping == "," and typ == "d":
                # Use locale formatting for thousands separators
                digits = JSParen(
                    JSMemberCall(
                        JSCall(JSIdentifier("Math.trunc"), [abs_num]),
                        "toLocaleString",
                        [JSString("en-US")],
                    )
                )
            base_expr = digits
        elif typ in {"f", "F", "e", "E", "g", "G", "n", "%"}:
            num = JSCall(JSIdentifier("Number"), [value_expr])
            abs_num = JSCall(JSIdentifier("Math.abs"), [num])
            if typ in {"f", "F"}:
                p = precision if precision is not None else 6
                if grouping == ",":
                    s = JSParen(
                        JSMemberCall(
                            JSCall(JSIdentifier("Number"), [abs_num]),
                            "toLocaleString",
                            [
                                JSString("en-US"),
                                JSIdentifier(
                                    f"{{minimumFractionDigits: {p}, maximumFractionDigits: {p}}}"
                                ),
                            ],
                        )
                    )
                else:
                    s = JSMemberCall(
                        JSCall(JSIdentifier("Number"), [abs_num]),
                        "toFixed",
                        [JSNumber(str(p))],
                    )
            elif typ in {"e", "E"}:
                p = precision if precision is not None else 6
                s = JSMemberCall(
                    JSCall(JSIdentifier("Number"), [abs_num]),
                    "toExponential",
                    [JSNumber(str(p))],
                )
                if typ == "E":
                    s = JSParen(JSMemberCall(s, "toUpperCase", []))
            elif typ in {"g", "G"}:
                p = precision if precision is not None else 6
                s = JSMemberCall(
                    JSCall(JSIdentifier("Number"), [abs_num]),
                    "toPrecision",
                    [JSNumber(str(p))],
                )
                if typ == "G":
                    s = JSParen(JSMemberCall(s, "toUpperCase", []))
            elif typ == "n":
                if precision is None:
                    s = JSMemberCall(
                        JSCall(JSIdentifier("Number"), [abs_num]),
                        "toLocaleString",
                        [JSString("en-US")],
                    )
                else:
                    s = JSParen(
                        JSMemberCall(
                            JSCall(JSIdentifier("Number"), [abs_num]),
                            "toLocaleString",
                            [
                                JSString("en-US"),
                                JSIdentifier(
                                    f"{{minimumFractionDigits: {precision}, maximumFractionDigits: {precision}}}"
                                ),
                            ],
                        )
                    )
            else:  # '%'
                p = precision if precision is not None else 6
                s = JSBinary(
                    left=JSMemberCall(
                        JSBinary(JSCall(JSIdentifier("Number"), [abs_num]), "*", JSNumber("100")),
                        "toFixed",
                        [JSNumber(str(p))],
                    ),
                    op="+",
                    right=JSString("%"),
                )
            base_expr = s
        else:
            # Fallback to String conversion
            base_expr = JSCall(JSIdentifier("String"), [value_expr])

        # Apply sign for numeric types
        if typ in {"d", "b", "o", "x", "X", "f", "F", "e", "E", "g", "G", "n", "%"}:
            num = JSCall(JSIdentifier("Number"), [value_expr])
            cond = JSBinary(num, "<", JSNumber("0"))
            if sign == "+":
                sign_expr: JSExpr = JSConditional(cond, JSString("-"), JSString("+"))
            elif sign == " ":
                sign_expr = JSConditional(cond, JSString("-"), JSString(" "))
            else:
                sign_expr = JSConditional(cond, JSString("-"), JSTemplate([]))
        else:
            sign_expr = JSTemplate([])

        # Combine sign/prefix and base
        # Combine sign/prefix with base
        def is_empty_template(e: JSExpr) -> bool:
            return isinstance(e, JSTemplate) and len(e.parts) == 0

        if not is_empty_template(prefix_expr) or not is_empty_template(sign_expr):
            combined: JSExpr = JSBinary(JSBinary(sign_expr, "+", prefix_expr), "+", base_expr)
        else:
            combined = base_expr

        # Width, alignment and zero-padding
        if width is not None and width > 0:
            if align == "^":
                combined = JSParen(
                    JSMemberCall(
                        JSMemberCall(
                            combined,
                            "padStart",
                            [
                                JSCall(
                                    JSIdentifier("Math.floor"),
                                    [
                        JSBinary(
                            JSNumber(str(width)),
                            "+",
                            JSMember(JSParen(combined), "length", wrap=False),
                        )
                                    ],
                                ),
                                fill_lit,
                            ],
                        ),
                        "padEnd",
                        [JSNumber(str(width)), fill_lit],
                    )
                )
            elif align == "<":
                combined = JSParen(
                    JSMemberCall(combined, "padEnd", [JSNumber(str(width)), fill_lit])
                )
            elif align == "=":
                if typ in {
                    "d",
                    "b",
                    "o",
                    "x",
                    "X",
                    "f",
                    "F",
                    "e",
                    "E",
                    "g",
                    "G",
                    "n",
                    "%",
                }:
                    # Width should be like: width - ((sign).length)
                    # Prefer sign only for length when prefix is empty
                    def is_empty_template(e: JSExpr) -> bool:
                        return isinstance(e, JSTemplate) and len(e.parts) == 0

                    if is_empty_template(prefix_expr):
                        head_for_len = sign_expr
                    else:
                        head_for_len = JSBinary(sign_expr, "+", prefix_expr)
                    width_arg = JSIdentifier(f"{width} - (({head_for_len.emit()})).length")
                    tail = base_expr
                    combined = JSBinary(
                        JSParen(JSBinary(sign_expr, "+", prefix_expr)),
                        "+",
                        JSMemberCall(
                            tail,
                            "padStart",
                            [
                                width_arg,
                                fill_lit,
                            ],
                            wrap=False,
                        ),
                    )
                else:
                    combined = JSParen(
                        JSMemberCall(combined, "padStart", [JSNumber(str(width)), fill_lit])
                    )
            else:
                pad_fill = fill_lit if not zero else JSString("0")
                if (
                    zero
                    and align is None
                    and typ in {"d", "f", "F", "e", "E", "g", "G", "n", "%"}
                ):
                    head = sign_expr
                    tail = base_expr
                    zero_padded = JSBinary(
                        head,
                        "+",
                        JSMemberCall(
                            tail,
                            "padStart",
                            [
                                JSBinary(JSNumber(str(width)), "-", JSMember(head, "length")),
                                JSString("0"),
                            ],
                        ),
                    )
                    if not is_empty_template(prefix_expr):
                        head2 = JSParen(JSBinary(head, "+", prefix_expr))
                        zero_padded = JSBinary(
                            head2,
                            "+",
                            JSMemberCall(
                                tail,
                                "padStart",
                                [
                                    JSBinary(
                                        JSNumber(str(width)),
                                        "-",
                                        JSMember(JSParen(head2), "length", wrap=False),
                                    ),
                                    JSString("0"),
                                ],
                            ),
                        )
                    combined = zero_padded
                else:
                    combined = JSParen(
                        JSMemberCall(combined, "padStart", [JSNumber(str(width)), pad_fill])
                    )

        return combined

    def _emit_slice_index_arg(self, node: ast.expr) -> JSExpr:
        """Emit a slice index argument without redundant parentheses for negatives.

        Ensures that a unary negative integer like -2 is emitted as -2 (not (-2)).
        """
        # -<int>
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, int)
        ):
            return JSNumber(f"-{node.operand.value}")
        return self.emit_expr(node)

    def _emit_single_compare(
        self,
        left_expr: JSExpr,
        left_node: ast.expr,
        op: ast.cmpop,
        right_expr: JSExpr,
        right_node: ast.expr,
    ) -> JSExpr:
        # Identity comparisons with None
        if isinstance(op, ast.Is) or isinstance(op, ast.IsNot):
            is_not = isinstance(op, ast.IsNot)
            if (isinstance(right_node, ast.Constant) and right_node.value is None) or (
                isinstance(left_node, ast.Constant) and left_node.value is None
            ):
                # normalize to <expr> === null
                expr = right_expr if isinstance(left_node, ast.Constant) else left_expr
                return JSBinary(expr, "!==" if is_not else "===", JSNull())
            raise JSCompilationError("'is'/'is not' only supported with None")
        # Membership
        if isinstance(op, ast.In) or isinstance(op, ast.NotIn):
            inner_call = JSMemberCall(right_expr, "includes", [left_expr])
            if isinstance(op, ast.NotIn):
                return JSUnary("!", inner_call)
            return inner_call
        # Standard comparisons
        op_type = type(op)
        if op_type not in ALLOWED_CMPOPS:
            raise JSCompilationError("Comparison not allowed")
        return JSBinary(left_expr, ALLOWED_CMPOPS[op_type], right_expr)

    # --- Entrypoints ---------------------------------------------------------
    def emit_function(self, body: list[ast.stmt]) -> JSFunctionExpr:
        stmts: list[JSStmt] = []
        for stmt in body:
            s = self.emit_stmt(stmt)
            if s is None:
                continue
            stmts.append(s)
        # Validate that we did not reference free variables
        if self.freevars:
            names = ", ".join(sorted(self.freevars))
            raise JSCompilationError(
                f"Unsupported free variables referenced: {names}. "
                "Only parameters and local variables are allowed."
            )
        # Function expression
        return JSFunctionExpr(self.arg_names, stmts)

    # --- Statements ----------------------------------------------------------
    def emit_stmt(self, node: ast.stmt) -> JSStmt:
        if isinstance(node, ast.Return):
            expr = None if node.value is None else self.emit_expr(node.value)
            return JSReturn(expr)
        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                raise JSCompilationError("Only simple augmented assignments supported.")
            target = _mangle_identifier(node.target.id)
            # Support only whitelisted binary ops via mapping
            op_type = type(node.op)
            if op_type not in ALLOWED_BINOPS:
                raise JSCompilationError("AugAssign operator not allowed")
            value_expr = self.emit_expr(node.value)
            return JSAugAssign(target, ALLOWED_BINOPS[op_type], value_expr)
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise JSCompilationError(
                    "Only simple assignments to local names are supported."
                )
            target = node.targets[0].id
            target_ident = _mangle_identifier(target)
            value_expr = self.emit_expr(node.value)
            # Use 'let' only on first assignment to a local name. Parameters
            # are considered locals from the start and thus won't be re-declared.
            if target in self.locals:
                return JSAssign(target_ident, value_expr, declare=False)
            else:
                self.locals.add(target)
                return JSAssign(target_ident, value_expr, declare=True)
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                raise JSCompilationError("Only simple annotated assignments supported.")
            target = node.target.id
            target_ident = _mangle_identifier(target)
            value = JSNull() if node.value is None else self.emit_expr(node.value)
            if target in self.locals:
                return JSAssign(target_ident, value, declare=False)
            else:
                self.locals.add(target)
                return JSAssign(target_ident, value, declare=True)
        if isinstance(node, ast.If):
            test = self.emit_expr(node.test)
            body = [self.emit_stmt(s) for s in node.body]
            orelse = [self.emit_stmt(s) for s in node.orelse] if node.orelse else []
            return JSIf(test, body, orelse)
        raise JSCompilationError(
            f"Unsupported statement: {ast.dump(node, include_attributes=False)}"
        )

    # --- Expressions ---------------------------------------------------------
    def emit_expr(self, node: ast.expr) -> JSExpr:
        if isinstance(node, ast.ListComp):
            # Support single-generator list comprehension with optional ifs.
            if len(node.generators) != 1:
                raise JSCompilationError(
                    "Only single 'for' comprehensions are supported"
                )
            gen = node.generators[0]
            if gen.is_async:
                raise JSCompilationError("Async comprehensions are not supported")
            iter_expr = self.emit_expr(gen.iter)
            chain, param, name_list = self._build_comp_chain(gen, gen.ifs)
            # Map if the element expression is not a direct identity
            old_locals2 = set(self.locals)
            for n in name_list:
                self.locals.add(n)
            elt_expr = self.emit_expr(node.elt)
            self.locals = old_locals2
            if (
                isinstance(node.elt, ast.Name)
                and node.elt.id in name_list
                and chain.emit() != iter_expr.emit()
            ):
                return JSParen(chain)
            mapper = JSArrowFunction(param, elt_expr)
            if chain.emit() == iter_expr.emit():
                return JSMemberCall(iter_expr, "map", [mapper])
            return JSMemberCall(chain, "map", [mapper])
        if isinstance(node, ast.GeneratorExp):
            # Similar to ListComp but returns a chained array expression
            if len(node.generators) != 1:
                raise JSCompilationError("Only single 'for' generators are supported")
            gen = node.generators[0]
            if gen.is_async:
                raise JSCompilationError("Async generators are not supported")
            iter_expr = self.emit_expr(gen.iter)
            chain, param, name_list = self._build_comp_chain(gen, gen.ifs)
            old_locals2 = set(self.locals)
            for n in name_list:
                self.locals.add(n)
            elt_expr = self.emit_expr(node.elt)
            self.locals = old_locals2
            if (
                isinstance(node.elt, ast.Name)
                and node.elt.id in name_list
                and chain.emit() != iter_expr.emit()
            ):
                return JSParen(chain)
            mapper = JSArrowFunction(param, elt_expr)
            if chain.emit() == iter_expr.emit():
                return JSMemberCall(iter_expr, "map", [mapper])
            return JSMemberCall(chain, "map", [mapper])
        if isinstance(node, ast.DictComp):
            if len(node.generators) != 1:
                raise JSCompilationError(
                    "Only single 'for' dict comprehensions are supported"
                )
            gen = node.generators[0]
            if gen.is_async:
                raise JSCompilationError("Async comprehensions are not supported")
            chain, param, name_list = self._build_comp_chain(gen, gen.ifs)
            old_locals = set(self.locals)
            for n in name_list:
                self.locals.add(n)
            key_expr = self.emit_expr(node.key)
            val_expr = self.emit_expr(node.value)
            self.locals = old_locals
            # Ensure string keys for JS object entries
            key_to_str = JSCall(JSIdentifier("String"), [key_expr])
            entry_arr = JSArray([key_to_str, val_expr])
            mapper = JSArrowFunction(param, entry_arr)
            iter_expr2 = self.emit_expr(gen.iter)
            if chain.emit() == iter_expr2.emit():
                entries = JSMemberCall(iter_expr2, "map", [mapper], wrap=False)
            else:
                entries = JSMemberCall(chain, "map", [mapper], wrap=False)
            return JSParen(JSCall(JSIdentifier("Object.fromEntries"), [entries]))
        if isinstance(node, ast.List):
            return JSArray([self.emit_expr(e) for e in node.elts])
        if isinstance(node, ast.Tuple):
            return JSArray([self.emit_expr(e) for e in node.elts])
        if isinstance(node, ast.Dict):
            pairs: list[Tuple[str, JSExpr]] = []
            for k, v in zip(node.keys, node.values):
                if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                    raise JSCompilationError(
                        "Only string literal dict keys are supported"
                    )
                key_str = k.value.replace("\\", "\\\\").replace('"', '\\"')
                val_expr = self.emit_expr(v)
                pairs.append((key_str, val_expr))
            return JSObject(pairs)
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, str):
                return JSString(v)
            if v is None:
                return JSNull()
            if v is True:
                return JSBoolean(True)
            if v is False:
                return JSBoolean(False)
            return JSNumber(repr(v))
        if isinstance(node, ast.Name):
            ident = node.id
            if ident not in self.locals:
                # Track potential freevar usage
                self.freevars.add(ident)
            return JSIdentifier(_mangle_identifier(ident))
        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op not in ALLOWED_BINOPS:
                raise JSCompilationError(f"Operator not allowed: {op.__name__}")
            left = self.emit_expr(node.left)
            right = self.emit_expr(node.right)
            return JSBinary(left, ALLOWED_BINOPS[op], right)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                # Emit bare negative numeric literals without extra parens
                if isinstance(node.operand, ast.Constant) and isinstance(
                    node.operand.value, (int, float)
                ):
                    return JSNumber(f"-{repr(node.operand.value)}")
                return JSUnary("-", self.emit_expr(node.operand))
            if isinstance(node.op, ast.UAdd):
                if isinstance(node.operand, ast.Constant) and isinstance(
                    node.operand.value, (int, float)
                ):
                    return JSNumber(f"+{repr(node.operand.value)}")
                return JSUnary("+", self.emit_expr(node.operand))
            if isinstance(node.op, ast.Not):
                return JSUnary("!", self.emit_expr(node.operand))
            raise JSCompilationError("Unsupported unary op")
        if isinstance(node, ast.BoolOp):
            op = "&&" if isinstance(node.op, ast.And) else "||"
            return JSLogicalChain(op, [self.emit_expr(v) for v in node.values])
        if isinstance(node, ast.Compare):
            # Support chained comparisons, identity with None, and membership
            # Build sequential comparisons combined with &&
            operands: list[ast.expr] = [node.left, *node.comparators]
            exprs: list[JSExpr] = [self.emit_expr(e) for e in operands]
            parts: list[JSExpr] = []
            for i, op in enumerate(node.ops):
                left_node = operands[i]
                right_node = operands[i + 1]
                left_expr = exprs[i]
                right_expr = exprs[i + 1]
                parts.append(
                    self._emit_single_compare(
                        left_expr, left_node, op, right_expr, right_node
                    )
                )
            if len(parts) == 1:
                return parts[0]
            return JSLogicalChain("&&", parts)
        if isinstance(node, ast.IfExp):
            test = self.emit_expr(node.test)
            body = self.emit_expr(node.body)
            orelse = self.emit_expr(node.orelse)
            return JSConditional(test, body, orelse)
        if isinstance(node, ast.Call):
            # Whitelisted builtins and attribute calls
            if isinstance(node.func, ast.Name):
                fname = node.func.id
                args = [self.emit_expr(a) for a in node.args]
                # Support keyword arguments for round/int
                kw_map: dict[str, JSExpr] = {}
                for kw in node.keywords:
                    if kw.arg is None:
                        raise JSCompilationError("**kwargs not supported")
                    kw_map[kw.arg] = self.emit_expr(kw.value)
                if fname == "len" and len(args) == 1:
                    return JSOptionalLength(args[0])
                if fname in {"min", "max"}:
                    return JSCall(JSIdentifier(f"Math.{fname}"), args)
                if fname == "abs" and len(args) == 1:
                    return JSCall(JSIdentifier("Math.abs"), args)
                if fname == "round":
                    if kw_map:
                        # round(number=x) or round(number=x, ndigits=2)
                        num = kw_map.get("number")
                        nd = kw_map.get("ndigits")
                        if num is None:
                            raise JSCompilationError(
                                "round() requires 'number' kw when using keywords"
                            )
                        if nd is None:
                            return JSCall(JSIdentifier("Math.round"), [num])
                        return JSParen(
                            JSMemberCall(
                                JSCall(JSIdentifier("Number"), [num]),
                                "toFixed",
                                [nd],
                                wrap=False,
                            )
                        )
                    # positional
                    if not (1 <= len(args) <= 2):
                        raise JSCompilationError("round() arity not supported")
                    # round(x) -> Math.round(x); round(x, n) -> Number(x).toFixed(n)
                    if len(args) == 1:
                        return JSCall(JSIdentifier("Math.round"), [args[0]])
                    return JSParen(
                        JSMemberCall(
                            JSCall(JSIdentifier("Number"), [args[0]]),
                            "toFixed",
                            [args[1]],
                            wrap=False,
                        )
                    )
                if fname == "str" and len(args) == 1:
                    return JSCall(JSIdentifier("String"), [args[0]])
                if fname == "int":
                    if kw_map:
                        num = kw_map.get("x")
                        base = kw_map.get("base")
                        if num is None:
                            raise JSCompilationError(
                                "int() requires 'x' kw when using keywords"
                            )
                        if base is None:
                            return JSCall(JSIdentifier("parseInt"), [num])
                        return JSCall(JSIdentifier("parseInt"), [num, base])
                    if len(args) in (1, 2):
                        # When base is provided positionally, include it
                        if len(args) == 1:
                            return JSCall(JSIdentifier("parseInt"), [args[0]])
                        return JSCall(JSIdentifier("parseInt"), [args[0], args[1]])
                if fname == "float" and len(args) == 1:
                    return JSCall(JSIdentifier("parseFloat"), [args[0]])
                if fname == "list" and len(args) == 1:
                    return JSParen(args[0])
                if fname in {"any", "all"} and len(node.args) == 1:
                    gen_arg = node.args[0]
                    if (
                        isinstance(gen_arg, ast.GeneratorExp)
                        and len(gen_arg.generators) == 1
                    ):
                        gen = gen_arg.generators[0]
                        if gen.is_async:
                            raise JSCompilationError(
                                "Async generators are not supported"
                            )
                        iter_expr = self.emit_expr(gen.iter)
                        chain, param, name_list = self._build_comp_chain(gen, gen.ifs)
                        old_locals = set(self.locals)
                        for n in name_list:
                            self.locals.add(n)
                        elt_expr = self.emit_expr(gen_arg.elt)
                        self.locals = old_locals
                        method = "some" if fname == "any" else "every"
                        arrow = JSArrowFunction(param, JSParen(elt_expr))
                        if chain.emit() == iter_expr.emit():
                            return JSMemberCall(iter_expr, method, [arrow])
                        return JSMemberCall(chain, method, [arrow])
                    # Fallback: treat as array-like boolean test
                    if fname == "any":
                        return JSMemberCall(args[0], "some", [JSArrowFunction("v", JSIdentifier("v"))])
                    else:
                        return JSMemberCall(args[0], "every", [JSArrowFunction("v", JSIdentifier("v"))])
                if fname == "sum" and 1 <= len(args) <= 2:
                    start = args[1] if len(args) == 2 else JSNumber("0")
                    base = args[0]
                    if isinstance(base, JSMemberCall) and base.method == "map":
                        base = JSMemberCall(base.obj, base.method, base.args, wrap=False)
                    reducer = JSArrowFunction("(a, b)", JSBinary(JSIdentifier("a"), "+", JSIdentifier("b")))
                    wrap_chain = isinstance(base, JSMemberCall)
                    reduce_call = JSMemberCall(base, "reduce", [reducer, start], wrap=not wrap_chain)
                    if wrap_chain:
                        return JSParen(JSMemberCall(base, "reduce", [reducer, start], wrap=False))
                    return reduce_call
                raise JSCompilationError(f"Call to unsupported function: {fname}()")
            if isinstance(node.func, ast.Attribute):
                obj = self.emit_expr(node.func.value)
                attr = node.func.attr
                args = [self.emit_expr(a) for a in node.args]
                # Allow common string methods
                if attr == "join" and len(args) == 1:
                    # "sep".join(xs) -> xs.join("sep")
                    return JSMemberCall(args[0], "join", [obj])
                # Dict-like helpers: get/keys/values/items
                if attr == "get" and 1 <= len(node.args) <= 2:
                    # obj.get(k, default) -> (obj[k] ?? default)
                    key_node = node.args[0]
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        key_str = key_node.value.replace("\\", "\\\\").replace('"', '\\"')
                        key_expr: JSExpr = JSIdentifier(f'"{key_str}"')
                    else:
                        key_expr = self.emit_expr(key_node)
                    # Special-case to avoid extra parens around subscript in nullish
                    lhs = JSSubscript(obj, key_expr, wrap=False)
                    if len(node.args) == 2:
                        default = self.emit_expr(node.args[1])
                        return JSNullishCoalesce(lhs, default)
                    else:
                        return JSNullishCoalesce(lhs, JSNull())
                if attr == "keys" and len(args) == 0:
                    return JSCall(JSIdentifier("Object.keys"), [obj])
                if attr == "values" and len(args) == 0:
                    return JSCall(JSIdentifier("Object.values"), [obj])
                if attr == "items" and len(args) == 0:
                    return JSCall(JSIdentifier("Object.entries"), [obj])
                if attr in {"lower", "upper", "strip"} and len(args) == 0:
                    mapping = {
                        "lower": "toLowerCase",
                        "upper": "toUpperCase",
                        "strip": "trim",
                    }
                    return JSMemberCall(obj, mapping[attr], [])
                if attr == "capitalize" and len(args) == 0:
                    left = JSParen(
                        JSMemberCall(
                            JSMemberCall(obj, "charAt", [JSNumber("0")], wrap=False),
                            "toUpperCase",
                            [],
                            wrap=False,
                        )
                    )
                    right = JSParen(
                        JSMemberCall(
                            JSMemberCall(obj, "slice", [JSNumber("1")], wrap=False),
                            "toLowerCase",
                            [],
                            wrap=False,
                        )
                    )
                    return JSBinary(left, "+", right)
                if attr == "zfill" and len(args) == 1:
                    return JSMemberCall(obj, "padStart", [args[0], JSString("0")])
                if attr in {"startswith", "endswith"} and len(args) == 1:
                    mapping = {
                        "startswith": "startsWith",
                        "endswith": "endsWith",
                    }
                    return JSMemberCall(obj, mapping[attr], [args[0]])
                if attr == "lstrip" and len(args) == 0:
                    return JSMemberCall(obj, "trimStart", [])
                if attr == "rstrip" and len(args) == 0:
                    return JSMemberCall(obj, "trimEnd", [])
                if attr == "replace" and len(args) == 2:
                    return JSMemberCall(obj, "replaceAll", [args[0], args[1]])
                return JSMemberCall(obj, attr, args)
        if isinstance(node, ast.Attribute):
            value = self.emit_expr(node.value)
            return JSMember(value, node.attr)
        if isinstance(node, ast.Subscript):
            value = self.emit_expr(node.value)
            # Slice handling
            if isinstance(node.slice, ast.Slice):
                if node.slice.step is not None:
                    raise JSCompilationError("Unsupported slice step in slicing")
                lower = node.slice.lower
                upper = node.slice.upper
                if lower is None and upper is None:
                    # full slice -> copy
                    return JSMemberCall(value, "slice", [])
                if lower is None:
                    start = JSNumber("0")
                    end = self._emit_slice_index_arg(node.slice.upper)
                    return JSMemberCall(value, "slice", [start, end])
                if upper is None:
                    start = self._emit_slice_index_arg(node.slice.lower)
                    return JSMemberCall(value, "slice", [start])
                start = self._emit_slice_index_arg(node.slice.lower)
                end = self._emit_slice_index_arg(node.slice.upper)
                return JSMemberCall(value, "slice", [start, end])
            # Negative index single access -> at()
            if (
                isinstance(node.slice, ast.UnaryOp)
                and isinstance(node.slice.op, ast.USub)
                and isinstance(node.slice.operand, ast.Constant)
                and isinstance(node.slice.operand.value, int)
            ):
                idx = JSNumber(f"-{node.slice.operand.value}")
                return JSMemberCall(value, "at", [idx])
            index = self.emit_expr(node.slice)
            return JSSubscript(value, index)
        if isinstance(node, ast.JoinedStr):
            # Special-case a single formatted value like f"{x:...}" -> apply format spec
            if len(node.values) == 1 and isinstance(node.values[0], ast.FormattedValue):
                fv = node.values[0]
                if fv.format_spec is not None:
                    spec_str = self._const_joinedstr_to_str(fv.format_spec)
                    if spec_str is None:
                        raise JSCompilationError(
                            "Format spec must be a constant string"
                        )
                    inner = self.emit_expr(fv.value)
                    return self._apply_format_spec(inner, fv.value, spec_str)

            # General f-strings -> backtick template
            parts: list[Union[str, JSExpr]] = []
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    s = part.value.replace("\\", "\\\\").replace("`", "\\`")
                    parts.append(s)
                elif isinstance(part, ast.FormattedValue):
                    expr_inner = self.emit_expr(part.value)
                    # Apply full format spec if provided
                    if part.format_spec is not None:
                        spec_str = self._const_joinedstr_to_str(part.format_spec)
                        if spec_str is None:
                            raise JSCompilationError(
                                "Format spec must be a constant string"
                            )
                        expr_inner = self._apply_format_spec(
                            expr_inner, part.value, spec_str
                        )
                    parts.append(expr_inner)
                else:
                    raise JSCompilationError("Unsupported f-string component")
            return JSTemplate(parts)
        raise JSCompilationError(
            f"Unsupported expression: {ast.dump(node, include_attributes=False)}"
        )


###############################################################################
# JS codegen wrapper
###############################################################################


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
    js_fn = visitor.emit_function(fndef.body)
    code = js_fn.emit()
    n_args = len(arg_names)
    h = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
    return code, n_args, h


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
