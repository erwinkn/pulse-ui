# Transpiler V2 Review: Issues & Proposed Solutions

This document catalogs issues identified in the v2 transpiler system along with proposed solutions. Issues are organized by category and prioritized.

---

## Priority Legend

- **P0 (Critical)**: Causes incorrect behavior or data corruption
- **P1 (High)**: Significant functionality gaps or fragile patterns
- **P2 (Medium)**: Missing features or inconsistencies
- **P3 (Low)**: Minor improvements or edge cases

---

## 1. Python/JavaScript Semantic Mismatches

### 1.1 `list.remove()` Silently Removes Wrong Element [P0]

**Location:** `builtins.py:673-678`

**Problem:**
```python
def remove(self, value: Expr) -> Expr:
    return Call(
        Member(self.this, "splice"),
        [Call(Member(self.this, "indexOf"), [value]), Literal(1)],
    )
```

Python's `list.remove(x)` raises `ValueError` if x not found. The JS version calls `splice(indexOf(x), 1)`. When `indexOf` returns `-1`, this splices at index -1, **removing the last element** instead of raising an error.

**Proposed Solution:**
```python
def remove(self, value: Expr) -> Expr:
    """list.remove(value) -> safe removal with error on not found"""
    # Generate: (idx => idx === -1 ? (() => { throw new Error("...") })() : list.splice(idx, 1))(list.indexOf(value))
    idx = Identifier("$idx")
    index_call = Call(Member(self.this, "indexOf"), [value])
    throw_expr = Call(
        Arrow([], Call(Identifier("(() => { throw new Error('list.remove(x): x not in list') })"), [])),
        []
    )
    safe_splice = Ternary(
        Binary(idx, "===", Literal(-1)),
        throw_expr,
        Call(Member(self.this, "splice"), [idx, Literal(1)])
    )
    return Call(Arrow(["$idx"], safe_splice), [index_call])
```

Alternatively, emit a simpler runtime check:
```javascript
((i) => i < 0 ? (() => {throw new Error("x not in list")})() : list.splice(i, 1))(list.indexOf(x))
```

---

### 1.2 Floor Division `//` Not Supported [P1]

**Location:** `transpiler.py:45-52`

**Problem:** Python's `//` operator is not in `ALLOWED_BINOPS`. Users get "Unsupported binary operator: FloorDiv" with no guidance.

**Proposed Solution:**
```python
# In ALLOWED_BINOPS, add special handling:
# ast.FloorDiv cannot map directly to a JS operator

# In _emit_binop():
def _emit_binop(self, node: ast.BinOp) -> Expr:
    op = type(node.op)

    # Special case: floor division
    if op is ast.FloorDiv:
        left = self.emit_expr(node.left)
        right = self.emit_expr(node.right)
        # x // y -> Math.floor(x / y)
        return Call(
            Member(Identifier("Math"), "floor"),
            [Binary(left, "/", right)]
        )

    # ... rest of existing code
```

---

### 1.3 `str.split()` Without Args Behaves Differently [P1]

**Location:** `builtins.py:536-538`

**Problem:**
- Python: `"a  b".split()` → `["a", "b"]` (splits on whitespace, removes empty)
- JavaScript: `"a  b".split()` → `["a  b"]` (returns whole string)

Current code returns `None` to fall through to default `.split()` call.

**Proposed Solution:**
```python
def split(self, sep: Expr | None = None) -> Expr | None:
    """str.split(sep) -> str.split(sep) or special whitespace handling"""
    if sep is None:
        # Python's default: split on whitespace and filter empties
        # "a  b".split() -> "a  b".trim().split(/\s+/)
        trimmed = Call(Member(self.this, "trim"), [])
        return Call(Member(trimmed, "split"), [Identifier(r"/\s+/")])
    return None  # Fall through for explicit separator
```

Note: Need to handle the case where `sep` is `Literal(None)` vs not provided at all. The transformer signature should distinguish these:

