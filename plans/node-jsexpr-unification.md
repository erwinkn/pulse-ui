# Implementation Plan: Unify Node and JSExpr

## Overview

Make `Node` extend `JSExpr` to unify the VDOM and JSX representations. This eliminates **6 redundant types** (`JSXCallExpr`, `ReactComponentCallExpr`, `JSXElement`, `JSXFragment`, `JSXProp`, `JSXSpreadProp`) and enables client-side components (`ReactComponent`, `JsxFunction`) to work seamlessly in both VDOM and transpiled contexts.

### Goals

1. **Single element type**: `Node` represents all elements (HTML, components, fragments)
2. **Dual-mode operation**: `Node` works in VDOM context (rendered by Python) and JSX context (emitted as code)
3. **Enable `JsxFunction` in VDOM**: Transpiled components can accept Pulse components as children
4. **Reduce complexity**: Delete intermediate JSX AST types, inline formatting in `Node.emit()`

## Key Insight

`Node` and `JSXCallExpr` represent the same structure:

| Property | Node                      | JSXCallExpr                                       |
| -------- | ------------------------- | ------------------------------------------------- |
| Tag      | `tag: str`                | `tag: str \| JSExpr`                              |
| Props    | `props: dict[str, Any]`   | `props: Sequence[JSXProp]`                        |
| Children | `children: list[Element]` | `children: Sequence[str \| JSExpr \| JSXElement]` |

The only difference is **interpretation context**:

- **VDOM**: Props are Python values, callbacks become `$cb`, JSExprs become `$js:...`
- **JSX**: Props are JSExprs, emitted as `{expr}` in JSX syntax

By making `Node` a `JSExpr`, we get:

1. A single element type that works in both contexts
2. Unified component factories (`ReactComponent`, `JsxFunction`) that return `Node`
3. Elimination of redundant call expression types

## The `$$` Convention

The `$$` prefix on tags is overloaded:

| Context            | Tag `"div"`           | Tag `"$$Button_1a2b"`                       |
| ------------------ | --------------------- | ------------------------------------------- |
| **VDOM rendering** | Built-in HTML element | Client looks up `get_object('Button_1a2b')` |
| **JSX emit**       | `<div>`               | `<Button_1a2b>` (identifier reference)      |

This convention already exists in `ReactComponent`. We just need `Node.emit()` to respect it.

---

## Phase 1: Make Node a JSExpr

### Step 1.1: Add JSExpr import to vdom.py

```python
# packages/pulse/python/src/pulse/vdom.py

from pulse.transpiler.nodes import JSExpr
```

Note: This creates a dependency from `vdom.py` to `transpiler/nodes.py`. This is acceptable because `JSExpr` is a foundational type.

### Step 1.2: Make Node extend JSExpr

```python
@final
class Node(JSExpr):
    __slots__ = (
        "tag",
        "props",
        "children",
        "allow_children",
        "key",
    )

    # Existing fields unchanged
    # NOTE: tag="" represents a fragment (<>...</>)
    tag: str
    props: dict[str, Any] | None
    children: list[Element] | None
    allow_children: bool
    key: str | None
```

### Step 1.3: Implement Node.emit()

`Node.emit()` produces JSX directly, eliminating the need for `JSXElement`:

```python
# Class variable
is_jsx: ClassVar[bool] = True
is_primary: ClassVar[bool] = True

@override
def emit(self) -> str:
    """Emit as JSX.

    Props and children must be JSExpr-compatible (primitives or JSExpr).
    Python callables will raise TypeError.

    Tag conventions:
    - "" (empty): Fragment → <>{children}</>
    - "div", "span", etc.: HTML element → <div>{children}</div>
    - "$$ComponentId": Client component → <ComponentId>{children}</ComponentId>
    """
    from pulse.transpiler.context import is_interpreted_mode
    from pulse.transpiler.nodes import JSExpr, JSSpread, JSString

    if is_interpreted_mode():
        raise ValueError(
            "Node cannot be emitted in interpreted mode. "
            "Use standard VDOM rendering instead."
        )

    # Fragment: empty tag
    if not self.tag:
        children_code = self._emit_children()
        return f"<>{children_code}</>" if children_code else "<></>"

    # Resolve tag string
    if self.tag.startswith("$$"):
        # Client component: $$Button_1a2b → Button_1a2b
        tag_code = self.tag[2:]
    else:
        # HTML element: "div" → "div"
        tag_code = self.tag

    # Build props string
    props_code = self._emit_props()

    # Build children
    children_code = self._emit_children()

    # Self-closing if no children
    if not children_code:
        if props_code:
            return f"<{tag_code} {props_code} />"
        return f"<{tag_code} />"

    # Open/close tags
    open_tag = f"<{tag_code} {props_code}>" if props_code else f"<{tag_code}>"
    return f"{open_tag}{children_code}</{tag_code}>"

def _emit_props(self) -> str:
    """Emit props as JSX attributes."""
    from pulse.transpiler.nodes import JSExpr, JSSpread, JSString

    if not self.props:
        return ""

    parts: list[str] = []
    for key, value in self.props.items():
        if isinstance(value, JSSpread):
            # Spread prop: {...expr}
            parts.append(f"{{...{value.expr.emit()}}}")
        elif isinstance(value, JSExpr):
            # JSExpr prop: name={expr}
            if isinstance(value, JSString):
                # String literal: name="value"
                parts.append(f'{key}={value.emit()}')
            else:
                parts.append(f"{key}={{{value.emit()}}}")
        else:
            # Primitive: convert via JSExpr.of()
            expr = JSExpr.of(value)
            if isinstance(expr, JSString):
                parts.append(f'{key}={expr.emit()}')
            else:
                parts.append(f"{key}={{{expr.emit()}}}")

    return " ".join(parts)

def _emit_children(self) -> str:
    """Emit children as JSX content."""
    from pulse.transpiler.nodes import JSExpr, JSString

    if not self.children:
        return ""

    parts: list[str] = []
    for child in self.children:
        if isinstance(child, str):
            # Raw text - escape for JSX
            parts.append(_escape_jsx_text(child))
        elif isinstance(child, Node):
            # Nested Node - recursive emit
            parts.append(child.emit())
        elif isinstance(child, JSExpr):
            if child.is_jsx:
                # JSX expression (including other Nodes) - emit directly
                parts.append(child.emit())
            elif isinstance(child, JSString):
                # String literal - unwrap
                parts.append(_escape_jsx_text(child.value))
            else:
                # Other expression - wrap in {}
                parts.append(f"{{{child.emit()}}}")
        elif isinstance(child, (int, float, bool)) or child is None:
            expr = JSExpr.of(child)
            parts.append(f"{{{expr.emit()}}}")
        else:
            raise TypeError(
                f"Cannot emit {type(child).__name__} as JSX child. "
                "Only Node, JSExpr, str, and primitives can be emitted."
            )

    return "".join(parts)


def _escape_jsx_text(text: str) -> str:
    """Escape text for JSX content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
```

### Step 1.4: Add emit_call and emit_subscript to Node

For consistency with other JSExprs:

```python
@override
def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
    """Calling a Node is an error - it's already constructed."""
    raise JSCompilationError(
        f"Cannot call Node <{self.tag}> - use subscript for children: "
        f"Node(...)[children]"
    )

@override
def emit_subscript(self, indices: list[Any]) -> JSExpr:
    """Handle Node[children] - add children to this node."""
    if self.children:
        raise JSCompilationError(
            f"<{self.tag}> already has children. "
            "Use either positional args or subscript for children, not both."
        )
    return Node(
        tag=self.tag,
        props=self.props,
        children=list(indices),
        key=self.key,
        allow_children=self.allow_children,
    )
```

---

## Phase 2: Update Transpiler to Use Node

### Step 2.1: Update PyTags to return Node

**File**: `packages/pulse/python/src/pulse/transpiler/modules/tags.py`

```python
def _create_tag_function(tag_name: str):
    """Create a tag function that returns Node when called."""

    @staticmethod
    def tag_func(*args: Any, **kwargs: Any) -> Node:
        """Tag function that creates Node with props and children."""
        from pulse.vdom import Node

        # Handle key specially
        key = kwargs.pop("key", None)

        # Props stay as-is (can be JSExpr or primitive)
        props = dict(kwargs) if kwargs else None

        # Children from positional args
        children = list(args) if args else None

        return Node(
            tag=tag_name,
            props=props,
            children=children,
            key=key,
        )

    return tag_func
```

### Step 2.2: Update fragment handling

Fragments become `Node(tag="")`:

```python
@staticmethod
def fragment(*args: Any, **kwargs: Any) -> Node:
    """Fragment - Node with empty tag."""
    from pulse.vdom import Node

    if kwargs:
        raise JSCompilationError("React fragments cannot have props")

    return Node(
        tag="",  # Empty tag = fragment
        props=None,
        children=list(args) if args else None,
    )
```

