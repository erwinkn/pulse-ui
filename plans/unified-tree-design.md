# Unified Tree Design

## Executive Summary

This document proposes a unified tree structure that serves both as the VDOM (for server-side rendering and client interpretation) and as a JS AST (for code generation). The key insight is that both representations describe the same thing: a tree of React elements with expressions—the only difference is whether they're interpreted at runtime or emitted as code.

## Current System Analysis

### Data Flow

```
Python Code
    │
    ├─[VDOM Path]────────────────────────────────────────────────────┐
    │   │                                                             │
    │   ▼                                                             │
    │  Node / ComponentNode                                           │
    │   │                                                             │
    │   ▼ (Renderer)                                                  │
    │  VDOMNode (dict)  ──────► JSON ──────► Client interprets        │
    │   • callbacks → "$cb"                                           │
    │   • JSExpr → "$js:code"                                         │
    │                                                                 │
    └─[Transpile Path]───────────────────────────────────────────────┐│
        │                                                             ││
        ▼                                                             ││
       JSXCallExpr / JSXElement / ReactComponentCallExpr              ││
        │                                                             ││
        ▼ (.emit())                                                   ││
       JavaScript code string ──────► route.tsx file                  ││
                                                                      ││
                                      (Both go to the same client)◄───┘│
```

### Redundant Types (6 total)

| Type                     | Purpose                          | Replacement           |
| ------------------------ | -------------------------------- | --------------------- |
| `JSXElement`             | Emit JSX from tag/props/children | `Node.emit()`         |
| `JSXFragment`            | Emit `<>...</>`                  | `Node(tag="").emit()` |
| `JSXCallExpr`            | Tag function call result         | `Node`                |
| `JSXProp`                | Format prop as `name={value}`    | Inline in emit        |
| `JSXSpreadProp`          | Format spread prop               | Inline in emit        |
| `ReactComponentCallExpr` | React component call result      | `Node`                |

### The Core Problem

The same conceptual element (e.g., `<Button onClick={handler}>Click</Button>`) has two completely separate representations depending on context:

1. **VDOM context**: `Node(tag="$$Button_1a2b", props={"onClick": handler}, children=["Click"])`
2. **Transpile context**: `JSXElement(tag="Button_1a2b", props=[JSXProp("onClick", handler)], children=["Click"])`

These are isomorphic structures with different Python types, requiring conversion logic and making it impossible to use transpiled components in VDOM context.

---

## Proposed Design

### Core Idea

A single tree type that can be:

1. **Rendered**: Recursively resolve Pulse components, output tree the client interprets
2. **Transpiled**: Recursively emit as JS/JSX code

### Node Types

```
UnifiedNode (abstract)
    │
    ├── ValueNode          # Wraps any non-primitive Python value
    │
    ├── ExprNode (abstract) # JS expressions
    │   ├── Identifier     # x, foo, myFunc
    │   ├── Literal        # 42, "hello", true, null
    │   ├── Array          # [a, b, c]
    │   ├── Object         # { key: value }
    │   ├── Member         # obj.prop
    │   ├── Subscript      # obj[key]
    │   ├── Call           # fn(args)
    │   ├── Unary          # -x, !x
    │   ├── Binary         # x + y
    │   ├── Ternary        # cond ? a : b
    │   ├── Arrow          # (x) => expr
    │   └── Template       # `hello ${name}`
    │
    ├── ElementNode        # React element (built-in tag, fragment, client component)
    │
    └── PulseNode          # Pulse server-side component
```

### Primitive Passthrough

Primitives (`str`, `int`, `float`, `bool`, `None`) are NOT wrapped—they flow through as-is. This is critical for:

- Zero overhead for the common case (most prop values are primitives)
- Natural Python code: `div(className="foo")` not `div(className=Str("foo"))`
- Serialization efficiency

### ValueNode: Lightweight Data Wrapper

```python
class ValueNode:
    """Wraps a non-primitive Python value for pass-through serialization.

    This allows arbitrary data structures (dicts, lists, dataclasses, etc.)
    to be passed as props without converting them into an AST. The serializer
    handles them directly.

    Use cases:
    - Complex prop values: options={{"a": 1, "b": 2}}
    - Server-computed data passed to client components
    - Any value that doesn't need expression semantics
    """
    __slots__ = ("value",)
    value: Any
```