```python
@transformer("str.split")  # Method-specific transformer
def emit_str_split(self_expr: Any, *args: Any, ctx: Transpiler) -> Expr:
    if len(args) == 0:
        # No separator provided - Python whitespace semantics
        trimmed = Call(Member(ctx.emit_expr(self_expr), "trim"), [])
        return Call(Member(trimmed, "split"), [Identifier(r"/\s+/")])
    # Explicit separator
    return None  # Fall through
```

---

### 1.4 Truthy/Falsy Differences in `filter()` [P2]

**Location:** `builtins.py:194-211`

**Problem:** `filter(None, iterable)` uses `v => v` predicate, which uses JS truthiness. Empty arrays `[]` are truthy in JS but falsy in Python.

**Proposed Solution:**

For full Python compatibility, implement a `pyTruthy` helper:
```javascript
const pyTruthy = (v) =>
  v != null &&
  v !== false &&
  v !== 0 &&
  v !== "" &&
  !(Array.isArray(v) && v.length === 0) &&
  !(v instanceof Set && v.size === 0) &&
  !(v instanceof Map && v.size === 0);
```

Then in the transpiler:
```python
@transformer("filter")
def emit_filter(*args: Any, ctx: Transpiler) -> Expr:
    # ... existing code ...
    if is_none_filter:
        # Use Python-compatible truthiness
        predicate = Identifier("$pyTruthy")  # Must be included in runtime
```

**Alternative:** Document that `filter(None, ...)` uses JS truthiness and recommend explicit predicates for edge cases. This is a tradeoff between correctness and code size.

---

### 1.5 String Multiplication Not Supported [P3]

**Location:** `transpiler.py:45-52`

**Problem:** Python `"a" * 3` → `"aaa"`, but JS `"a" * 3` → `NaN`. The `*` operator is allowed without type checking.

**Proposed Solution:**

Option A: Disallow and provide clear error
```python
def _emit_binop(self, node: ast.BinOp) -> Expr:
    # After emitting, check for string * number pattern
    # This requires type inference which we don't have
```

Option B: Document as known limitation

Option C: Use runtime check (expensive)
```python
# x * y -> typeof x === "string" ? x.repeat(y) : x * y
```

**Recommendation:** Document as limitation. Type inference would be needed for a clean solution.

---

## 2. Format Spec Parser Issues

### 2.1 Center Alignment Uses Uninitialized `expr.length` [P0]

**Location:** `transpiler.py:877-898`

**Problem:** The center alignment code uses `Member(expr, "length")` but `expr` may be a number at this point (e.g., after `toFixed()`), not a string.

**Current Code:**
```python
elif align == "^":
    expr = Call(
        Member(
            Call(
                Member(expr, "padStart"),
                [
                    Binary(
                        Binary(
                            Binary(width_num, "+", Member(expr, "length")),  # BUG: expr may not be string
```

**Proposed Solution:**
```python
elif align == "^":
    # Ensure expr is a string first
    str_expr = Call(Identifier("String"), [expr])
    len_expr = Member(str_expr, "length")

    # Calculate padding: (width + len) / 2 | 0
    pad_left = Binary(
        Binary(Binary(width_num, "+", len_expr), "/", Literal(2)),
        "|",
        Literal(0),
    )

    expr = Call(
        Member(
            Call(Member(str_expr, "padStart"), [pad_left, fill_str]),
            "padEnd",
        ),
        [width_num, fill_str],
    )
```

---

### 2.2 Thousand Separators Matched But Ignored [P2]

**Location:** `transpiler.py:775-907`

**Problem:** The regex captures group 6 for `,` and `_` thousand separators but never uses it.

```python
pattern = r"^...([,_])?..."  # Group 6
# match.group(6) is never used
```