This unifies fragments with regular nodes. `Node.emit()` handles `tag=""` by producing `<>...</>`.

### Step 2.3: Update convert_jsx_child

**File**: `packages/pulse/python/src/pulse/transpiler/jsx.py`

```python
def convert_jsx_child(item: Any) -> JSExpr | JSXElement | str:
    """Convert a single child item for JSX."""
    from pulse.vdom import Node

    # Node is now a JSExpr - return as-is (will emit recursively)
    if isinstance(item, Node):
        return item

    expr = JSExpr.of(item) if not isinstance(item, JSExpr) else item
    if isinstance(expr, JSSpread):
        return expr.expr
    if isinstance(expr, JSString):
        return expr.value
    return expr
```

---

## Phase 3: Eliminate Redundant Types

### Step 3.1: Remove JSXCallExpr

**File**: `packages/pulse/python/src/pulse/transpiler/jsx.py`

Delete the `JSXCallExpr` class entirely. All usages will be replaced with `Node`.

### Step 3.2: Remove ReactComponentCallExpr

**File**: `packages/pulse/python/src/pulse/react_component.py`

Delete the `ReactComponentCallExpr` class.

### Step 3.3: Update ReactComponent.emit_call

```python
@override
def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
    """Handle Component(props...) -> Node for JSX emission."""
    from pulse.vdom import Node

    key = kwargs.pop("key", None)
    props = dict(kwargs) if kwargs else None
    children = list(args) if args else None

    return Node(
        tag=f"$${self.expr}",
        props=props,
        children=children,
        key=key,
    )
```

### Step 3.4: Update Import.emit_call (jsx=True case)

**File**: `packages/pulse/python/src/pulse/transpiler/imports.py`

```python
@override
def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
    """Handle Import calls - Node if jsx=True, regular call otherwise."""
    if not self.jsx:
        if kwargs:
            raise JSCompilationError(
                "Keyword arguments not supported in default function call"
            )
        return JSCall(self, [JSExpr.of(a) for a in args])

    # JSX mode: return Node
    from pulse.vdom import Node

    key = kwargs.pop("key", None)
    props = dict(kwargs) if kwargs else None
    children = list(args) if args else None

    return Node(
        tag=f"$${self.js_name}",
        props=props,
        children=children,
        key=key,
    )
```

### Step 3.5: Update JsxFunction.emit_call

**File**: `packages/pulse/python/src/pulse/transpiler/function.py`

```python
@override
def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
    """Handle JSX-style calls: return Node."""
    from pulse.vdom import Node

    key = kwargs.pop("key", None)
    props = dict(kwargs) if kwargs else None
    children = list(args) if args else None

    return Node(
        tag=f"$${self.js_name}",
        props=props,
        children=children,
        key=key,
    )
```

---

## Phase 4: Enable JsxFunction in VDOM Context

### Step 4.1: Add **call** to JsxFunction

**File**: `packages/pulse/python/src/pulse/transpiler/function.py`

```python
class JsxFunction(JSExpr, Generic[P, R]):
    # ... existing code ...

    @override
    def __call__(self, *children: Any, **props: Any) -> Node:
        """Create a VDOM node for interpreted mode.

        Children passed here can be Pulse components - they'll be
        rendered by the Python renderer before being sent to the client.
        """
        from pulse.vdom import Node

        key = props.pop("key", None)
        if key is not None and not isinstance(key, str):
            raise ValueError("key must be a string or None")

        return Node(
            tag=f"$${self.js_name}",
            key=key,
            props=props or None,
            children=list(children) if children else None,
        )
```

### Step 4.2: Track JsxFunction in component registry (optional)

For codegen to know about these components, we may want to track them:

```python
# In function.py
from pulse.react_component import COMPONENT_REGISTRY

class JsxFunction(JSExpr, Generic[P, R]):
    def __init__(self, fn: Callable[P, Any]) -> None:
        # ... existing init ...

        # Register with component registry for codegen visibility
        # (This is optional - depends on codegen requirements)
        # COMPONENT_REGISTRY.get().add_jsx_function(self)
```

Alternatively, codegen can collect from `JSX_FUNCTION_CACHE` directly.

---

## Phase 5: Update Tests

### Step 5.1: Update transpiler tests

Tests that expect `JSXCallExpr` should now expect `Node`:

```python
# Before
assert isinstance(result, JSXCallExpr)
assert result.tag == "div"

# After
assert isinstance(result, Node)
assert result.tag == "div"
```

### Step 5.2: Add Node.emit() tests