The key insight: when you pass `data=my_dict` as a prop, you don't need to represent `my_dict` as a tree of `Object`/`Array` nodes—you just need to serialize it. `ValueNode` marks the boundary where the tree stops and serialization takes over.

### ElementNode: The Unified React Element

```python
class ElementNode:
    """A React element: built-in tag, fragment, or client component.

    Tag conventions:
    - "" (empty): Fragment
    - "div", "span", etc.: HTML element
    - "$$ComponentId": Client component (registered in JS registry)

    Props can contain:
    - Primitives (str, int, float, bool, None): serialized directly
    - ValueNode: serialized as data
    - ExprNode: rendered as $js:code or emitted as {expr}
    - ElementNode: render prop
    - Callbacks: rendered as $cb or emitted as inline handler

    Children can contain:
    - Primitives: text content
    - ElementNode: nested elements
    - ExprNode: dynamic content
    - PulseNode: server component (render only, not transpile)
    """
    __slots__ = ("tag", "props", "children", "key")

    tag: str
    props: dict[str, Any] | None  # Any = Primitive | ValueNode | ExprNode | ElementNode | Callable
    children: list[Child] | None  # Child = Primitive | ElementNode | ExprNode | PulseNode
    key: str | None
```

### PulseNode: Server-Side Component

```python
class PulseNode:
    """A Pulse server-side component instance.

    Unlike ElementNode, this represents a component with Python-side state
    and hooks. It can only appear in VDOM context (render path), never in
    transpiled code.

    During rendering, PulseNode is called and replaced by its returned tree.
    """
    __slots__ = ("fn", "args", "kwargs", "key", "hooks", "contents")

    fn: Callable[..., Child]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    key: str | None
    # Renderer state
    hooks: HookContext
    contents: Child | None
```

### ExprNode Hierarchy

```python
class ExprNode(ABC):
    """Base class for JS expressions."""

    @abstractmethod
    def emit(self) -> str:
        """Emit JavaScript code."""
        ...

    def render(self) -> str:
        """Render as $js:code for client-side evaluation."""
        return f"$js:{self.emit()}"

class Identifier(ExprNode):
    name: str

    def emit(self) -> str:
        return self.name

class Literal(ExprNode):
    """JS literal (number, string, boolean, null)."""
    value: int | float | str | bool | None

    def emit(self) -> str:
        if isinstance(self.value, str):
            return json.dumps(self.value)  # Proper escaping
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if self.value is None:
            return "null"
        return str(self.value)

class Array(ExprNode):
    elements: list[ExprNode]

    def emit(self) -> str:
        return f"[{', '.join(e.emit() for e in self.elements)}]"

class Object(ExprNode):
    props: list[tuple[str, ExprNode]]

    def emit(self) -> str:
        pairs = [f'"{k}": {v.emit()}' for k, v in self.props]
        return "{" + ", ".join(pairs) + "}"

class Member(ExprNode):
    obj: ExprNode
    prop: str

    def emit(self) -> str:
        return f"{self.obj.emit()}.{self.prop}"

class Call(ExprNode):
    callee: ExprNode
    args: list[ExprNode]

    def emit(self) -> str:
        args_code = ", ".join(a.emit() for a in self.args)
        return f"{self.callee.emit()}({args_code})"

class Binary(ExprNode):
    left: ExprNode
    op: str
    right: ExprNode

    def emit(self) -> str:
        return f"{self.left.emit()} {self.op} {self.right.emit()}"

# ... etc for Unary, Ternary, Arrow, Template
```

### ElementNode.emit() for JSX