**Proposed Solution:**
```python
def _parse_and_apply_format(self, expr: Expr, spec: str) -> Expr:
    # ... existing parsing ...
    grouping = match.group(6)  # ',' or '_' or None

    # After type conversion, before padding:
    if grouping:
        # Use toLocaleString for comma grouping
        if grouping == ",":
            expr = Call(Member(expr, "toLocaleString"), [Literal("en-US")])
        elif grouping == "_":
            # No native JS support, use regex replacement
            # expr.toLocaleString().replace(/,/g, "_")
            locale_str = Call(Member(expr, "toLocaleString"), [Literal("en-US")])
            expr = Call(
                Member(locale_str, "replace"),
                [Identifier("/,/g"), Literal("_")]
            )
```

---

### 2.3 Missing Format Types: `%`, `n`, `c`, `g`/`G` [P2]

**Location:** `transpiler.py:809-861`

**Problem:** These format types are in the regex but not implemented.

**Proposed Solution:**
```python
# Add to _parse_and_apply_format:

elif type_char == "%":
    # Percentage: multiply by 100, add %
    prec = precision if precision is not None else 6
    multiplied = Binary(expr, "*", Literal(100))
    fixed = Call(Member(multiplied, "toFixed"), [Literal(prec)])
    expr = Binary(fixed, "+", Literal("%"))

elif type_char == "c":
    # Character: convert code point to character
    expr = Call(Member(Identifier("String"), "fromCodePoint"), [expr])

elif type_char in ("g", "G"):
    # General format: use toPrecision
    prec = precision if precision is not None else 6
    expr = Call(Member(expr, "toPrecision"), [Literal(prec)])
    if type_char == "G":
        expr = Call(Member(expr, "toUpperCase"), [])

elif type_char == "n":
    # Locale-aware number (simplified to toLocaleString)
    expr = Call(Member(expr, "toLocaleString"), [])
```

---

## 3. Global State & Concurrency Issues

### 3.1 Non-Thread-Safe Global Registries [P1]

**Location:** `function.py:50-54`, `nodes.py:55`, `imports.py:128`

**Problem:** Global mutable dictionaries without synchronization:
```python
FUNCTION_CACHE: dict[Callable[..., Any], AnyJsFunction] = {}
CONSTANT_REGISTRY: dict[int, "Constant"] = {}
EXPR_REGISTRY: dict[int, "Expr"] = {}
_IMPORT_REGISTRY: dict[_ImportKey, "Import"] = {}
```

**Proposed Solution:**

Option A: Thread-local registries
```python
import threading

_local = threading.local()

def get_function_cache() -> dict[Callable[..., Any], AnyJsFunction]:
    if not hasattr(_local, 'function_cache'):
        _local.function_cache = {}
    return _local.function_cache
```

Option B: Context-based transpilation
```python
@dataclass
class TranspileContext:
    function_cache: dict[Callable[..., Any], AnyJsFunction] = field(default_factory=dict)
    constant_registry: dict[int, Constant] = field(default_factory=dict)
    expr_registry: dict[int, Expr] = field(default_factory=dict)
    import_registry: dict[_ImportKey, Import] = field(default_factory=dict)
    id_counter: int = 0

# Pass context through all functions
def javascript(fn, *, ctx: TranspileContext | None = None):
    ctx = ctx or TranspileContext()
    # ...
```

Option C: Lock-based protection (simplest)
```python
import threading

_CACHE_LOCK = threading.RLock()

def javascript(fn):
    with _CACHE_LOCK:
        if fn in FUNCTION_CACHE:
            return FUNCTION_CACHE[fn]
        # ... rest of transpilation
```

**Recommendation:** Option C for minimal disruption, Option B for cleaner architecture.

---

### 3.2 Identity-Based Caching with `id()` [P2]

**Location:** `function.py:50-54`, `nodes.py:265`

**Problem:** Using `id(value)` as dict keys can cause issues:
- Objects can be garbage collected, new objects can get same id
- No weak references → potential memory leaks

