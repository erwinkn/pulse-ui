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
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Optional,
    Sequence,
    TypedDict,
    Union,
    cast,
)

from pulse.javascript.format_spec import _apply_format_spec, _extract_formatspec_str
from pulse.javascript.reftable import ReferenceTable

from .nodes import (
    PRIMARY_PRECEDENCE,
    ALLOWED_BINOPS,
    ALLOWED_CMPOPS,
    ALLOWED_UNOPS,
    JSArray,
    JSArrowFunction,
    JSAssign,
    JSAugAssign,
    JSBinary,
    JSBoolean,
    JSBreak,
    JSCall,
    JSCompilationError,
    JSComputedProp,
    JSConstAssign,
    JSContinue,
    JSExpr,
    JSForOf,
    JSFunctionDef,
    JSIdentifier,
    JSIf,
    JSLogicalChain,
    JSMember,
    JSMemberCall,
    JSMultiStmt,
    JSNew,
    JSNull,
    JSNumber,
    JSObject,
    JSProp,
    JSRaw,
    JSReturn,
    JsSingleStmt,
    JSSpread,
    JSStmt,
    JSString,
    JSSubscript,
    JSTemplate,
    JSTertiary,
    JSUnary,
    JSUndefined,
    JSWhile,
)


###############################################################################
# Python AST -> JS AST
###############################################################################