```python
def test_node_emit_html():
    node = Node(tag="div", props={"className": "foo"}, children=["Hello"])
    assert node.emit() == '<div className="foo">Hello</div>'

def test_node_emit_component():
    node = Node(tag="$$Button_1a2b", props={"variant": "primary"})
    assert node.emit() == '<Button_1a2b variant="primary" />'

def test_node_emit_nested():
    node = Node(
        tag="div",
        children=[
            Node(tag="span", children=["Hello"]),
            Node(tag="span", children=["World"]),
        ]
    )
    assert node.emit() == '<div><span>Hello</span><span>World</span></div>'

def test_node_emit_with_jsexpr():
    from pulse.transpiler.nodes import JSIdentifier
    node = Node(
        tag="div",
        props={"onClick": JSIdentifier("handleClick")},
    )
    assert node.emit() == '<div onClick={handleClick} />'

def test_node_emit_fails_on_callback():
    node = Node(tag="div", props={"onClick": lambda: None})
    with pytest.raises(TypeError):
        node.emit()

def test_node_emit_fragment():
    node = Node(tag="", children=["Hello", "World"])
    assert node.emit() == "<>HelloWorld</>"

def test_node_emit_fragment_empty():
    node = Node(tag="")
    assert node.emit() == "<></>"

def test_node_emit_fragment_with_nodes():
    node = Node(
        tag="",
        children=[
            Node(tag="span", children=["A"]),
            Node(tag="span", children=["B"]),
        ]
    )
    assert node.emit() == "<><span>A</span><span>B</span></>"

def test_node_emit_spread_props():
    from pulse.transpiler.nodes import JSIdentifier, JSSpread
    node = Node(
        tag="div",
        props={
            "className": "foo",
            "spread": JSSpread(JSIdentifier("restProps")),
        }
    )
    assert 'className="foo"' in node.emit()
    assert "{...restProps}" in node.emit()
```

### Step 5.3: Add JsxFunction VDOM tests

```python
def test_jsx_function_returns_node():
    @javascript(component=True)
    def MyCard(title: str):
        return div()[title]

    # In VDOM context
    result = MyCard(title="Hello")

    assert isinstance(result, Node)
    assert result.tag == f"$$MyCard_{MyCard.id}"
    assert result.props == {"title": "Hello"}

def test_jsx_function_with_pulse_children():
    @javascript(component=True)
    def Card():
        return div(className="card")[js.children]

    @component
    def Counter():
        count = use_state(0)
        return div()[str(count.value)]

    # JsxFunction can have Pulse component children
    result = Card()[Counter()]

    assert isinstance(result, Node)
    assert len(result.children) == 1
    assert isinstance(result.children[0], ComponentNode)
```

---

## Phase 6: Clean Up Imports

### Step 6.1: Update **init**.py exports

**File**: `packages/pulse/python/src/pulse/transpiler/__init__.py`

Remove exports of deleted types:

```python
# Remove these:
# from pulse.transpiler.jsx import JSXCallExpr as JSXCallExpr

# Keep:
from pulse.transpiler.nodes import JSXElement as JSXElement
```

### Step 6.2: Update imports in other files

Search and replace:

- `from pulse.transpiler.jsx import JSXCallExpr` → remove or update
- `from pulse.react_component import ReactComponentCallExpr` → remove

---

## Phase 7: Eliminate JSXElement and JSXFragment

With `Node.emit()` handling all JSX formatting directly, we can delete the intermediate types.

### Step 7.1: Delete JSXElement

**File**: `packages/pulse/python/src/pulse/transpiler/nodes.py`

Delete the `JSXElement` class (~40 lines). All its functionality is now in `Node.emit()`.

### Step 7.2: Delete JSXFragment

**File**: `packages/pulse/python/src/pulse/transpiler/nodes.py`

Delete the `JSXFragment` class (~25 lines). Fragments are now `Node(tag="")`.

### Step 7.3: Keep JSXProp and JSXSpreadProp (optional)

These are small helper classes for prop formatting. Options:

**Option A: Delete them** - inline the formatting in `Node._emit_props()` (already done in Step 1.3)

**Option B: Keep them** - useful if other code needs to construct props programmatically

Recommendation: **Delete them** since `Node._emit_props()` handles everything.

### Step 7.4: Update type hints

Any code using `JSXElement` or `JSXFragment` type hints should use `Node` instead:

```python
# Before
def convert_jsx_child(item: Any) -> JSExpr | JSXElement | str:

# After
def convert_jsx_child(item: Any) -> JSExpr | str:
# (Node is a JSExpr, so JSExpr covers it)
```

### Step 7.5: Update exports

**File**: `packages/pulse/python/src/pulse/transpiler/__init__.py`

```python
# Remove these exports:
# from pulse.transpiler.nodes import JSXElement as JSXElement
# from pulse.transpiler.nodes import JSXFragment as JSXFragment
# from pulse.transpiler.nodes import JSXProp as JSXProp
# from pulse.transpiler.nodes import JSXSpreadProp as JSXSpreadProp
```

---

## Implementation Checklist

### Files to Modify

1. **`packages/pulse/python/src/pulse/vdom.py`**
   - Add: `JSExpr` import
   - Change: `Node` extends `JSExpr`
   - Add: `Node.emit()`, `Node._emit_props()`, `Node._emit_children()`
   - Add: `Node.emit_call()`, `Node.emit_subscript()`
   - Add: `_escape_jsx_text()` helper
   - Add: `is_jsx = True`, `is_primary = True` class variables

2. **`packages/pulse/python/src/pulse/transpiler/modules/tags.py`**
   - Change: Tag functions return `Node` instead of `JSXCallExpr`
   - Change: `fragment()` returns `Node(tag="")` instead of `JSXFragment`

3. **`packages/pulse/python/src/pulse/transpiler/jsx.py`**
   - Delete: `JSXCallExpr` class
   - Update: `convert_jsx_child()` to handle `Node`
   - Keep: `build_jsx_props()` (may still be useful for edge cases)

4. **`packages/pulse/python/src/pulse/transpiler/nodes.py`**
   - Delete: `JSXElement` class
   - Delete: `JSXFragment` class
   - Delete: `JSXProp` class
   - Delete: `JSXSpreadProp` class
   - Delete: `_escape_jsx_text()` helper (moved to vdom.py)
   - Delete: `_check_not_interpreted_mode()` helper (logic moved to Node.emit)

5. **`packages/pulse/python/src/pulse/react_component.py`**
   - Delete: `ReactComponentCallExpr` class
   - Delete: `_build_jsx_props()`, `_flatten_children()` (use shared versions)
   - Update: `ReactComponent.emit_call()` to return `Node`

6. **`packages/pulse/python/src/pulse/transpiler/imports.py`**
   - Update: `Import.emit_call()` for jsx=True case to return `Node`
   - Remove: import of `JSXCallExpr`

7. **`packages/pulse/python/src/pulse/transpiler/function.py`**
   - Add: `JsxFunction.__call__()` returning `Node`
   - Update: `JsxFunction.emit_call()` to return `Node`
   - Remove: import of `JSXCallExpr`

8. **`packages/pulse/python/src/pulse/transpiler/__init__.py`**
   - Remove: `JSXCallExpr` export
   - Remove: `JSXElement` export
   - Remove: `JSXFragment` export
   - Remove: `JSXProp` export
   - Remove: `JSXSpreadProp` export

### Test Files to Update

1. **`packages/pulse/python/tests/test_transpiler.py`** (if exists)
   - Update expectations from `JSXCallExpr` to `Node`
   - Update expectations from `JSXElement` to `Node`
   - Update expectations from `JSXFragment` to `Node(tag="")`

2. **`packages/pulse/python/tests/test_react.py`**
   - Update expectations from `ReactComponentCallExpr` to `Node`
   - Add tests for `ReactComponent.emit_call()` returning `Node`

3. **`packages/pulse/python/tests/test_nodes.py`** (if exists)
   - Remove tests for `JSXElement`, `JSXFragment`, `JSXProp`, `JSXSpreadProp`
   - Or update to test equivalent `Node` functionality

4. **New test file or section for `Node.emit()`**
   - Test HTML element emission
   - Test component emission ($$-prefixed tags)
   - Test fragment emission (empty tag)
   - Test nested Node emission
   - Test prop formatting (primitives, JSExpr, spread)
   - Test error cases (Python callables, interpreted mode)

---

## Migration Notes

### Behavioral Changes

1. **`Node` is now a `JSExpr`**
   - Can be used anywhere a JSExpr is expected
   - Has `emit()` method that produces JSX

2. **Component factories return `Node`**
   - `ReactComponent.__call__()` already returns `Node` (unchanged)
   - `ReactComponent.emit_call()` now returns `Node` (was `ReactComponentCallExpr`)
   - `JsxFunction.__call__()` now returns `Node` (was not defined)
   - `JsxFunction.emit_call()` now returns `Node` (was `JSXCallExpr`)