**Proposed Solution:**
```python
import weakref

# For functions (can use weakref):
FUNCTION_CACHE: weakref.WeakKeyDictionary[Callable[..., Any], AnyJsFunction] = weakref.WeakKeyDictionary()

# For arbitrary values (harder - many aren't weakref-able):
# Option: Use (id, hash of repr) as key with periodic cleanup
# Option: Use WeakValueDictionary and accept some re-transpilation
```

For EXPR_REGISTRY, consider:
```python
# Store both id and a weak reference where possible
@dataclass
class RegistryEntry:
    expr: Expr
    weak_ref: weakref.ref | None = None

EXPR_REGISTRY: dict[int, RegistryEntry] = {}

def register(value: Any, expr: Expr) -> None:
    try:
        weak = weakref.ref(value, lambda _: EXPR_REGISTRY.pop(id(value), None))
        EXPR_REGISTRY[id(value)] = RegistryEntry(expr, weak)
    except TypeError:
        # Not weakref-able
        EXPR_REGISTRY[id(value)] = RegistryEntry(expr, None)
```

---

## 4. Missing Python Syntax Support

### 4.1 Exception Handling Not Supported [P1]

**Location:** `transpiler.py:225-313`

**Problem:** No `try`/`except`/`finally`/`raise` support despite `Throw` node existing.

**Proposed Solution:**

Add statement handlers:
```python
# In emit_stmt():
if isinstance(node, ast.Try):
    return self._emit_try(node)

if isinstance(node, ast.Raise):
    return self._emit_raise(node)

def _emit_try(self, node: ast.Try) -> Stmt:
    body = [self.emit_stmt(s) for s in node.body]

    handlers = []
    for handler in node.handlers:
        # handler.type is the exception type (or None for bare except)
        # handler.name is the variable name (or None)
        catch_body = [self.emit_stmt(s) for s in handler.body]
        handlers.append(CatchClause(
            param=handler.name,
            body=catch_body
        ))

    finally_body = [self.emit_stmt(s) for s in node.finalbody] if node.finalbody else None

    return TryStmt(body, handlers, finally_body)

def _emit_raise(self, node: ast.Raise) -> Stmt:
    if node.exc is None:
        # Bare raise - re-raise current exception
        return Throw(Identifier("$err"))  # Assumes we're in catch block
    exc_expr = self.emit_expr(node.exc)
    return Throw(exc_expr)
```

New node types needed:
```python
@dataclass(slots=True)
class CatchClause:
    param: str | None
    body: Sequence[Stmt]

@dataclass(slots=True)
class TryStmt(Stmt):
    body: Sequence[Stmt]
    handlers: Sequence[CatchClause]
    finally_: Sequence[Stmt] | None = None

    def emit(self, out: list[str]) -> None:
        out.append("try {\n")
        for stmt in self.body:
            stmt.emit(out)
            out.append("\n")
        out.append("}")
        for handler in self.handlers:
            out.append(" catch")
            if handler.param:
                out.append(f" ({handler.param})")
            out.append(" {\n")
            for stmt in handler.body:
                stmt.emit(out)
                out.append("\n")
            out.append("}")
        if self.finally_:
            out.append(" finally {\n")
            for stmt in self.finally_:
                stmt.emit(out)
                out.append("\n")
            out.append("}")
```

---

### 4.2 Walrus Operator `:=` Not Supported [P2]

**Location:** `transpiler.py:399-487`

**Problem:** Python 3.8+ `NamedExpr` (walrus operator) not handled.

**Proposed Solution:**
```python
if isinstance(node, ast.NamedExpr):
    # x := expr -> (x = expr, x)[1] in JS
    # Or use comma operator: (x = expr)
    target = node.target.id
    value = self.emit_expr(node.value)

    # Add to locals if new
    if target not in self.locals:
        self.locals.add(target)
        # Need to emit declaration somewhere - tricky!

    # Return assignment expression
    return Binary(
        Identifier(target),
        "=",
        value
    )
```