class JsTranspiler(ast.NodeVisitor):
    """AST visitor that builds a JS AST from a restricted Python subset.

    The visitor can be provided with:
    - predeclared: names that are already declared in the current scope (e.g.,
      parameters). These will not be re-declared with 'let' on first assignment.
    - ref_table: mapping from Python identifier -> JSExpr to inline/rename
      non-local/global references resolved by the orchestrator.
    """

    def __init__(
        self,
        fndef: ast.FunctionDef,
        args: list[str],
        globals_: list[str],
        ref: ReferenceTable,
    ) -> None:
        self.fndef = fndef
        self.args = args
        self.globals = globals_
        self.ref = ref

        self.predeclared: set[str] = set(args) | set(globals_)
        # Track locals for declaration decisions
        self.locals: set[str] = set(self.predeclared)
        self._lines: list[str] = []
        self._temp_counter: int = 0

    # -----------------------------
    # Builtin replacement helpers
    # -----------------------------

    def _builtin_function(self, fname: str, node: ast.Call) -> JSExpr:
        args = [self.emit_expr(a) for a in node.args]
        # Build kw_map as JSExprs
        kw_map: dict[str, JSExpr] = {}
        for kw in node.keywords:
            if kw.arg is None:
                raise JSCompilationError("**kwargs not supported")
            kw_map[kw.arg] = self.emit_expr(kw.value)

        if fname == "print":
            return JSMemberCall(JSIdentifier("console"), "log", args)
        if fname == "len" and len(args) == 1:
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
            if len(args) == 1:
                return JSCall(JSIdentifier("parseInt"), [args[0]])
            if len(args) == 2:
                return JSCall(JSIdentifier("parseInt"), [args[0], args[1]])
        if fname == "float" and len(args) == 1:
            return JSCall(JSIdentifier("parseFloat"), [args[0]])
        if fname == "list" and len(args) == 1:
            return args[0]
        if fname in {"any", "all"} and len(node.args) == 1:
            gen_arg = node.args[0]
            if (
                isinstance(gen_arg, ast.GeneratorExp)
                and len(gen_arg.generators) == 1
                and not gen_arg.generators[0].ifs
            ):
                g = gen_arg.generators[0]
                if g.is_async:
                    raise JSCompilationError("Async comprehensions are not supported")
                iter_expr = self.emit_expr(g.iter)
                param_code, names = self._arrow_param_from_target(g.target)
                for nm in names:
                    self.locals.add(nm)
                pred = self.emit_expr(gen_arg.elt)
                method = "some" if fname == "any" else "every"
                return JSMemberCall(
                    iter_expr, method, [JSArrowFunction(param_code, pred)]
                )
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
        # Fallback generic call
        if node.keywords:
            raise JSCompilationError(
                "Keyword arguments are not supported for arbitrary calls"
            )
        callee_expr = self.emit_expr(node.func)
        return JSCall(callee_expr, args)

    def _builtin_method(
        self, attr: str, obj: JSExpr, args: list[JSExpr], node: ast.Call
    ) -> JSExpr:
        # String/array/dict helpers
        if attr == "join" and len(args) == 1:
            return JSMemberCall(args[0], "join", [obj])
        if attr == "get" and 1 <= len(node.args) <= 2:
            key_node = node.args[0]
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
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
            mapping = {"lower": "toLowerCase", "upper": "toUpperCase", "strip": "trim"}
            return JSMemberCall(obj, mapping[attr], [])
        if attr == "capitalize" and len(args) == 0:
            left = JSMemberCall(
                JSMemberCall(obj, "charAt", [JSNumber(0)]), "toUpperCase", []
            )
            right = JSMemberCall(
                JSMemberCall(obj, "slice", [JSNumber(1)]), "toLowerCase", []
            )
            return JSBinary(left, "+", right)
        if attr == "zfill" and len(args) == 1:
            return JSMemberCall(obj, "padStart", [args[0], JSString("0")])
        if attr in {"startswith", "endswith"} and len(args) == 1:
            mapping = {"startswith": "startsWith", "endswith": "endsWith"}
            return JSMemberCall(obj, mapping[attr], [args[0]])
        if attr == "lstrip" and len(args) == 0:
            return JSMemberCall(obj, "trimStart", [])
        if attr == "rstrip" and len(args) == 0:
            return JSMemberCall(obj, "trimEnd", [])
        if attr == "replace" and len(args) == 2:
            return JSMemberCall(obj, "replaceAll", [args[0], args[1]])
        if attr == "index" and len(args) == 1:
            return JSMemberCall(obj, "indexOf", [args[0]])
        if attr == "count" and len(args) == 1:
            filtered = JSMemberCall(
                obj,
                "filter",
                [JSArrowFunction("v", JSBinary(JSIdentifier("v"), "===", args[0]))],
            )
            return JSMember(filtered, "length")
        if attr == "copy" and len(args) == 0:
            return JSTertiary(
                JSCall(JSIdentifier("Array.isArray"), [obj]),
                JSMemberCall(obj, "slice", []),
                JSObject([JSSpread(obj)]),
            )
        # Pop can appear on lists, dict, or set
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
            code = (
                f"(() => {{if (Array.isArray({obj.emit()})) {{ {obj.emit()}.length = 0; return; }} "
                f'if ({obj.emit()} && typeof {obj.emit()} === "object") {{ for (const __k in {obj.emit()}){{ if (Object.hasOwn({obj.emit()}, __k)) delete {obj.emit()}[__k]; }} return; }} '
                f"return {obj.emit()}.clear(); }})()"
            )
            return JSIdentifier(code)
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
    def transpile(self, body: list[ast.stmt]) -> JSFunctionDef:
        stmts: list[JSStmt] = []
        # Reset temp counter per function emission
        self._temp_counter = 0
        for stmt in body:
            s = self.emit_stmt(stmt)
            if s is None:
                continue
            stmts.append(s)
        # Function expression
        return JSFunctionDef(self.args, stmts)

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
            if ident in self.locals:
                return JSIdentifier(_mangle_identifier(ident))
            if ident in self.ref.rename:
                return self.ref.rename[ident]
            # Unresolved non-local
            raise JSCompilationError(
                f"Unsupported free variables referenced: {ident}. Only parameters and local variables are allowed."
            )
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
                # Reference-table hook for function calls
                if fname in self.ref.replace_function:
                    return self.ref.replace_function[fname](node, self)
                # Builtin fallback
                return self._builtin_function(fname, node)
            if isinstance(node.func, ast.Attribute):
                obj = self.emit_expr(node.func.value)
                attr = node.func.attr
                args = [self.emit_expr(a) for a in node.args]
                # Reference-table hook for method calls (by attribute name only)
                if attr in self.ref.replace_method:
                    return self.ref.replace_method[attr](node, self)
                # Centralized builtin-dispatch for ambiguous methods
                # builtin methods fallback
                return self._builtin_method(attr, obj, args, node)
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
                        spec_str = _extract_formatspec_str(part.format_spec)
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
    # Legacy compile uses bare transpiler with no refs/globals
    ref = ReferenceTable(rename={}, replace_function={}, replace_method={})
    visitor = JsTranspiler(fndef, arg_names, [], ref)
    js_fn = visitor.transpile(fndef.body)
    code = js_fn.emit()
    n_args = len(arg_names)
    h = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
    return code, n_args, h


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


def _mangle_identifier(name: str) -> str:
    # Keep simple characters; this can be expanded later if needed
    return name