```python
class ElementNode:
    def emit(self) -> str:
        """Emit as JSX code."""
        # Fragment
        if not self.tag:
            children_code = self._emit_children()
            return f"<>{children_code}</>" if children_code else "<></>"

        # Resolve tag
        tag_code = self.tag[2:] if self.tag.startswith("$$") else self.tag

        # Build props
        props_code = self._emit_props()

        # Build children
        children_code = self._emit_children()

        # Self-closing if no children
        if not children_code:
            if props_code:
                return f"<{tag_code} {props_code} />"
            return f"<{tag_code} />"

        open_tag = f"<{tag_code} {props_code}>" if props_code else f"<{tag_code}>"
        return f"{open_tag}{children_code}</{tag_code}>"

    def _emit_props(self) -> str:
        if not self.props:
            return ""

        parts = []
        for key, value in self.props.items():
            if isinstance(value, ExprNode):
                parts.append(f"{key}={{{value.emit()}}}")
            elif isinstance(value, str):
                parts.append(f'{key}="{_escape_attr(value)}"')
            elif isinstance(value, (int, float, bool)) or value is None:
                parts.append(f"{key}={{{Literal(value).emit()}}}")
            elif isinstance(value, ValueNode):
                # Emit serialized value
                parts.append(f"{key}={{{_emit_serialized(value.value)}}}")
            elif isinstance(value, ElementNode):
                # Render prop
                parts.append(f"{key}={{{value.emit()}}}")
            elif callable(value):
                raise TypeError("Cannot emit callable in transpile context")
            else:
                raise TypeError(f"Cannot emit {type(value)} as prop")

        return " ".join(parts)

    def _emit_children(self) -> str:
        if not self.children:
            return ""

        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(_escape_jsx_text(child))
            elif isinstance(child, ElementNode):
                parts.append(child.emit())
            elif isinstance(child, ExprNode):
                parts.append(f"{{{child.emit()}}}")
            elif isinstance(child, PulseNode):
                raise TypeError("PulseNode cannot be emitted - render first")
            elif isinstance(child, (int, float)):
                parts.append(f"{{{child}}}")
            elif child is None or isinstance(child, bool):
                pass  # React ignores None/bool children
            else:
                raise TypeError(f"Cannot emit {type(child)} as child")

        return "".join(parts)
```

---

## Rendering vs Transpilation

### Rendering (VDOM Path)

```python
def render(node: Child, path: str = "") -> tuple[VDOM, Child]:
    """Render a unified tree to VDOM.

    Returns (vdom, normalized) where:
    - vdom: JSON-serializable VDOM for the client
    - normalized: The tree with PulseNodes expanded
    """
    # Primitives pass through
    if node is None or isinstance(node, (str, int, float, bool)):
        return node, node

    # PulseNode: call and recurse into result
    if isinstance(node, PulseNode):
        with node.hooks:
            result = node.fn(*node.args, **node.kwargs)
        vdom, normalized = render(result, path)
        node.contents = normalized
        return vdom, node

    # ElementNode: render props and children
    if isinstance(node, ElementNode):
        vdom_node = {"tag": node.tag}
        if node.key:
            vdom_node["key"] = node.key

        # Render props
        vdom_props = {}
        for key, value in (node.props or {}).items():
            prop_path = f"{path}.{key}" if path else key
            vdom_props[key] = render_prop(value, prop_path)
        if vdom_props:
            vdom_node["props"] = vdom_props

        # Render children
        vdom_children = []
        for i, child in enumerate(node.children or []):
            child_path = f"{path}.{i}" if path else str(i)
            vdom_child, _ = render(child, child_path)
            vdom_children.append(vdom_child)
        if vdom_children:
            vdom_node["children"] = vdom_children

        return vdom_node, node

    # ExprNode: emit as $js:code
    if isinstance(node, ExprNode):
        return node.render(), node

    # ValueNode: serialize directly
    if isinstance(node, ValueNode):
        return serialize(node.value), node

    raise TypeError(f"Unknown node type: {type(node)}")


def render_prop(value: Any, path: str) -> Any:
    """Render a prop value to VDOM format."""
    # Primitives
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # Callbacks
    if callable(value):
        register_callback(path, value)
        return "$cb"

    # ExprNode
    if isinstance(value, ExprNode):
        register_jsexpr_path(path)
        return value.render()  # "$js:code"

    # ValueNode
    if isinstance(value, ValueNode):
        return serialize(value.value)

    # Render props (nested elements)
    if isinstance(value, (ElementNode, PulseNode)):
        register_render_prop(path)
        vdom, _ = render(value, path)
        return vdom

    # Plain data (dict, list, etc.)
    return serialize(value)
```