**Challenge:** JS `let`/`const` declarations can't be inside expressions. Options:
1. Hoist declarations to function start
2. Use IIFE: `((x) => (x = expr, x))(undefined)`
3. Require pre-declaration

---

### 4.3 Slice with Step Not Supported [P2]

**Location:** `transpiler.py:716-733`

**Problem:** `x[::2]` raises "Slice steps are not supported"

**Proposed Solution:**
```python
def _emit_slice(self, value: Expr, slice_node: ast.Slice) -> Expr:
    lower = slice_node.lower
    upper = slice_node.upper
    step = slice_node.step

    if step is not None:
        step_expr = self.emit_expr(step)
        # arr.slice(lower, upper).filter((_, i) => i % step === 0)
        base_slice = self._emit_simple_slice(value, lower, upper)
        return Call(
            Member(base_slice, "filter"),
            [Arrow(["_", "i"], Binary(Binary(Identifier("i"), "%", step_expr), "===", Literal(0)))]
        )

    return self._emit_simple_slice(value, lower, upper)
```

**Note:** This doesn't handle negative steps (reversing). For `x[::-1]`:
```python
if is_negative_one_step:
    return Call(Member(Call(Member(value, "slice"), []), "reverse"), [])
```

---

## 5. Error Handling Improvements

### 5.1 Silent Skip of Unknown Names in Deps [P1]

**Location:** `function.py:400-408`

**Problem:**
```python
if value is None:
    # Not in globals - could be a builtin or unresolved
    # TODO: Add builtin support
    continue
```

Typos in variable names are silently skipped, leading to confusing "Unbound name" errors later.

**Proposed Solution:**
```python
import builtins as py_builtins

PYTHON_BUILTINS = set(dir(py_builtins))

for name in all_names:
    value = effective_globals.get(name)

    if value is None:
        # Check if it's a known builtin that we handle
        if name in BUILTINS:  # Our transpiler builtins
            continue
        # Check if it's a Python builtin we don't handle
        if name in PYTHON_BUILTINS:
            continue  # Will fail at transpile time with clear message
        # Unknown name - likely a typo
        raise TranspileError(
            f"Unknown name '{name}' in function. "
            f"Did you forget to import it or define it?"
        )
```

---

### 5.2 Add Node Context to More Errors [P2]

**Location:** Various in `builtins.py`, `transpiler.py`

**Problem:** Many `TranspileError` raises don't include `node=` for source location.

**Proposed Solution:**

Add a helper that captures current node context:
```python
class Transpiler:
    _current_node: ast.AST | None = None

    def emit_expr(self, node: ast.expr | None) -> Expr:
        old_node = self._current_node
        self._current_node = node
        try:
            # ... existing code
        finally:
            self._current_node = old_node

    def error(self, message: str) -> TranspileError:
        return TranspileError(message, node=self._current_node)
```

Then use `raise ctx.error("message")` instead of `raise TranspileError("message")`.

---

### 5.3 Spread Props Error Message [P3]

**Location:** `transpiler.py:666-669`

**Problem:** Message says "not yet supported" but no tracking.

**Proposed Solution:**

Either implement it:
```python
if kw.arg is None:
    # **kwargs spread
    spread_expr = self.emit_expr(kw.value)
    # Handle in call processing
    has_spread = True
```

Or clarify the message:
```python
raise TranspileError(
    "Spread props (**kwargs) are not supported in function calls. "
    "Use explicit keyword arguments instead.",
    node=node
)
```

---

## 6. JSX/VDOM Issues

### 6.1 Non-String Keys Rejected [P2]

**Location:** `nodes.py:530-535`

**Problem:** React supports numeric keys but they're rejected.

