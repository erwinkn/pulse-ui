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

from abc import ABC, abstractmethod
import ast
import hashlib
import inspect
import textwrap
from dataclasses import dataclass  # noqa: F401
from typing import Any, Callable, Sequence, cast

from pulse.javascript.format_spec import _apply_format_spec, _extract_formatspec_str
from pulse.javascript.reftable import ReferenceTable

from .nodes import (
    ALLOWED_BINOPS,
    ALLOWED_CMPOPS,
    ALLOWED_UNOPS,
    JSArray,
    JSArrowFunction,
    JSAssign,
    JSAugAssign,
    JSBinary,
    JSBlock,
    JSBoolean,
    JSBreak,
    JSCall,
    JSCompilationError,
    JSComputedProp,  # noqa: F401
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
    JSSingleStmt,
    JSMultiStmt,
    JSNew,
    JSNull,
    JSNumber,
    JSProp,  # noqa: F401
    JSReturn,
    JSSpread,
    JSStmt,
    JSString,
    JSSubscript,
    JSTemplate,
    JSTertiary,
    JSUnary,
    JSUndefined,
    JSWhile,
    JSComma,
    is_primary,
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
        # Generic dispatchers for known types
        expr = JSMemberCall(obj, attr, args)
        # Apply in increasing priority so that later (higher priority) wrappers
        # end up outermost in the final expression. We prefer string/list
        # semantics first, then set, then dict, to better match common Python
        # expectations for overlapping method names like pop/copy.
        builtins: list[type[BuiltinMethods]] = [
            DictMethods,
            SetMethods,
            ListMethods,
            StringMethods,
        ]
        for cls in builtins:
            if attr in cls.__methods__():
                try:
                    instance = cls(obj)
                    dispatch_expr = getattr(instance, attr)(*args)
                    if dispatch_expr is not None:
                        expr = JSTertiary(
                            cls.__runtime_check__(obj), dispatch_expr, expr
                        )
                except TypeError:
                    pass
        # if attr in DICT_METHODS:
        #     di = DictTranspiler(obj)
        #     try:
        #         di_expr = getattr(di, attr)(*args)
        #         if di_expr is not None:
        #             expr = JSTertiary(
        #                 di.__runtime_check__(obj), di_expr, expr
        #             )
        #     except TypeError:
        #         pass
        # if attr in SET_METHODS:
        #     se = SetMethods(obj)
        #     try:
        #         expr = JSTertiary(
        #             se.__runtime_check__(obj), getattr(se, attr)(*args), expr
        #         )
        #     except TypeError:
        #         pass
        # if attr in LIST_METHODS:
        #     ls = ListMethods(obj)
        #     try:
        #         expr = JSTertiary(
        #             ls.__runtime_check__(obj), getattr(ls, attr)(*args), expr
        #         )
        #     except TypeError:
        #         pass
        # if attr in STR_METHODS:
        #     st = StringMethods(obj)
        #     try:
        #         expr = JSTertiary(
        #             st.__runtime_check__(obj), getattr(st, attr)(*args), expr
        #         )
        #     except TypeError:
        #         pass
        return expr

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
                tmp_name = f"$tmp{self._temp_counter}"
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
            return JSSingleStmt(self.emit_expr(node.value))
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
            # Convert Python dict literal to new Map([...])
            entries: list[JSExpr] = []
            for k, v in zip(node.keys, node.values):
                if k is None:
                    # Spread merge: normalize to iterable of [k, v] pairs
                    vexpr = self.emit_expr(v)
                    is_map = JSBinary(vexpr, "instanceof", JSIdentifier("Map"))
                    map_entries = JSMemberCall(vexpr, "entries", [])
                    obj_entries = JSCall(
                        JSMember(JSIdentifier("Object"), "entries"), [vexpr]
                    )
                    entries.append(
                        JSSpread(JSTertiary(is_map, map_entries, obj_entries))
                    )
                    continue
                key_expr = self.emit_expr(k)
                val_expr = self.emit_expr(v)
                entries.append(JSArray([key_expr, val_expr]))
            return JSNew(JSIdentifier("Map"), [JSArray(entries)])
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
            # {k: v for ...} -> new Map(chain.map(x => [k, v]))
            pairs = self._build_comprehension_chain(
                node.generators,
                lambda: JSArray(
                    [
                        self.emit_expr(node.key),
                        self.emit_expr(node.value),
                    ]
                ),
            )
            return JSNew(JSIdentifier("Map"), [pairs])
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
        # arrays/strings: includes; objects: hasOwn
        is_string = StringMethods.__runtime_check__(right_expr)
        is_array = ListMethods.__runtime_check__(right_expr)
        is_set = SetMethods.__runtime_check__(right_expr)
        is_map = DictMethods.__runtime_check__(right_expr)
        is_array_or_string = JSLogicalChain("||", [is_array, is_string])
        is_set_or_map = JSLogicalChain("||", [is_set, is_map])
        has_array_or_string = JSMemberCall(right_expr, "includes", [left_expr])
        has_set_or_map = JSMemberCall(right_expr, "has", [left_expr])
        has_obj = JSBinary(left_expr, "in", right_expr)

        membership_expr = JSTertiary(
            is_array_or_string,
            has_array_or_string,
            JSTertiary(is_set_or_map, has_set_or_map, has_obj),
        )
        if isinstance(op, ast.NotIn):
            membership_expr = JSUnary('!', membership_expr)
        return membership_expr
    # Standard comparisons
    op_type = type(op)
    if op_type not in ALLOWED_CMPOPS:
        raise JSCompilationError("Comparison not allowed")
    return JSBinary(left_expr, ALLOWED_CMPOPS[op_type], right_expr)


def _mangle_identifier(name: str) -> str:
    # Keep simple characters; this can be expanded later if needed
    return name


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
    # def split(self, sep: JSExpr):
    #     return JSMemberCall(self.this, "split", [sep])

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
    # def add(self, value: JSExpr):
    #     return JSMemberCall(self.this, "add", [value])

    # `clear` doesn't require any modifications
    # def clear(self):
    #     return JSMemberCall(self.this, "clear", [])

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
    # def clear(self):
    #     return JSMemberCall(self.this, "clear", [])


DICT_METHODS = {k for k in DictMethods.__dict__.keys() if not k.startswith("__")}


def iife(body: JSExpr | Sequence[JSStmt | None]):
    if not isinstance(body, JSExpr):
        fn_body = JSBlock(list(filter(None, body)))
    else:
        fn_body = body

    return JSCall(JSArrowFunction("()", fn_body), [])


def const(ident: str, value: JSExpr):
    ident_expr = JSIdentifier(ident)
    return ident_expr, JSConstAssign(ident, value)


def let(ident: str, value: JSExpr):
    ident_expr = JSIdentifier(ident)
    return ident_expr, JSAssign(ident, value)


def define_if_not_primary(ident: str, expr: JSExpr):
    if is_primary(expr):
        return expr, None
    return const(ident, expr)