### Transpilation (Code Generation)

```python
def transpile(node: Child) -> str:
    """Transpile a unified tree to JavaScript code.

    PulseNode is not allowed - must render first.
    """
    if node is None:
        return "null"
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, str):
        return json.dumps(node)
    if isinstance(node, (int, float)):
        return str(node)

    if isinstance(node, ElementNode):
        return node.emit()

    if isinstance(node, ExprNode):
        return node.emit()

    if isinstance(node, ValueNode):
        return _emit_serialized(node.value)

    if isinstance(node, PulseNode):
        raise TypeError(
            f"Cannot transpile PulseNode '{node.fn.__name__}'. "
            "Server components must be rendered, not transpiled."
        )

    raise TypeError(f"Cannot transpile {type(node)}")
```

---

## Component Factories

### Tag Functions (div, span, etc.)

```python
def _create_tag_fn(tag: str):
    def tag_fn(*children: Child, **props: Any) -> ElementNode:
        return ElementNode(
            tag=tag,
            props=props or None,
            children=list(children) if children else None,
            key=props.pop("key", None),
        )
    return tag_fn

div = _create_tag_fn("div")
span = _create_tag_fn("span")
# ... etc
```

### Fragment

```python
def fragment(*children: Child) -> ElementNode:
    return ElementNode(tag="", props=None, children=list(children) if children else None)
```

### ReactComponent

```python
class ReactComponent(ExprNode):
    """A client-side React component (imported from npm package)."""

    import_: Import
    expr: str  # e.g., "Button_1a2b" or "AppShell_1a2b.Header"

    def emit(self) -> str:
        return self.expr

    def __call__(self, *children: Child, **props: Any) -> ElementNode:
        """Create an ElementNode when called."""
        key = props.pop("key", None)
        return ElementNode(
            tag=f"$${self.expr}",
            props=props or None,
            children=list(children) if children else None,
            key=key,
        )
```

### JsxFunction (Transpiled Component)

```python
class JsxFunction(ExprNode):
    """A transpiled component function."""

    fn: Callable[..., Child]
    js_name: str  # e.g., "MyCard_1a2b"

    def emit(self) -> str:
        if is_interpreted_mode():
            return f"get_object('{self.js_name}')"
        return self.js_name

    def __call__(self, *children: Child, **props: Any) -> ElementNode:
        """Create an ElementNode when called (for VDOM context)."""
        key = props.pop("key", None)
        return ElementNode(
            tag=f"$${self.js_name}",
            props=props or None,
            children=list(children) if children else None,
            key=key,
        )
```

Now `JsxFunction` can be used in VDOM context! Its children can include `PulseNode` instances, which get rendered before being sent to the client.

### Pulse Component

```python
class Component:
    """Factory for Pulse server-side components."""

    fn: Callable[..., Child]
    name: str

    def __call__(self, *children: Child, **props: Any) -> PulseNode:
        key = props.pop("key", None)
        return PulseNode(
            fn=self.fn,
            args=children,
            kwargs=props,
            key=key,
        )
```

---

## Serialization Strategy

The serializer handles `ValueNode` contents and any plain data in props/children:

```python
def serialize(value: Any) -> PlainJSON:
    """Serialize a Python value to JSON-compatible format.

    Special handling:
    - datetime → timestamp with metadata
    - set → array with metadata
    - circular refs → ref index with metadata
    - dataclasses → dict
    """
    # Existing serializer logic...
```

For transpilation, `ValueNode` needs to emit valid JS:

```python
def _emit_serialized(value: Any) -> str:
    """Emit a Python value as JavaScript literal.

    Used when ValueNode appears in transpiled code.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return f"[{', '.join(_emit_serialized(v) for v in value)}]"
    if isinstance(value, dict):
        pairs = [f"{json.dumps(k)}: {_emit_serialized(v)}" for k, v in value.items()]
        return "{" + ", ".join(pairs) + "}"
    if isinstance(value, datetime):
        return f'new Date({int(value.timestamp() * 1000)})'
    if isinstance(value, set):
        return f"new Set([{', '.join(_emit_serialized(v) for v in value)}])"

    raise TypeError(f"Cannot emit {type(value)} as JavaScript")
```