**Proposed Solution:**
```python
def __init__(self, ...):
    # ...
    if self.key is not None:
        if isinstance(key, (int, float)):
            self.key = str(key)
        elif isinstance(key, Literal) and isinstance(key.value, (int, float)):
            self.key = str(key.value)
        elif not (isinstance(key, str) or (isinstance(key, Literal) and isinstance(key.value, str))):
            raise ValueError(f"Key must be string or number, got {type(key)}")
```

---

### 6.2 VDOM `else_` Key Naming [P3]

**Location:** `vdom.py:102-107`

**Problem:** TypedDict uses `else_` to avoid Python keyword, but this must be handled consistently.

**Proposed Solution:**

Document the mapping clearly and ensure serialization/deserialization handles it:
```python
class TernaryExpr(TypedDict):
    """Ternary expression.

    Note: Uses 'else_' in Python, serializes to 'else' in JSON.
    Client code should access the 'else' key.
    """
    t: Literal["ternary"]
    cond: VDOMExpr
    then: VDOMExpr
    else_: VDOMExpr

# Add custom serialization if needed:
def serialize_ternary(expr: TernaryExpr) -> dict:
    return {
        "t": "ternary",
        "cond": expr["cond"],
        "then": expr["then"],
        "else": expr["else_"],  # Rename on serialization
    }
```

---

### 6.3 Missing `Spread` in VDOMExpr Types [P2]

**Location:** `vdom.py:132-148`

**Problem:** `Spread` expression type missing from the union.

**Proposed Solution:**
```python
class SpreadExpr(TypedDict):
    t: Literal["spread"]
    expr: VDOMExpr

VDOMExpr: TypeAlias = (
    RegistryRef
    | IdentifierExpr
    | LiteralExpr
    | UndefinedExpr
    | ArrayExpr
    | ObjectExpr
    | MemberExpr
    | SubscriptExpr
    | CallExpr
    | UnaryExpr
    | BinaryExpr
    | TernaryExpr
    | TemplateExpr
    | ArrowExpr
    | NewExpr
    | SpreadExpr  # Add this
)
```

---

## 7. Import System Issues

### 7.1 Relative Path Resolution Fragile [P2]

**Location:** `imports.py:30-42`

**Problem:** `caller_file(depth=2)` assumes fixed call stack depth.

**Proposed Solution:**
```python
def caller_file(depth: int = 2, *, fallback: Path | None = None) -> Path:
    """Get the file path of the caller.

    Args:
        depth: Stack frames to skip (2 = caller of caller)
        fallback: Path to use if detection fails

    Raises:
        RuntimeError: If detection fails and no fallback provided
    """
    frame = inspect.currentframe()
    try:
        for _ in range(depth):
            if frame is None:
                if fallback:
                    return fallback
                raise RuntimeError("Could not determine caller file")
            frame = frame.f_back
        if frame is None:
            if fallback:
                return fallback
            raise RuntimeError("Could not determine caller file")
        return Path(frame.f_code.co_filename)
    finally:
        del frame

# Alternative: Allow explicit base path
class Import(Expr):
    def __init__(
        self,
        name: str,
        src: str,
        *,
        base_path: Path | None = None,  # Explicit base for relative resolution
        # ... other args
    ):
        if is_relative_path(src):
            if base_path:
                caller = base_path
            else:
                caller = caller_file(depth=_caller_depth)
```

---

### 7.2 Different Paths for Same File [P2]

**Location:** `imports.py:221-253`

**Problem:** `./utils.ts` and `./utils` can resolve to same file but get different registry keys.

**Proposed Solution:**
```python
def __init__(self, ...):
    # ... existing resolution ...

    # Normalize the source path for deduplication
    if source_path is not None:
        # Use resolved absolute path as canonical form
        canonical_src = str(source_path)
    else:
        canonical_src = import_src

    # Use canonical path for registry key
    if kind == "named":
        key: _ImportKey = (name, canonical_src, "named")
    else:
        key = ("", canonical_src, kind)
```

---

## 8. Miscellaneous Issues

### 8.1 Temp Variable Name Collision [P2]

