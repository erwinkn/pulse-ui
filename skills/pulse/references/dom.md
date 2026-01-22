# DOM Elements & Events

HTML/SVG elements and event handling.

## HTML Elements

All standard tags available as `ps.<tag>(*children, **props)`.

### Layout

| Element | Notes |
|---------|-------|
| div, span | Generic containers |
| section, article, aside | Semantic sections |
| header, footer, main, nav | Page structure |

### Text

| Element | Notes |
|---------|-------|
| h1–h6 | Headings |
| p, blockquote | Paragraphs |
| strong, em, small, mark | Inline formatting |
| code, pre | Code blocks |

### Lists

| Element | Key Props | Notes |
|---------|-----------|-------|
| ul, ol | start, type | Unordered/ordered lists |
| li | value | List item |
| dl, dt, dd | — | Definition list |

### Forms

| Element | Key Props | Notes |
|---------|-----------|-------|
| form | onSubmit, action, method | Container for inputs |
| input | value, onChange, type, placeholder, disabled | See Input Types |
| textarea | value, onChange, rows, cols | Multi-line text |
| select | value, onChange, multiple | Dropdown |
| option | value, selected, disabled | Select option |
| button | onClick, type, disabled | type: "button" / "submit" |
| label | htmlFor | Associate with input |
| fieldset | disabled | Group inputs |
| legend | — | Fieldset caption |

### Input Types

| Type | Extra Props | Notes |
|------|-------------|-------|
| text, password, email, search, tel, url | — | Text variants |
| number | min, max, step | Numeric input |
| checkbox | checked, onChange | Boolean toggle |
| radio | name, checked | Group by name |
| file | accept, multiple | accept=".pdf,.doc" |
| date, time, datetime-local | — | Date/time pickers |
| range | min, max | Slider |
| color | — | Color picker |
| hidden | value | Not displayed |

### Media

| Element | Key Props | Notes |
|---------|-----------|-------|
| img | src, alt, width, height, loading | loading="lazy" |
| video | src, controls, autoplay, muted | Container for source |
| audio | src, controls | Audio player |
| source | src, type | type="video/mp4" |
| picture | — | Responsive images |
| iframe | src, width, height | Embedded content |
| canvas | width, height | Drawing surface |

### Tables

| Element | Key Props | Notes |
|---------|-----------|-------|
| table | — | Container |
| thead, tbody, tfoot | — | Row groups |
| tr | — | Row |
| th | colSpan, rowSpan, scope | Header cell |
| td | colSpan, rowSpan | Data cell |
| caption | — | Table caption |

### Links

| Element | Key Props | Notes |
|---------|-----------|-------|
| a | href, target, rel | target="_blank", rel="noopener" |
| Link | to | Client-side nav: `ps.Link("Home", to="/")` |

### Interactive

| Element | Key Props | Notes |
|---------|-----------|-------|
| details | open | Expandable section |
| summary | — | Details header |
| dialog | open | Modal dialog |
| menu | — | Menu container |

### SVG

| Element | Key Props | Notes |
|---------|-----------|-------|
| svg | width, height, viewBox | Container |
| circle | cx, cy, r, fill | Circle shape |
| rect | x, y, width, height, fill | Rectangle |
| path | d, stroke, fill | Arbitrary path |
| line | x1, y1, x2, y2, stroke | Line segment |
| polygon | points, fill | Closed shape |
| polyline | points, stroke, fill | Open shape |
| ellipse | cx, cy, rx, ry | Ellipse |
| text | x, y | SVG text |
| g | transform | Group: `transform="translate(10,10)"` |
| defs, use, clipPath, mask, pattern | id, href | Reusable definitions |

### Other

| Element | Notes |
|---------|-------|
| br, hr | Line break, horizontal rule |
| fragment | React fragment `<>...</>` |
| slot | Web component slot |
| template | Template element |

## Syntax Variants

```python
ps.div(ps.h1("Title"), ps.p("Body"))                  # Positional children
ps.div(className="container")[ps.h1("Title")]         # Bracket syntax
ps.div(show_header and ps.h1("Header"), ps.p("..."))  # Conditional
```

## Common Props