---

## Key Differences from Original Plan

| Aspect              | Original Plan         | This Design                    |
| ------------------- | --------------------- | ------------------------------ |
| Node extends JSExpr | Yes                   | No - separate hierarchies      |
| ValueNode           | Not explicit          | Explicit wrapper for data      |
| PulseNode           | ComponentNode         | Renamed, clearer purpose       |
| ExprNode            | Part of Node tree     | Separate hierarchy, composable |
| Circular refs       | Handled by serializer | Same, but clearer boundary     |

The separation of `ExprNode` from `ElementNode` is important:

- `ExprNode` is for JS expressions (can be emitted, can be used in props)
- `ElementNode` is for React elements (has tag/props/children structure)
- `PulseNode` is for server components (never transpiled)

---

## Open Questions and Edge Cases

### 1. ExprNode in Children

When an `ExprNode` appears as a child:

- **Render**: Output `$js:code` for client evaluation
- **Transpile**: Output `{code}` in JSX

But what if the expression returns a React element? The client needs to know to treat `$js:code` as something to evaluate and render, not as text.

**Proposed solution**: The client already handles `$js:` prefix for props. Extend to children with same semantics.

### 2. Callbacks in Transpiled Code

In VDOM context, callbacks become `$cb` and are registered server-side. In transpiled code, callbacks should be inline functions.

```python
# VDOM context
Button(onClick=lambda: print("hi"))
# Renders to: {"tag": "button", "props": {"onClick": "$cb"}}

# Transpile context
@javascript(component=True)
def MyButton():
    return Button(onClick=lambda: console.log("hi"))
# Emits: <Button onClick={() => console.log("hi")} />
```

**Proposed solution**: In transpile context, lambdas are transpiled to arrow functions. The existing transpiler already handles this.

### 3. Nested PulseNode in Transpiled Context

```python
@javascript(component=True)
def ClientCard():
    return Card()[
        Counter()  # PulseNode - ERROR in transpile!
    ]
```

This is invalid and should fail at transpile time with a clear error.

**Proposed solution**: `ElementNode.emit()` raises `TypeError` when it encounters a `PulseNode` child.

### 4. ReactComponent in Pulse Children

```python
@component
def Page():
    return div()[
        Button(variant="primary")["Click me"]  # ReactComponent
    ]
```

This works fine! `Button(...)` returns `ElementNode`, which renders to VDOM normally.

### 5. JsxFunction with Pulse Children

```python
@javascript(component=True)
def ClientLayout():
    return div(className="layout")[js.children]

@component
def Page():
    return ClientLayout()[
        Counter()  # PulseNode - should work!
    ]
```

Now this works! `ClientLayout()` returns `ElementNode`, which can have `PulseNode` children. During render, the `PulseNode` is expanded.

### 6. ValueNode Serialization Limits

`ValueNode` can wrap anything, but not everything is serializable:

- Functions → Error
- Classes → Error
- Modules → Error
- Circular refs → Handled by serializer

**Proposed solution**: The serializer already raises `TypeError` for unsupported types. `ValueNode` inherits this behavior.

### 7. Fragment Key

React fragments can't have keys in `<></>` syntax, but can with `<Fragment key="...">`.

```python
fragment(key="item-1")[child1, child2]  # How to handle?
```

**Proposed solution**: If `ElementNode` has `tag=""` and `key is not None`, emit `<Fragment key="...">` instead of `<>`.

### 8. Spread Props

```python
div(**some_dict)
```

Currently handled via `JSSpread`. In the unified design:

```python
class Spread(ExprNode):
    expr: ExprNode

    def emit(self) -> str:
        return f"...{self.expr.emit()}"
```

Props dict can contain `Spread` nodes, which emit as `{...expr}` in JSX.

---

## Fragile Edge Cases

### 1. Mixed Static/Dynamic Children

```python
div()[
    "Hello",           # Static string
    js.name,           # ExprNode
    Counter(),         # PulseNode (render only)
    Button()["Click"], # ElementNode
]
```