**Location:** `transpiler.py:111-117`

**Problem:** Only checks args and deps, not locals declared inside function.

**Proposed Solution:**
```python
def init_temp_counter(self) -> None:
    """Initialize temp counter to avoid collisions."""
    # Collect all names from the function body
    all_names = set(self.args) | set(self.deps.keys())

    # Also scan function body for local assignments
    for node in ast.walk(self.fndef):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            all_names.add(node.id)
        elif isinstance(node, ast.arg):
            all_names.add(node.arg)

    counter = 0
    while f"$tmp{counter}" in all_names:
        counter += 1
    self._temp_counter = counter
```

---

### 8.2 `render()` Method Unimplemented [P3]

**Location:** `nodes.py:129-137`

**Problem:** Base class declares `render()` but no subclass implements it.

**Proposed Solution:**

Either remove the method (if unused) or implement for serializable nodes:
```python
# In Literal:
def render(self) -> dict[str, Any]:
    return {"t": "lit", "value": self.value}

# In Identifier:
def render(self) -> dict[str, Any]:
    return {"t": "id", "name": self.name}

# In Binary:
def render(self) -> dict[str, Any]:
    return {
        "t": "binary",
        "op": self.op,
        "left": self.left.render(),
        "right": self.right.render(),
    }

# etc.
```

---

### 8.3 Bitwise Operator Inconsistency [P3]

**Location:** `transpiler.py:45-67` vs `nodes.py:186-204`

**Problem:** `Expr.__and__` maps `&` to `&&`, but transpiler doesn't support bitwise `&`.

**Proposed Solution:**

Option A: Add bitwise operators to transpiler
```python
ALLOWED_BINOPS = {
    # ... existing ...
    ast.BitAnd: "&",
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.LShift: "<<",
    ast.RShift: ">>",
}

ALLOWED_UNOPS = {
    # ... existing ...
    ast.Invert: "~",
}
```

Option B: Change Expr dunders to use bitwise (breaking change)
```python
def __and__(self, other: object) -> "Binary":
    return Binary(self, "&", Expr.of(other))  # Bitwise AND
```

**Recommendation:** Option A - add bitwise support to transpiler for consistency.

---

## Implementation Status

### User questions
- **Q:** How should we fix `list.remove()` which silently removes the LAST element when value not found (because `indexOf` returns -1)?  
  **A:** Throw error

- **Q:** How should we handle the center alignment format spec bug where `expr.length` is used on non-string values?  
  **A:** Convert to String first

- **Q:** How should we address the non-thread-safe global registries (`FUNCTION_CACHE`, `EXPR_REGISTRY`, etc)?  
  **A:** Skip. The registries should only be populated during App definition, which is single-threaded and happens once on startup.

- **Q:** Should we add support for floor division (`//`) operator?  
  **A:** Yes, Math.floor

- **Q:** How should we fix `str.split()` without args? Python splits on whitespace and removes empties, JS returns whole string.  
  **A:** Fix with regex

- **Q:** Should we add try/except/raise exception handling support?  
  **A:** Yes, full support

- **Q:** How should unknown names in dependency analysis be handled? Currently silently skipped, causing confusing errors later.  
  **A:** Skip fix

- **Q:** Should we implement the missing format spec features (thousand separators, `%', n, c, g/G`)?  
  **A:** Yes, all

- **Q:** Should we add support for the walrus operator (`:=`) assignment expressions?  
  **A:** Skip

- **Q:** Should we add support for slice with step (e.g., `x[::2]`, `x[::-1]`)?  
  **A:** Skip

- **Q:** Should we add support for bitwise operators (`&`, `|`, `^`, `~`, `<<`, `>>`)?  
  **A:** Yes

- **Q:** Should we support numeric keys in JSX elements? Currently only strings allowed.  
  **A:** Support arbitrary expression keys in transpilation and restrict to only strings or numerics during rendering