| Prop | Example |
|------|---------|
| id | `id="unique-id"` |
| className | `className="class1 class2"` |
| style | `style=ps.CSSProperties(backgroundColor="red", padding="10px")` |
| key | `key="unique-key"` — for list reconciliation |
| title | `title="Tooltip text"` |
| tabIndex, hidden, draggable, contentEditable | Boolean/int props |

### ARIA & Data Attributes

```python
aria_label="Description"    data_testid="my-element"
aria_describedby="id"       data_custom="value"
aria_hidden=True
role="button"
```

## Styling

```python
# Inline styles
ps.div("Content", style=ps.CSSProperties(
    backgroundColor="red", color="white", padding="10px", display="flex",
    justifyContent="center", borderRadius="8px",
))

# Class names
ps.div(className="card shadow-lg")
ps.div(className=f"btn {'active' if is_active else ''}")
```

## Events

### Event Props

| Category | Events |
|----------|--------|
| Mouse | onClick, onDoubleClick, onMouseDown/Up, onMouseEnter/Leave, onMouseMove, onMouseOver/Out, onContextMenu |
| Keyboard | onKeyDown, onKeyUp |
| Focus | onFocus, onBlur |
| Form | onChange, onInput, onSubmit, onReset, onInvalid |
| Touch | onTouchStart/End/Move/Cancel |
| Drag | onDrag, onDragStart/End, onDragEnter/Leave/Over, onDrop |
| Clipboard | onCopy, onCut, onPaste |
| Media | onPlay, onPause, onEnded, onLoadedData, onTimeUpdate, onVolumeChange |
| Animation | onAnimationStart/End/Iteration, onTransitionEnd |
| Other | onLoad, onError, onScroll, onWheel, onToggle |

### Event Handling Patterns

```python
# Simple click
ps.button("Click", onClick=lambda: do_action())

# Input value
ps.input(value=state.text, onChange=lambda e: setattr(state, "text", e["target"]["value"]))

# Checkbox
ps.input(type="checkbox", checked=state.enabled,
         onChange=lambda e: setattr(state, "enabled", e["target"]["checked"]))

# Select
ps.select(value=state.choice, onChange=lambda e: setattr(state, "choice", e["target"]["value"]))[
    ps.option("Option A", value="a"),
    ps.option("Option B", value="b"),
]

# Keyboard
ps.input(onKeyDown=lambda e: submit() if e["key"] == "Enter" else None)

# Async handler
async def handle_click():
    await api.fetch_data()
ps.button("Load", onClick=handle_click)
```

### Event Object Structure

Events are serialized dicts:

```python
# Mouse: type, target, clientX, clientY, button, altKey, ctrlKey, metaKey, shiftKey
{"type": "click", "target": {"id": "...", "value": "..."}, "clientX": 100, "clientY": 200, ...}

# Keyboard: type, key, code, repeat, altKey, ctrlKey, metaKey, shiftKey
{"type": "keydown", "key": "Enter", "code": "Enter", ...}

# Change: type, target.value, target.checked (checkbox), target.selectedIndex (select)
{"type": "change", "target": {"value": "new text", "checked": True}}
```

## Built-in Components

| Component | Usage |
|-----------|-------|
| `ps.For` | `ps.For(items, lambda item, i: ps.li(item.name, key=str(item.id)))` |
| `ps.If` | `ps.If(cond, then=ps.div("Yes"), else_=ps.div("No"))` |
| `ps.Link` | `ps.Link("Home", to="/")` — client-side navigation |
| `ps.Outlet` | Renders child routes in layout components |
| `ps.Form` | `ps.Form(ps.input(name="email"), on_submit=handler)` |

### `ps.Outlet` Example

```python
@ps.component
def Layout():
    return ps.div(ps.nav(...), ps.main(ps.Outlet()))
```

## Helpers

| Helper | Usage |
|--------|-------|
| `ps.repeat(n, fn)` | `*ps.repeat(5, lambda i: ps.span(f"Item {i}"))` |
| `ps.later(delay, fn)` | `ps.later(5.0, lambda: state.refresh())` — delayed callback |

## See Also

- `forms.md` - Form handling and validation
- `routing.md` - Link component and navigation
- `js-interop.md` - Custom React components