All these child types must be handled correctly in both render and transpile paths. The proposed design handles this, but it's a complex case to test thoroughly.

### 2. Render Props with Callbacks

```python
DataTable(
    rowRenderer=lambda row: div()[row["name"]]  # Callback returning ElementNode
)
```

In VDOM context, this becomes a render prop. The callback is registered, and when called, returns more VDOM. This works today but needs careful handling in the unified design.

### 3. ExprNode Identity

```python
x = js.some_value
div(a=x, b=x)  # Same ExprNode used twice
```

Both paths should handle this correctly—no special case needed since ExprNode is immutable.

### 4. Deeply Nested ValueNode

```python
div(data=ValueNode({
    "users": [
        {"name": "Alice", "avatar": {"url": "...", "size": 64}},
        # ... 1000 more
    ]
}))
```

For render: serialized efficiently  
For transpile: generates large inline JS object

**Concern**: Transpiled code could become very large. Consider a threshold or warning.

---

## Type Definitions

```python
# Core primitives
Primitive = str | int | float | bool | None

# Child can be any node type or primitive
Child = Primitive | ElementNode | ExprNode | PulseNode | ValueNode

# Props can contain various types
PropValue = Primitive | ValueNode | ExprNode | ElementNode | Callable[..., Any]
Props = dict[str, PropValue]

# VDOM output (JSON-serializable)
VDOM = Primitive | VDOMElement
VDOMElement = TypedDict("VDOMElement", {
    "tag": str,
    "key": NotRequired[str],
    "props": NotRequired[dict[str, Any]],
    "children": NotRequired[list[VDOM]],
})
```

---

## Migration Path

### Phase 1: Introduce New Types

- Add `ElementNode`, `ExprNode` hierarchy, `ValueNode`, `PulseNode`
- Keep existing types working

### Phase 2: Update Factories

- Tag functions return `ElementNode`
- `ReactComponent.__call__` returns `ElementNode`
- `JsxFunction.__call__` returns `ElementNode`
- `Component.__call__` returns `PulseNode`

### Phase 3: Update Renderer

- Handle new node types
- Remove handling of old types

### Phase 4: Update Transpiler

- `ElementNode.emit()` replaces `JSXElement.emit()`
- `JsxFunction.emit_call()` returns `ElementNode`
- Remove `JSXCallExpr`, `ReactComponentCallExpr`

### Phase 5: Delete Old Types

- `JSXElement`, `JSXFragment`, `JSXProp`, `JSXSpreadProp`
- `JSXCallExpr`, `ReactComponentCallExpr`
- Current `Node`, `ComponentNode` (replaced by `ElementNode`, `PulseNode`)

---

## Benefits

1. **Single mental model**: One tree structure, two interpretations
2. **JsxFunction in VDOM**: Transpiled components can wrap Pulse components
3. **~6 types eliminated**: Simpler codebase
4. **Clear boundaries**: ExprNode vs ElementNode vs PulseNode vs ValueNode
5. **Better error messages**: PulseNode in transpile context fails with clear error
6. **Efficient serialization**: ValueNode avoids AST overhead for data

## Risks

1. **Migration complexity**: Many files need updates
2. **Subtle behavior changes**: Props handling, child flattening
3. **Performance**: Need to benchmark render/transpile paths
4. **Type system complexity**: Union types for Child, PropValue

---

## Alternative Considered: Single Node Type

Your original message suggested a single data structure where primitive values pass through directly. I initially designed around that but realized there's a tension:

**Option A: Everything is a node (current proposal)**

```
ElementNode, ExprNode, PulseNode, ValueNode
```

- Pro: Clear type discrimination
- Pro: Explicit semantics for each case
- Con: More types to juggle

**Option B: Single "Tree" union + primitives**

```python
Tree = Primitive | dict[str, Any]  # Element/Expr/Pulse as dicts with "type" field
```

- Pro: Even simpler conceptually
- Pro: Closer to JSON structure
- Con: Loses type safety
- Con: Dict dispatch is slower than isinstance
- Con: Harder to add methods

**Option C: ExprNode IS the element type (your proposal hint)**

