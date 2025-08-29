"""
Minimal AST-to-JS transpiler for a restricted, pure subset of Python used to
define synchronous JavaScript callbacks in the Pulse UI runtime.

The goal is to translate small Python functions into compact
JavaScript functions that can be inlined on the client where a sync
callback is required (e.g., chart formatters, sorters, small mappers).

The subset of the language supported is intended to be:
- Primitives (int, float, str, bool, datetime, None) and their methods
- Lists, tuples, sets, dicts, their constructor, their expressions, and their methods
- Core statements: return, if, elif, else, for, while, break, continue,
- Unary and binary operations, assignments, `in` operator
- Collections unpacking and comprehensions
- F-strings and the formatting mini-language
- Print (converted to console.log)
- Arbitrary JS objects with property access, method calling, and unpacking
- Lambdas (necessary for certain operations like filter, map, etc...)
- Built-in functions like `min`, `max`, `any`, `filter`, `sorted`
- Math module (later)
- Helpers, like deep equality (later)

The `@javascript` decorator compiles a function at definition-time and stores
metadata on the Python callable so the reconciler can send the compiled code to
the client.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Optional,
    Sequence,
    TypedDict,
    Union,
    cast,
)


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

ALLOWED_UNOPS: dict[type[ast.unaryop], str] = {
    ast.UAdd: "+",
    ast.USub: "-",
    ast.Not: "!",
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
    value: Any

    def emit(self) -> str:
        s = self.value
        # Escape for double-quoted JS string literals
        s = (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            .replace("\b", "\\b")
            .replace("\f", "\\f")
            .replace("\v", "\\v")
            .replace("\x00", "\\x00")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )
        return f'"{s}"'


@dataclass
class JSNumber(JSExpr):
    value: float

    def emit(self) -> str:
        return str(self.value)


@dataclass
class JSBoolean(JSExpr):
    value: bool

    def emit(self) -> str:
        return "true" if self.value else "false"


@dataclass
class JSNull(JSExpr):
    def emit(self) -> str:
        return "null"


@dataclass
class JSUndefined(JSExpr):
    def emit(self) -> str:
        return "undefined"


@dataclass
class JSArray(JSExpr):
    elements: Sequence[JSExpr]

    def emit(self) -> str:
        inner = ", ".join(e.emit() for e in self.elements)
        return f"[{inner}]"


@dataclass
class JSSpread(JSExpr):
    expr: JSExpr

    def emit(self) -> str:
        return f"...{self.expr.emit()}"


@dataclass
class JSProp(JSExpr):
    key: JSString
    value: JSExpr

    def emit(self) -> str:
        return f"{self.key.emit()}: {self.value.emit()}"


@dataclass
class JSComputedProp(JSExpr):
    key: JSExpr
    value: JSExpr

    def emit(self) -> str:
        return f"[{self.key.emit()}]: {self.value.emit()}"


@dataclass
class JSObject(JSExpr):
    props: Sequence[JSProp | JSComputedProp | JSSpread]

    def emit(self) -> str:
        inner = ", ".join(p.emit() for p in self.props)
        return "{" + inner + "}"


@dataclass
class JSUnary(JSExpr):
    op: str  # '-', '+', '!'
    operand: JSExpr

    def emit(self) -> str:
        operand_code = _emit_child_for_binary_like(
            self.operand, parent_op=self.op, side="unary"
        )
        return f"{self.op}{operand_code}"


@dataclass
class JSBinary(JSExpr):
    left: JSExpr
    op: str
    right: JSExpr

    def emit(self) -> str:
        # Left child
        force_left_paren = False
        # Special JS grammar rule: left operand of ** cannot be a unary +/- without parentheses
        if (
            self.op == "**"
            and isinstance(self.left, JSUnary)
            and self.left.op in {"-", "+"}
        ):
            force_left_paren = True
        left_code = _emit_child_for_binary_like(
            self.left,
            parent_op=self.op,
            side="left",
            force_paren=force_left_paren,
        )
        # Right child
        right_code = _emit_child_for_binary_like(
            self.right, parent_op=self.op, side="right"
        )
        return f"{left_code} {self.op} {right_code}"


@dataclass
class JSLogicalChain(JSExpr):
    op: str  # '&&' or '||'
    values: Sequence[JSExpr]

    # TODO: parenthesizing
    def emit(self) -> str:
        if len(self.values) == 1:
            return self.values[0].emit()
        parts: list[str] = []
        for v in self.values:
            # No strict left/right in chains, but treat as middle
            code = _emit_child_for_binary_like(v, parent_op=self.op, side="chain")
            parts.append(code)
        return f" {self.op} ".join(parts)


@dataclass
class JSTertiary(JSExpr):
    test: JSExpr
    if_true: JSExpr
    if_false: JSExpr

    def emit(self) -> str:
        return f"{self.test.emit()} ? {self.if_true.emit()} : {self.if_false.emit()}"


@dataclass
class JSFunctionExpr(JSExpr):
    params: Sequence[str]
    body: Sequence[JSStmt]

    def emit(self) -> str:
        params = ", ".join(self.params)
        body_code = "\n".join(s.emit() for s in self.body)
        return f"function({params}){{\n{body_code}\n}}"


@dataclass
class JSTemplate(JSExpr):
    # parts are either raw strings (literal text) or JSExpr instances which are
    # emitted inside ${...}
    parts: Sequence[Union[str, JSExpr]]

    def emit(self) -> str:
        out: list[str] = ["`"]
        for p in self.parts:
            if isinstance(p, str):
                out.append(
                    p.replace("\\", "\\\\")
                    .replace("`", "\\`")
                    .replace("${", "\\${")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t")
                    .replace("\b", "\\b")
                    .replace("\f", "\\f")
                    .replace("\v", "\\v")
                    .replace("\x00", "\\x00")
                    .replace("\u2028", "\\u2028")
                    .replace("\u2029", "\\u2029")
                )
            else:
                out.append("${" + p.emit() + "}")
        out.append("`")
        return "".join(out)


@dataclass
class JSMember(JSExpr):
    obj: JSExpr
    prop: str

    def emit(self) -> str:
        obj_code = _emit_child_for_primary(self.obj)
        return f"{obj_code}.{self.prop}"


@dataclass
class JSSubscript(JSExpr):
    obj: JSExpr
    index: JSExpr

    def emit(self) -> str:
        obj_code = _emit_child_for_primary(self.obj)
        return f"{obj_code}[{self.index.emit()}]"


@dataclass
class JSCall(JSExpr):
    callee: JSExpr  # typically JSIdentifier
    args: Sequence[JSExpr]

    def emit(self) -> str:
        fn = _emit_child_for_primary(self.callee)
        return f"{fn}({', '.join(a.emit() for a in self.args)})"


@dataclass
class JSMemberCall(JSExpr):
    obj: JSExpr
    method: str
    args: Sequence[JSExpr]

    def emit(self) -> str:
        obj_code = _emit_child_for_primary(self.obj)
        return f"{obj_code}.{self.method}({', '.join(a.emit() for a in self.args)})"


@dataclass
class JSNew(JSExpr):
    ctor: JSExpr
    args: Sequence[JSExpr]

    def emit(self) -> str:
        ctor_code = _emit_child_for_primary(self.ctor)
        return f"new {ctor_code}({', '.join(a.emit() for a in self.args)})"


@dataclass
class JSArrowFunction(JSExpr):
    params_code: str  # already formatted e.g. 'x' or '(a, b)' or '([k, v])'
    body: JSExpr

    def emit(self) -> str:
        return f"{self.params_code} => {self.body.emit()}"


@dataclass
class JSReturn(JSStmt):
    value: JSExpr

    def emit(self) -> str:
        return f"return {self.value.emit()};"


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
class JSRaw(JSExpr):
    content: str

    def emit(self) -> str:
        return self.content


# -----------------------------
# Precedence helpers
# -----------------------------

_PRIMARY_PRECEDENCE = 20


def _precedence_of_op(op: str) -> int:
    # Higher number = binds tighter
    if op in {".", "[]", "()"}:  # pseudo ops for primary contexts
        return _PRIMARY_PRECEDENCE
    if op in {"!", "+u", "-u"}:  # unary; we encode + and - as unary with +u/-u
        return 17
    if op == "**":
        return 16
    if op in {"*", "/", "%"}:
        return 15
    if op in {"+", "-"}:
        return 14
    if op in {"<", "<=", ">", ">=", "===", "!=="}:
        return 12
    if op == "&&":
        return 7
    if op == "||":
        return 6
    if op == "??":
        return 6
    if op == "?:":  # ternary
        return 4
    return 0


def _is_right_associative(op: str) -> bool:
    return op == "**"


def _precedence_of_expr(e: JSExpr) -> int:
    if isinstance(e, JSBinary):
        return _precedence_of_op(e.op)
    if isinstance(e, JSUnary):
        # Distinguish unary + and - from binary precedence table by tag
        tag = "+u" if e.op == "+" else ("-u" if e.op == "-" else e.op)
        return _precedence_of_op(tag)
    if isinstance(e, JSTertiary):
        return _precedence_of_op("?:")
    if isinstance(e, JSLogicalChain):
        return _precedence_of_op(e.op)
    # Nullish now represented as JSBinary with op "??"; precedence resolved below
    if isinstance(e, (JSMember, JSSubscript, JSCall, JSMemberCall, JSNew)):
        return _precedence_of_op(".")
    # Treat primitives and containers as primary
    if isinstance(
        e,
        (
            JSIdentifier,
            JSString,
            JSNumber,
            JSBoolean,
            JSNull,
            JSUndefined,
            JSArray,
            JSObject,
            JSTemplate,
            JSRaw,
        ),
    ):
        return _PRIMARY_PRECEDENCE
    return 0


def _mixes_nullish_and_logical(parent_op: str, child: JSExpr) -> bool:
    if parent_op in {"&&", "||"} and isinstance(child, JSBinary) and child.op == "??":
        return True
    if parent_op == "??" and isinstance(child, JSLogicalChain):
        return True
    return False


def _emit_child_for_binary_like(
    child: JSExpr, parent_op: str, side: str, force_paren: bool = False
) -> str:
    # side is one of: 'left', 'right', 'unary', 'chain'
    code = child.emit()
    if force_paren:
        return f"({code})"
    # Ternary as child should always be wrapped under binary-like contexts
    if isinstance(child, JSTertiary):
        return f"({code})"
    # Explicit parens when mixing ?? with &&/||
    if _mixes_nullish_and_logical(parent_op, child):
        return f"({code})"
    child_prec = _precedence_of_expr(child)
    parent_prec = _precedence_of_op(parent_op)
    if child_prec < parent_prec:
        return f"({code})"
    if child_prec == parent_prec:
        # Handle associativity for exact same precedence buckets
        if isinstance(child, JSBinary):
            if _is_right_associative(parent_op):
                # Need parens on left child for same prec to preserve grouping
                if side == "left":
                    return f"({code})"
            else:
                # Left-associative: protect right child when equal precedence
                if side == "right":
                    return f"({code})"
        if isinstance(child, JSLogicalChain):
            # Same op chains don't need parens; different logical ops rely on precedence
            if child.op != parent_op:
                # '&&' has higher precedence than '||'; no parens needed for tighter child
                # But if equal (shouldn't happen here), remain as-is
                pass
        # For other equal-precedence non-binary nodes, keep as-is
    return code


def _emit_child_for_primary(expr: JSExpr) -> str:
    code = expr.emit()
    if _precedence_of_expr(expr) < _PRIMARY_PRECEDENCE or isinstance(expr, JSTertiary):
        return f"({code})"
    return code


@dataclass
class JSAugAssign(JSStmt):
    name: str
    op: str
    value: JSExpr

    def emit(self) -> str:
        return f"{self.name} {self.op}= {self.value.emit()};"


@dataclass
class JSConstAssign(JSStmt):
    name: str
    value: JSExpr

    def emit(self) -> str:
        return f"const {self.name} = {self.value.emit()};"


@dataclass
class JsSingleStmt(JSStmt):
    expr: JSExpr

    def emit(self) -> str:
        return f"{self.expr.emit()};"


@dataclass
class JSMultiStmt(JSStmt):
    stmts: Sequence[JSStmt]

    def emit(self) -> str:
        return "\n".join(s.emit() for s in self.stmts)


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
class JSForOf(JSStmt):
    target: str | list[str]
    iter_expr: JSExpr
    body: Sequence[JSStmt]

    def emit(self) -> str:
        body_code = "\n".join(s.emit() for s in self.body)
        target = self.target
        if not isinstance(target, str):
            target = f"[{', '.join(x for x in target)}]"
        return f"for (const {target} of {self.iter_expr.emit()}){{\n{body_code}\n}}"


@dataclass
class JSWhile(JSStmt):
    test: JSExpr
    body: Sequence[JSStmt]

    def emit(self) -> str:
        body_code = "\n".join(s.emit() for s in self.body)
        return f"while ({self.test.emit()}){{\n{body_code}\n}}"


class JSBreak(JSStmt):
    def emit(self) -> str:
        return "break;"


class JSContinue(JSStmt):
    def emit(self) -> str:
        return "continue;"


class FormatSpecInfo(TypedDict):
    fill: Optional[str]
    align: Optional[str]
    sign: Optional[str]
    alt: bool
    zero: bool
    width: Optional[int]
    grouping: Optional[str]
    precision: Optional[int]
    type: Optional[str]


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
        self._temp_counter: int = 0

    def _arrow_param_from_target(self, target: ast.expr) -> tuple[str, list[str]]:
        if isinstance(target, ast.Name):
            return target.id, [target.id]
        if isinstance(target, ast.Tuple) and all(
            isinstance(e, ast.Name) for e in target.elts
        ):
            names = [cast(ast.Name, e).id for e in target.elts]
            return f"([{', '.join(names)}])", names
        raise JSCompilationError(
            "Only name or 2-tuple targets supported in comprehensions"
        )

    def _build_comprehension_chain(
        self, generators: list[ast.comprehension], build_last: Callable[[], JSExpr]
    ) -> JSExpr:
        """Build a left-to-right flatMap/map chain for Python comprehensions.

        The provided build_last callback is invoked when the recursion reaches
        the innermost generator, and must return the mapped element expression
        (e.g., the `elt` for list/set comps or the `[key, value]` pair for
        dict comps). This helper snapshots and restores local scope so that
        comprehension-target variables do not leak to the outer scope.
        """
        if len(generators) == 0:
            raise JSCompilationError("Empty comprehension")

        saved_locals = set(self.locals)

        def build_chain(gen_index: int) -> JSExpr:
            gen = generators[gen_index]
            if gen.is_async:
                raise JSCompilationError("Async comprehensions are not supported")
            iter_expr = self.emit_expr(gen.iter)
            param_code, names = self._arrow_param_from_target(gen.target)
            for nm in names:
                self.locals.add(nm)
            base: JSExpr = iter_expr
            if gen.ifs:
                conds = [self.emit_expr(test) for test in gen.ifs]
                cond = JSLogicalChain("&&", conds) if len(conds) > 1 else conds[0]
                base = JSMemberCall(base, "filter", [JSArrowFunction(param_code, cond)])
            is_last = gen_index == len(generators) - 1
            if is_last:
                elt_expr = build_last()
                return JSMemberCall(
                    base, "map", [JSArrowFunction(param_code, elt_expr)]
                )
            inner = build_chain(gen_index + 1)
            return JSMemberCall(base, "flatMap", [JSArrowFunction(param_code, inner)])

        try:
            return build_chain(0)
        finally:
            self.locals = saved_locals

    # --- Entrypoints ---------------------------------------------------------
    def emit_function(self, body: list[ast.stmt]) -> JSFunctionExpr:
        stmts: list[JSStmt] = []
        # Reset temp counter per function emission
        self._temp_counter = 0
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
        """Supported statements:
        - return
        - break
        - continue
        - assign (regular and augmented)
        - if, elif, else
        - for (iterables only)
        - while
        - regular expr
        """
        if isinstance(node, ast.Return):
            return JSReturn(self.emit_expr(node.value))
        if isinstance(node, ast.Break):
            return JSBreak()
        if isinstance(node, ast.Continue):
            return JSContinue()
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
            if len(node.targets) != 1:
                raise JSCompilationError(
                    "Multiple assignment targets are not supported"
                )
            target_node = node.targets[0]
            # Tuple/list unpacking of flat names only
            if isinstance(target_node, (ast.Tuple, ast.List)):
                elements = target_node.elts
                if not elements or not all(isinstance(e, ast.Name) for e in elements):
                    raise JSCompilationError(
                        "Unpacking is supported only for simple variables. Example: `a, b, c = [x for x in range(3)]`."
                    )
                tmp_name = f"__tmp{self._temp_counter}"
                self._temp_counter += 1
                value_expr = self.emit_expr(node.value)
                stmts: list[JSStmt] = [
                    JSConstAssign(tmp_name, value_expr),
                ]
                for idx, e in enumerate(elements):
                    name = cast(ast.Name, e).id
                    ident = _mangle_identifier(name)
                    index_expr = JSNumber(idx)
                    sub = JSSubscript(JSIdentifier(tmp_name), index_expr)
                    if name in self.locals:
                        stmts.append(JSAssign(ident, sub, declare=False))
                    else:
                        self.locals.add(name)
                        stmts.append(JSAssign(ident, sub, declare=True))
                return JSMultiStmt(stmts)
            if not isinstance(target_node, ast.Name):
                raise JSCompilationError(
                    "Only simple assignments to local names are supported."
                )
            target = target_node.id
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
            orelse = [self.emit_stmt(s) for s in node.orelse]
            return JSIf(test, body, orelse)
        if isinstance(node, ast.Expr):
            return JsSingleStmt(self.emit_expr(node.value))
        if isinstance(node, ast.While):
            test = self.emit_expr(node.test)
            body = [self.emit_stmt(s) for s in node.body]
            # orelse on Python while isn't supported; ignore if present (empty expected)
            return JSWhile(test, body)
        if isinstance(node, ast.For):
            # Only "for name in <iter>" supported
            if not isinstance(node.target, ast.Name):
                raise JSCompilationError(
                    "Only simple name targets supported in for-loops"
                )
            target_ident = _mangle_identifier(node.target.id)
            # Loop variable is a new local; declare inside loop via const in JSForOf
            # (No redeclaration tracking needed as 'const' is per-iteration variable)
            # Track as local so references in the body are not considered freevars.
            self.locals.add(node.target.id)
            iter_expr = self.emit_expr(node.iter)
            body = [self.emit_stmt(s) for s in node.body]
            return JSForOf(target_ident, iter_expr, body)
        raise JSCompilationError(
            f"Unsupported statement: {ast.dump(node, include_attributes=False)}"
        )

    # --- Expressions ---------------------------------------------------------
    def emit_expr(self, node: ast.expr | None) -> JSExpr:
        """Supported expressions:
        - None
        - Constants
        - Tuples
        - Lists
        - Dicts
        - Generators
        - Binary operation
        - Unary operation
        - Boolean operation
        - Compare (Q: diff w/ BoolOp?)
        - If expression
        - Function call (covers both method and function calls)
        - Attribute access
        - Indexing (called "subscript")
        - f-string (called "JoinedStr")

        TODO:
        - List/set/dict comprehensions
        - Generator expressions (they get converted to arrays)
        - Set expressions
        """
        if node is None:
            return JSUndefined()

        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, str):
                return JSString(v)
            if v is None:
                return JSUndefined()
            if v is True:
                return JSBoolean(True)
            if v is False:
                return JSBoolean(False)
            return JSNumber(v)
        if isinstance(node, ast.Name):
            ident = node.id
            if ident not in self.locals:
                # Track potential freevar usage
                self.freevars.add(ident)
            return JSIdentifier(_mangle_identifier(ident))
        if isinstance(node, (ast.List, ast.Tuple)):
            list_parts: list[JSExpr] = []
            for e in node.elts:
                if isinstance(e, ast.Starred):
                    list_parts.append(JSSpread(self.emit_expr(e.value)))
                else:
                    list_parts.append(self.emit_expr(e))
            return JSArray(list_parts)
        if isinstance(node, ast.Dict):
            parts: list[JSProp | JSComputedProp | JSSpread] = []
            for k, v in zip(node.keys, node.values):
                if k is None:
                    # Spread {**expr}
                    parts.append(JSSpread(self.emit_expr(v)))
                    continue
                val_expr = self.emit_expr(v)
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    parts.append(JSProp(JSString(k.value), val_expr))
                else:
                    # Computed key -> [String(key)]
                    comp_key = JSCall(JSIdentifier("String"), [self.emit_expr(k)])
                    parts.append(JSComputedProp(comp_key, val_expr))
            return JSObject(parts)
        if isinstance(node, ast.ListComp):
            return self._build_comprehension_chain(
                node.generators, lambda: self.emit_expr(node.elt)
            )
        if isinstance(node, ast.GeneratorExp):
            return self._build_comprehension_chain(
                node.generators, lambda: self.emit_expr(node.elt)
            )
        if isinstance(node, ast.SetComp):
            arr = self._build_comprehension_chain(
                node.generators, lambda: self.emit_expr(node.elt)
            )
            return JSNew(JSIdentifier("Set"), [arr])
        if isinstance(node, ast.DictComp):
            # {k: v for ...} -> Object.fromEntries(chain.map(x => [k, v]))
            pairs = self._build_comprehension_chain(
                node.generators,
                lambda: JSArray(
                    [
                        JSCall(JSIdentifier("String"), [self.emit_expr(node.key)]),
                        self.emit_expr(node.value),
                    ]
                ),
            )
            return JSCall(JSIdentifier("Object.fromEntries"), [pairs])
        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op not in ALLOWED_BINOPS:
                raise JSCompilationError(f"Operator not allowed: {op.__name__}")
            left = self.emit_expr(node.left)
            right = self.emit_expr(node.right)
            return JSBinary(left, ALLOWED_BINOPS[op], right)
        if isinstance(node, ast.UnaryOp):
            op = type(node.op)
            if op not in ALLOWED_UNOPS:
                raise JSCompilationError("Unsupported unary op")
            return JSUnary(ALLOWED_UNOPS[op], self.emit_expr(node.operand))
        if isinstance(node, ast.BoolOp):
            op = "&&" if isinstance(node.op, ast.And) else "||"
            return JSLogicalChain(op, [self.emit_expr(v) for v in node.values])
        if isinstance(node, ast.Compare):
            # Support chained comparisons, identity with None, and membership
            # Build sequential comparisons combined with &&
            operands: list[ast.expr] = [node.left, *node.comparators]
            exprs: list[JSExpr] = [self.emit_expr(e) for e in operands]
            cmp_parts: list[JSExpr] = []
            for i, op in enumerate(node.ops):
                left_node = operands[i]
                right_node = operands[i + 1]
                left_expr = exprs[i]
                right_expr = exprs[i + 1]
                cmp_parts.append(
                    _build_comparison(left_expr, left_node, op, right_expr, right_node)
                )
            return JSLogicalChain("&&", cmp_parts)
        if isinstance(node, ast.IfExp):
            test = self.emit_expr(node.test)
            body = self.emit_expr(node.body)
            orelse = self.emit_expr(node.orelse)
            return JSTertiary(test, body, orelse)
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
                if fname == "print":
                    return JSMemberCall(JSIdentifier("console"), "log", args)
                if fname == "len" and len(args) == 1:
                    # (x?.length ?? Object.keys(x).length)
                    x = args[0]
                    return JSBinary(
                        JSMember(x, "length"),
                        "??",
                        JSMember(JSCall(JSIdentifier("Object.keys"), [x]), "length"),
                    )
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
                        return JSMemberCall(
                            JSCall(JSIdentifier("Number"), [num]),
                            "toFixed",
                            [nd],
                        )
                    # -> Positional args
                    # round(x) -> Math.round(x); round(x, n) -> Number(x).toFixed(n)
                    if len(args) == 1:
                        return JSCall(JSIdentifier("Math.round"), [args[0]])
                    elif len(args) == 2:
                        return JSMemberCall(
                            JSCall(JSIdentifier("Number"), [args[0]]),
                            "toFixed",
                            [args[1]],
                        )
                    else:
                        raise JSCompilationError(
                            f"round() expects one or two arguments, received {len(args)}"
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
                    return args[0]
                if fname in {"any", "all"} and len(node.args) == 1:
                    # Special-case single-generator predicate form: any(x > 0 for x in xs) -> xs.some(x => x > 0)
                    gen_arg = node.args[0]
                    if (
                        isinstance(gen_arg, ast.GeneratorExp)
                        and len(gen_arg.generators) == 1
                        and not gen_arg.generators[0].ifs
                    ):
                        # Only one generator; no if-guards; elt is predicate using the target
                        g = gen_arg.generators[0]
                        if g.is_async:
                            raise JSCompilationError(
                                "Async comprehensions are not supported"
                            )
                        iter_expr = self.emit_expr(g.iter)
                        param_code, names = self._arrow_param_from_target(g.target)
                        for nm in names:
                            self.locals.add(nm)
                        pred = self.emit_expr(gen_arg.elt)
                        method = "some" if fname == "any" else "every"
                        return JSMemberCall(
                            iter_expr, method, [JSArrowFunction(param_code, pred)]
                        )
                    # Fallback: treat input as array-like of booleans
                    method = "some" if fname == "any" else "every"
                    return JSMemberCall(
                        args[0], method, [JSArrowFunction("v", JSIdentifier("v"))]
                    )
                if fname == "sum" and 1 <= len(args) <= 2:
                    start = args[1] if len(args) == 2 else JSNumber(0)
                    base = args[0]
                    if isinstance(base, JSMemberCall) and base.method == "map":
                        base = JSMemberCall(base.obj, base.method, base.args)
                    reducer = JSArrowFunction(
                        "(a, b)", JSBinary(JSIdentifier("a"), "+", JSIdentifier("b"))
                    )
                    return JSMemberCall(base, "reduce", [reducer, start])
                raise JSCompilationError(f"Call to unsupported function: {fname}()")
            if isinstance(node.func, ast.Attribute):
                obj = self.emit_expr(node.func.value)
                attr = node.func.attr
                args = [self.emit_expr(a) for a in node.args]
                # Centralized builtin-dispatch for ambiguous methods
                if attr == "pop":
                    # No-arg -> list-style pop; leave as direct call (not ambiguous in Python subset)
                    if len(node.args) == 0:
                        return JSMemberCall(obj, "pop", [])
                    # Two args -> dict-style pop(key, default)
                    if len(node.args) == 2:
                        key_expr = args[0]
                        default_expr = args[1]
                        code = f"(() => {{const __k={key_expr.emit()}; if (Object.hasOwn({obj.emit()}, __k)) {{ const __v = {obj.emit()}[__k]; delete {obj.emit()}[__k]; return __v; }} return {default_expr.emit()}; }})()"
                        return JSRaw(code)
                    # One arg -> may be list index OR dict key; use runtime branch
                    if len(node.args) == 1:
                        key_node = node.args[0]
                        key_expr = args[0]
                        # If it's a clear string literal, keep dict semantics for stability
                        if isinstance(key_node, ast.Constant) and isinstance(
                            key_node.value, str
                        ):
                            code = f"(() => {{const __k={key_expr.emit()}; if (Object.hasOwn({obj.emit()}, __k)) {{ const __v = {obj.emit()}[__k]; delete {obj.emit()}[__k]; return __v; }} }})()"
                            return JSRaw(code)
                        # Otherwise choose at runtime
                        code = (
                            f"(() => {{const __k={key_expr.emit()}; if (Array.isArray({obj.emit()})) {{ return {obj.emit()}.splice(__k, 1)[0]; }} "
                            f'if ({obj.emit()} && typeof {obj.emit()} === "object") {{ if (Object.hasOwn({obj.emit()}, __k)) {{ const __v = {obj.emit()}[__k]; delete {obj.emit()}[__k]; return __v; }} }} '
                            f"return {obj.emit()}.pop(__k); }})()"
                        )
                        return JSRaw(code)
                # Allow common string methods
                if attr == "join" and len(args) == 1:
                    # "sep".join(xs) -> xs.join("sep")
                    return JSMemberCall(args[0], "join", [obj])
                # Dict-like helpers: get/keys/values/items
                if attr == "get" and 1 <= len(node.args) <= 2:
                    # obj.get(k, default) -> (obj[k] ?? default)
                    key_node = node.args[0]
                    if isinstance(key_node, ast.Constant) and isinstance(
                        key_node.value, str
                    ):
                        key_expr = JSString(key_node.value)
                    else:
                        key_expr = self.emit_expr(key_node)
                    lhs = JSSubscript(obj, key_expr)
                    if len(node.args) == 2:
                        default = self.emit_expr(node.args[1])
                        return JSBinary(lhs, "??", default)
                    else:
                        return JSBinary(lhs, "??", JSUndefined())
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
                    left = JSMemberCall(
                        JSMemberCall(obj, "charAt", [JSNumber(0)]),
                        "toUpperCase",
                        [],
                    )
                    right = JSMemberCall(
                        JSMemberCall(obj, "slice", [JSNumber(1)]),
                        "toLowerCase",
                        [],
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
                # List/array-like helpers
                if attr == "index" and len(args) == 1:
                    return JSMemberCall(obj, "indexOf", [args[0]])
                if attr == "count" and len(args) == 1:
                    filtered = JSMemberCall(
                        obj,
                        "filter",
                        [
                            JSArrowFunction(
                                "v", JSBinary(JSIdentifier("v"), "===", args[0])
                            )
                        ],
                    )
                    return JSMember(filtered, "length")
                if attr == "copy" and len(args) == 0:
                    # Prefer array slice when array; otherwise shallow object copy via spread
                    return JSTertiary(
                        JSCall(JSIdentifier("Array.isArray"), [obj]),
                        JSMemberCall(obj, "slice", []),
                        JSObject([JSSpread(obj)]),
                    )
                # Dict-like mutators
                if attr == "popitem" and len(args) == 0:
                    code = f"(() => {{const __ks = Object.keys({obj.emit()}); if (__ks.length === 0) {{ return; }} const __k = __ks[__ks.length-1]; const __v = {obj.emit()}[__k]; delete {obj.emit()}[__k]; return [__k, __v]; }})()"
                    return JSIdentifier(code)
                if attr == "setdefault" and (len(args) == 1 or len(args) == 2):
                    key_expr = args[0]
                    default_expr = args[1] if len(args) == 2 else JSUndefined()
                    code = f"(() => {{const __k={key_expr.emit()}; if (!Object.hasOwn({obj.emit()}, __k)) {{ {obj.emit()}[__k] = {default_expr.emit()}; return {default_expr.emit()}; }} return {obj.emit()}[__k]; }})()"
                    return JSIdentifier(code)
                if attr == "update" and len(args) == 1:
                    return JSIdentifier(
                        f"(() => {{Object.assign({obj.emit()}, {args[0].emit()}); }})()"
                    )
                if attr == "clear" and len(args) == 0:
                    # Runtime branch: arrays vs objects vs fallback method
                    code = (
                        f"(() => {{if (Array.isArray({obj.emit()})) {{ {obj.emit()}.length = 0; return; }} "
                        f'if ({obj.emit()} && typeof {obj.emit()} === "object") {{ for (const __k in {obj.emit()}){{ if (Object.hasOwn({obj.emit()}, __k)) delete {obj.emit()}[__k]; }} return; }} '
                        f"return {obj.emit()}.clear(); }})()"
                    )
                    return JSIdentifier(code)
                # Mutating list methods (allowed):
                if attr == "append" and len(args) == 1:
                    code = (
                        f"(() => {{if (Array.isArray({obj.emit()})) {{ {obj.emit()}.push({args[0].emit()}); return; }} "
                        f'if ({obj.emit()} && typeof {obj.emit()}.append === "function") {{ return {obj.emit()}.append({args[0].emit()}); }} '
                        f"return; }})()"
                    )
                    return JSIdentifier(code)
                if attr == "extend" and len(args) == 1:
                    code = (
                        f"(() => {{if (Array.isArray({obj.emit()})) {{ {obj.emit()}.push(...{args[0].emit()}); return; }} "
                        f'if ({obj.emit()} && typeof {obj.emit()}.extend === "function") {{ return {obj.emit()}.extend({args[0].emit()}); }} '
                        f"return; }})()"
                    )
                    return JSIdentifier(code)
                if attr == "insert" and len(args) == 2:
                    code = (
                        f"(() => {{if (Array.isArray({obj.emit()})) {{ {obj.emit()}.splice({args[0].emit()}, 0, {args[1].emit()}); return; }} "
                        f'if ({obj.emit()} && typeof {obj.emit()}.insert === "function") {{ return {obj.emit()}.insert({args[0].emit()}, {args[1].emit()}); }} '
                        f"return; }})()"
                    )
                    return JSIdentifier(code)
                if attr == "remove" and len(args) == 1:
                    code = (
                        f"(() => {{if (Array.isArray({obj.emit()})) {{ const __i={obj.emit()}.indexOf({args[0].emit()}); if(__i>=0){{{obj.emit()}.splice(__i,1);}} return; }} "
                        f'if ({obj.emit()} && typeof {obj.emit()}.remove === "function") {{ return {obj.emit()}.remove({args[0].emit()}); }} '
                        f"return; }})()"
                    )
                    return JSIdentifier(code)
                if attr == "reverse" and len(args) == 0:
                    return JSIdentifier(f"({obj.emit()}.reverse(), undefined)")
                if attr == "sort" and len(args) == 0:
                    return JSIdentifier(f"({obj.emit()}.sort(), undefined)")
                return JSMemberCall(obj, attr, args)
            # Generic call: allow any expression as callee, e.g. (a + b)(1)
            callee = self.emit_expr(node.func)
            if node.keywords:
                raise JSCompilationError(
                    "Keyword arguments are not supported for arbitrary calls"
                )
            args = [self.emit_expr(a) for a in node.args]
            return JSCall(callee, args)
        if isinstance(node, ast.Attribute):
            value = self.emit_expr(node.value)
            return JSMember(value, node.attr)
        if isinstance(node, ast.Subscript):
            value = self.emit_expr(node.value)
            # TODO: handle ast.Tuple for node.slice
            if isinstance(node.slice, ast.Tuple):
                raise JSCompilationError(
                    "Slices with multiple arguments are not implemented yet."
                )
            # Slice handling
            if isinstance(node.slice, ast.Slice):
                if node.slice.step is not None:
                    raise JSCompilationError("Slice steps are not implemented yet.")
                lower = node.slice.lower
                upper = node.slice.upper
                if lower is None and upper is None:
                    # full slice -> copy
                    return JSMemberCall(value, "slice", [])
                elif lower is None:
                    start = JSNumber(0)
                    end = self.emit_expr(upper)
                    return JSMemberCall(value, "slice", [start, end])
                elif upper is None:
                    start = self.emit_expr(lower)
                    return JSMemberCall(value, "slice", [start])
                else:
                    start = self.emit_expr(lower)
                    end = self.emit_expr(upper)
                    return JSMemberCall(value, "slice", [start, end])
            # Negative index single access -> at(), allow non-constant expression too
            if isinstance(node.slice, ast.UnaryOp) and isinstance(
                node.slice.op, ast.USub
            ):
                idx_expr = self.emit_expr(node.slice.operand)
                return JSMemberCall(value, "at", [JSUnary("-", idx_expr)])
            index = self.emit_expr(node.slice)
            return JSSubscript(value, index)
        if isinstance(node, ast.JoinedStr):
            # General f-strings -> backtick template
            template_parts: list[str | JSExpr] = []
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    template_parts.append(part.value)
                elif isinstance(part, ast.FormattedValue):
                    expr = self.emit_expr(part.value)
                    # Apply full format spec if provided
                    if part.format_spec is not None:
                        spec_str = _formatspec_str(part.format_spec)
                        expr = _apply_format_spec(expr, spec_str)
                        # Special case: f-string with a single formatted value -> do not wrap in JS template
                        if len(node.values) == 1:
                            return expr
                    template_parts.append(expr)
                else:
                    raise JSCompilationError(
                        f"Unsupported f-string component: {ast.dump(part, include_attributes=False)}"
                    )
            return JSTemplate(template_parts)
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


def escape_constant_str(s: str):
    return s.replace("\\", "\\\\").replace("`", "\\`")


def _formatspec_str(node: ast.AST):
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
                raise JSCompilationError("Format spec must be a constant string")
        return "".join(parts)
    raise JSCompilationError(
        f"Unexpected format spec: {ast.dump(node, include_attributes=False)}"
    )


def _build_comparison(
    left_expr: JSExpr,
    left_node: ast.expr,
    op: ast.cmpop,
    right_expr: JSExpr,
    right_node: ast.expr,
) -> JSExpr:
    # Identity comparisons: treat as strict equality; special-case None to
    # output x == null to match both null and undefined.
    if isinstance(op, ast.Is) or isinstance(op, ast.IsNot):
        is_not = isinstance(op, ast.IsNot)
        if (isinstance(right_node, ast.Constant) and right_node.value is None) or (
            isinstance(left_node, ast.Constant) and left_node.value is None
        ):
            # For None identity, allow null or undefined via loose equality
            expr = right_expr if isinstance(left_node, ast.Constant) else left_expr
            return JSBinary(expr, "!=" if is_not else "==", JSNull())
        # For non-None, use strict equality which matches desired semantics for our subset
        return JSBinary(left_expr, "!==" if is_not else "===", right_expr)
    # Membership
    if isinstance(op, ast.In) or isinstance(op, ast.NotIn):
        # Runtime branch: arrays/strings use includes, objects use hasOwnProperty
        R = right_expr.emit()
        L = left_expr.emit()
        # Avoid String() for string literal keys
        if isinstance(left_node, ast.Constant) and isinstance(left_node.value, str):
            key_arg = L
        else:
            key_arg = f"String({L})"
        expr_code = (
            f'((Array.isArray({R}) || typeof {R} === "string") ? {R}.includes({L}) : '
            f'({R} && typeof {R} === "object" && Object.hasOwn({R}, {key_arg})))'
        )
        out = JSRaw(expr_code)
        if isinstance(op, ast.NotIn):
            return JSUnary("!", out)
        return out
    # Standard comparisons
    op_type = type(op)
    if op_type not in ALLOWED_CMPOPS:
        raise JSCompilationError("Comparison not allowed")
    return JSBinary(left_expr, ALLOWED_CMPOPS[op_type], right_expr)


def _parse_format_spec(spec: str) -> FormatSpecInfo:
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


def _apply_format_spec(value_expr: JSExpr, spec: str) -> JSExpr:
    spec_info = _parse_format_spec(spec)
    fill = spec_info["fill"] or " "
    align = spec_info["align"]
    sign = spec_info["sign"]
    alt = bool(spec_info["alt"])  # bool
    zero = bool(spec_info["zero"])  # bool
    width = spec_info["width"]
    grouping = spec_info["grouping"]
    precision = spec_info["precision"]
    typ = spec_info["type"]

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
        raise JSCompilationError("Unsupported grouping separator '_' in format spec")
    if align == "=" and typ in {None, "s"}:
        raise JSCompilationError("Alignment '=' is only supported for numeric types")

    # Escape backtick in fill if present
    fill_expr = JSString(fill)

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
        return JSMemberCall(value_expr, "toFixed", [JSNumber(precision)])
    # Build numeric/string representations
    base_expr: JSExpr
    prefix_expr: JSExpr = JSString("")
    if typ is None:
        # Default to string conversion
        base_expr = JSCall(JSIdentifier("String"), [value_expr])
    elif typ == "s":
        base_expr = JSCall(JSIdentifier("String"), [value_expr])
        if precision is not None:
            base_expr = JSMemberCall(
                base_expr, "slice", [JSNumber(0), JSNumber(precision)]
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
                JSIdentifier("String"),
                [JSCall(JSIdentifier("Math.trunc"), [abs_num])],
            )
        else:
            base_map = {"b": 2, "o": 8, "x": 16, "X": 16}
            digits = JSMemberCall(
                JSCall(JSIdentifier("Math.trunc"), [abs_num]),
                "toString",
                [JSNumber((base_map[typ]))],
            )
            if typ == "X":
                digits = JSMemberCall(digits, "toUpperCase", [])
        if alt and typ in {"b", "o", "x", "X"}:
            prefix = {"b": "0b", "o": "0o", "x": "0x", "X": "0X"}[typ]
            prefix_expr = JSString(prefix)
        # Apply grouping for decimal with comma
        if grouping == "," and typ == "d":
            # Use locale formatting for thousands separators
            digits = JSMemberCall(
                JSCall(JSIdentifier("Math.trunc"), [abs_num]),
                "toLocaleString",
                [JSString("en-US")],
            )
        base_expr = digits
    elif typ in {"f", "F", "e", "E", "g", "G", "n", "%"}:
        num = JSCall(JSIdentifier("Number"), [value_expr])
        abs_num = JSCall(JSIdentifier("Math.abs"), [num])
        if typ in {"f", "F"}:
            p = precision if precision is not None else 6
            if grouping == ",":
                s = JSMemberCall(
                    abs_num,
                    "toLocaleString",
                    [
                        JSString("en-US"),
                        JSIdentifier(
                            f"{{minimumFractionDigits: {p}, maximumFractionDigits: {p}}}"
                        ),
                    ],
                )
            else:
                s = JSMemberCall(abs_num, "toFixed", [JSNumber(p)])
        elif typ in {"e", "E"}:
            p = precision if precision is not None else 6
            s = JSMemberCall(abs_num, "toExponential", [JSNumber(p)])
            if typ == "E":
                s = JSMemberCall(s, "toUpperCase", [])
        elif typ in {"g", "G"}:
            p = precision if precision is not None else 6
            s = JSMemberCall(abs_num, "toPrecision", [JSNumber(p)])
            if typ == "G":
                s = JSMemberCall(s, "toUpperCase", [])
        elif typ == "n":
            if precision is None:
                s = JSMemberCall(abs_num, "toLocaleString", [JSString("en-US")])
            else:
                s = JSMemberCall(
                    abs_num,
                    "toLocaleString",
                    [
                        JSString("en-US"),
                        JSIdentifier(
                            f"{{minimumFractionDigits: {precision}, maximumFractionDigits: {precision}}}"
                        ),
                    ],
                )
        else:  # '%'
            p = precision if precision is not None else 6
            s = JSBinary(
                left=JSMemberCall(
                    JSBinary(abs_num, "*", JSNumber(100)),
                    "toFixed",
                    [JSNumber(p)],
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
        cond = JSBinary(num, "<", JSNumber(0))
        if sign == "+":
            sign_expr = JSTertiary(cond, JSString("-"), JSString("+"))
        elif sign == " ":
            sign_expr = JSTertiary(cond, JSString("-"), JSString(" "))
        else:
            sign_expr = JSTertiary(cond, JSString("-"), JSString(""))
    else:
        sign_expr = JSString("")

    # Combine sign/prefix with base while avoiding unnecessary "" + chains
    def _is_empty_template(e: JSExpr) -> bool:
        return isinstance(e, JSTemplate) and len(e.parts) == 0

    def _is_empty_string(e: JSExpr) -> bool:
        return isinstance(e, JSString) and e.value == ""

    head: JSExpr | None = None
    # Prefer to include sign when present (numeric types), then prefix if non-empty
    if not _is_empty_template(sign_expr) and not _is_empty_string(sign_expr):
        head = sign_expr
    if not _is_empty_template(prefix_expr) and not _is_empty_string(prefix_expr):
        head = prefix_expr if head is None else JSBinary(head, "+", prefix_expr)

    combined: JSExpr
    if head is not None:
        combined = JSBinary(head, "+", base_expr)
    else:
        combined = base_expr

    # Width, alignment and zero-padding
    if width is not None and width > 0:
        if align == "^":
            # padStart to center: floor((width + len) / 2)
            half = JSCall(
                JSIdentifier("Math.floor"),
                [
                    JSBinary(
                        JSBinary(
                            JSNumber(width),
                            "+",
                            JSMember(combined, "length"),
                        ),
                        "/",
                        JSNumber(2),
                    )
                ],
            )
            combined = JSMemberCall(
                JSMemberCall(combined, "padStart", [half, fill_expr]),
                "padEnd",
                [JSNumber(width), fill_expr],
            )
        elif align == "<":
            combined = JSMemberCall(combined, "padEnd", [JSNumber(width), fill_expr])
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
                # Width should be like: width - ((head).length)
                # Prefer sign only for length when prefix is empty
                use_prefix_in_len = not _is_empty_template(
                    prefix_expr
                ) and not _is_empty_string(prefix_expr)
                head_for_len: JSExpr = (
                    sign_expr
                    if not use_prefix_in_len
                    else JSBinary(sign_expr, "+", prefix_expr)
                )
                # Avoid double parentheses around sign template
                width_arg = JSIdentifier(f"{width} - ({head_for_len.emit()}).length")
                tail = base_expr
                combined = JSBinary(
                    JSBinary(sign_expr, "+", prefix_expr),
                    "+",
                    JSMemberCall(
                        tail,
                        "padStart",
                        [
                            width_arg,
                            fill_expr,
                        ],
                    ),
                )
            else:
                combined = JSMemberCall(
                    combined, "padStart", [JSNumber(width), fill_expr]
                )
        else:
            pad_fill = fill_expr if not zero else JSString("0")
            if (
                zero
                and align is None
                and typ in {"d", "f", "F", "e", "E", "g", "G", "n", "%"}
            ):
                head_only_sign: JSExpr = sign_expr
                tail = base_expr
                zero_padded = JSBinary(
                    head_only_sign,
                    "+",
                    JSMemberCall(
                        tail,
                        "padStart",
                        [
                            JSBinary(
                                JSNumber(width), "-", JSMember(head_only_sign, "length")
                            ),
                            JSString("0"),
                        ],
                    ),
                )
                if not _is_empty_template(prefix_expr) and not _is_empty_string(
                    prefix_expr
                ):
                    head_with_prefix = JSBinary(head_only_sign, "+", prefix_expr)
                    zero_padded = JSBinary(
                        head_with_prefix,
                        "+",
                        JSMemberCall(
                            tail,
                            "padStart",
                            [
                                JSBinary(
                                    JSNumber(width),
                                    "-",
                                    JSMember(head_with_prefix, "length"),
                                ),
                                JSString("0"),
                            ],
                        ),
                    )
                combined = zero_padded
            else:
                combined = JSMemberCall(
                    combined, "padStart", [JSNumber(width), pad_fill]
                )

    return combined