3. **Transpiler tag functions return `Node`**
   - `PyTags.div()` etc. now return `Node` (was `JSXCallExpr`)

### Breaking Changes

1. **`JSXCallExpr` removed** - Any code checking `isinstance(x, JSXCallExpr)` must change to `isinstance(x, Node)`

2. **`ReactComponentCallExpr` removed** - Same as above

3. **`JSXElement` removed** - Use `Node` instead. `Node.emit()` produces the same JSX output.

4. **`JSXFragment` removed** - Use `Node(tag="")` instead. Empty tag emits as `<>...</>`.

5. **`JSXProp` / `JSXSpreadProp` removed** - Props are now `dict[str, Any]` on Node, formatted inline by `emit()`.

6. **`Node.emit()` added** - Calling `emit()` on a Node with Python callables in props will raise `TypeError`. Calling in interpreted mode will raise `ValueError`.

---

## Future Considerations

### Fragment in VDOM Context

Fragments (`Node(tag="")`) work in JSX emit context. In VDOM context, the renderer could:

- Flatten fragment children into parent (current behavior for generators)
- Or render as a special fragment marker if needed by client

For now, fragments are primarily useful in transpiled code.

### ComponentNode as JSExpr?

`ComponentNode` represents a Pulse component instance (server-side, with hooks/state). It's fundamentally different from `Node`:

- `Node` = element description (can be VDOM or JSX)
- `ComponentNode` = component instance (server-only, renders to produce Element)

`ComponentNode` should NOT become a JSExpr because it cannot be emitted to JS - it has Python state.

### Render Props

Nodes used as render props (VDOM in props) will work correctly because the renderer already handles `Node` in props. The `emit()` path is separate and only used during transpilation.

---

## Dependencies

```
JSExpr (transpiler/nodes.py)
   ^
   |
   +-- Node (vdom.py) ←── NEW: extends JSExpr
   |      |
   |      +-- emit() → JSX string (direct, no intermediate types)
   |      +-- tag="" → fragment (<>...</>)
   |      +-- tag="$$id" → component reference
   |
   +-- Import (transpiler/imports.py)
   |      |
   |      +-- emit_call(jsx=True) → Node ←── CHANGED
   |
   +-- ReactComponent (react_component.py)
   |      |
   |      +-- __call__() → Node (unchanged)
   |      +-- emit_call() → Node ←── CHANGED (was ReactComponentCallExpr)
   |
   +-- JsxFunction (transpiler/function.py)
          |
          +-- __call__() → Node ←── NEW
          +-- emit_call() → Node ←── CHANGED (was JSXCallExpr)

DELETED:
   - JSXElement (transpiler/nodes.py)
   - JSXFragment (transpiler/nodes.py)
   - JSXProp (transpiler/nodes.py)
   - JSXSpreadProp (transpiler/nodes.py)
   - JSXCallExpr (transpiler/jsx.py)
   - ReactComponentCallExpr (react_component.py)
```

---

## Summary

This refactoring:

1. **Unifies representations** - `Node` is the single element type for both VDOM and JSX
2. **Enables `JsxFunction` in VDOM** - Can now accept Pulse components as children
3. **Eliminates 6 redundant types**:
   - `JSXCallExpr` - replaced by `Node`
   - `ReactComponentCallExpr` - replaced by `Node`
   - `JSXElement` - replaced by `Node.emit()`
   - `JSXFragment` - replaced by `Node(tag="")`
   - `JSXProp` - replaced by dict props + inline formatting
   - `JSXSpreadProp` - replaced by dict props + inline formatting
4. **Simplifies mental model** - One type (`Node`) for all elements
5. **Preserves compatibility** - VDOM rendering unchanged, JSX emission added
6. **Uses existing convention** - `$$id` prefix handles component lookup, `""` tag handles fragments

### Lines of Code Impact (Estimated)

| Type                   | Lines Deleted | Lines Added |
| ---------------------- | ------------- | ----------- |
| JSXElement             | ~40           | 0           |
| JSXFragment            | ~25           | 0           |
| JSXProp                | ~15           | 0           |
| JSXSpreadProp          | ~10           | 0           |
| JSXCallExpr            | ~40           | 0           |
| ReactComponentCallExpr | ~45           | 0           |
| Node.emit() additions  | 0             | ~80         |
| **Net**                | **~175**      | **~80**     |

**Net reduction: ~95 lines** while adding new functionality (JsxFunction in VDOM).