Make a single `Node` type that can be:

- A primitive (passthrough)
- An expression (unary, binary, etc.)
- A React element (tag + props + children)
- A Pulse component

```python
@dataclass
class Node:
    kind: Literal["element", "pulse", "expr", "value"]
    # For element
    tag: str | None = None
    props: dict[str, Any] | None = None
    children: list[Any] | None = None
    key: str | None = None
    # For pulse
    fn: Callable | None = None
    args: tuple | None = None
    kwargs: dict | None = None
    # For expr
    op: str | None = None  # "binary", "unary", "call", etc.
    operands: list[Any] | None = None
    # For value
    value: Any = None
```

- Pro: Single type
- Con: Mega-struct with many optional fields
- Con: Runtime checks needed for valid combinations
- Con: Loses compile-time type safety

**Decision**: The current proposal (Option A) is the right balance. The type hierarchy is shallow, each type has clear semantics, and Python's structural pattern matching makes dispatch clean.

---

## Deeper Dive: Why ValueNode?

Without `ValueNode`, when you write:

```python
div(style={"color": "red", "fontSize": 14})
```

You'd need to convert `{"color": "red", "fontSize": 14}` to:

```python
Object([
    ("color", Literal("red")),
    ("fontSize", Literal(14)),
])
```

This is wasteful because:

1. The dict is already a valid serializable structure
2. Creating AST nodes for data has overhead
3. You lose the ability to pass arbitrary Python data

With `ValueNode`:

```python
div(style=ValueNode({"color": "red", "fontSize": 14}))
```

But we can be smarter - the tag factory can auto-wrap:

```python
def div(**props):
    processed = {}
    for k, v in props.items():
        if isinstance(v, (ExprNode, ElementNode, PulseNode)):
            processed[k] = v
        elif callable(v):
            processed[k] = v  # Callback
        elif v is None or isinstance(v, (str, int, float, bool)):
            processed[k] = v  # Primitive
        else:
            processed[k] = ValueNode(v)  # Auto-wrap complex data
    return ElementNode(tag="div", props=processed, ...)
```

This makes the API seamless while maintaining the clear internal boundary.

---

## Comparison with Original Plan

Your original plan in `node-jsexpr-unification.md` proposed making `Node` extend `JSExpr`. This design is different:

| Aspect      | Original Plan           | This Design                                 |
| ----------- | ----------------------- | ------------------------------------------- |
| Inheritance | `Node(JSExpr)`          | Separate `ElementNode`, `ExprNode`          |
| Emit method | On Node                 | On ElementNode (for JSX), ExprNode (for JS) |
| Naming      | Keep Node/ComponentNode | Rename to ElementNode/PulseNode             |
| ValueNode   | Not in plan             | Explicit type for data boundaries           |

**Why the change?**

Making `Node` extend `JSExpr` creates a conceptual problem: an element is not really an expression. You can't do arithmetic on a `<div>`. The `emit()` method on a React element produces JSX, which is syntactically different from JS expressions.

The clean separation:

- `ExprNode.emit()` → JS expression: `x + 1`, `foo.bar()`, `obj.prop`
- `ElementNode.emit()` → JSX: `<div className="x">...</div>`

Both are "emittable" but into different syntactic categories.

---

## Implementation Sketch

### File Structure

```
pulse/
├── tree.py              # ElementNode, PulseNode, ValueNode, ExprNode hierarchy
├── expr/
│   ├── __init__.py      # Re-exports
│   ├── base.py          # ExprNode ABC
│   ├── literals.py      # Identifier, Literal
│   ├── operators.py     # Binary, Unary, Ternary
│   ├── access.py        # Member, Subscript, Call
│   └── compound.py      # Array, Object, Arrow, Template
├── render.py            # render() function
├── transpile.py         # transpile() function, emit logic
├── serialize.py         # Existing serializer (unchanged)
└── html/
    └── tags.py          # div, span, etc. returning ElementNode
```

### Key Classes (Minimal)

```python
# tree.py

from __future__ import annotations
from typing import Any, Callable, final

@final
class ElementNode:
    __slots__ = ("tag", "props", "children", "key")

    def __init__(
        self,
        tag: str,
        props: dict[str, Any] | None = None,
        children: list[Any] | None = None,
        key: str | None = None,
    ):
        self.tag = tag
        self.props = props
        self.children = children
        self.key = key

    def emit(self) -> str:
        """Emit as JSX."""
        from pulse.transpile import emit_element
        return emit_element(self)


@final
class PulseNode:
    __slots__ = ("fn", "args", "kwargs", "key", "hooks", "contents")

    def __init__(
        self,
        fn: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        key: str | None = None,
    ):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs or {}
        self.key = key
        self.hooks = HookContext()
        self.contents = None


@final
class ValueNode:
    __slots__ = ("value",)

    def __init__(self, value: Any):
        self.value = value
```

### Tag Factory

```python
# html/tags.py

from pulse.tree import ElementNode, ValueNode

def _wrap_prop(value: Any) -> Any:
    """Wrap non-primitive, non-node values in ValueNode."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (ElementNode, PulseNode, ExprNode)):
        return value
    if callable(value):
        return value
    return ValueNode(value)

def _create_tag(name: str):
    def tag(*children: Any, key: str | None = None, **props: Any) -> ElementNode:
        return ElementNode(
            tag=name,
            props={k: _wrap_prop(v) for k, v in props.items()} or None,
            children=list(children) if children else None,
            key=key,
        )
    return tag

div = _create_tag("div")
span = _create_tag("span")
# ... etc
```

### ExprNode Base

```python
# expr/base.py

from abc import ABC, abstractmethod

class ExprNode(ABC):
    __slots__ = ()

    @abstractmethod
    def emit(self) -> str:
        """Emit JavaScript code."""
        raise NotImplementedError

    def render(self) -> str:
        """Render for client-side evaluation."""
        return f"$js:{self.emit()}"

    # Operator overloading for natural syntax
    def __add__(self, other: Any) -> ExprNode:
        from pulse.expr.operators import Binary
        return Binary(self, "+", ExprNode.of(other))

    def __getattr__(self, name: str) -> ExprNode:
        from pulse.expr.access import Member
        return Member(self, name)

    def __call__(self, *args: Any, **kwargs: Any) -> ExprNode:
        from pulse.expr.access import Call
        # Can be overridden by subclasses (e.g., JsxFunction)
        return Call(self, [ExprNode.of(a) for a in args])

    @classmethod
    def of(cls, value: Any) -> ExprNode:
        """Convert Python value to ExprNode."""
        if isinstance(value, ExprNode):
            return value
        from pulse.expr.literals import Literal
        if value is None or isinstance(value, (str, int, float, bool)):
            return Literal(value)
        # ... handle list, dict, etc.
        raise TypeError(f"Cannot convert {type(value)} to ExprNode")
```

---

## Summary

The unified tree design achieves:

1. **Single conceptual model**: A tree of elements, expressions, and server components
2. **Two interpretations**: Render (→ VDOM) or Transpile (→ JS code)
3. **JsxFunction in VDOM**: The main unlock—transpiled components can wrap Pulse components
4. **Clear type boundaries**:
   - `ElementNode`: React element (client-rendered)
   - `PulseNode`: Server component (Python-rendered)
   - `ExprNode`: JS expression (evaluable or emittable)
   - `ValueNode`: Data boundary (serialized, not AST-ified)
5. **~6 types eliminated**: `JSXElement`, `JSXFragment`, `JSXProp`, `JSXSpreadProp`, `JSXCallExpr`, `ReactComponentCallExpr`
6. **Primitives pass through**: No wrapper overhead for strings, numbers, booleans

---

## Appendix: Name Choices

| Current         | Proposed      | Rationale                                      |
| --------------- | ------------- | ---------------------------------------------- |
| `Node`          | `ElementNode` | Clearer - it's a React element                 |
| `ComponentNode` | `PulseNode`   | Matches terminology (Pulse = server framework) |
| `JSExpr`        | `ExprNode`    | Consistent naming, clearer in unified context  |
| (new)           | `ValueNode`   | Explicit boundary for data serialization       |

The `$$` prefix convention remains for `ElementNode.tag` to indicate client-registered components.
