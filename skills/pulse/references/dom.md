# DOM Elements & Events

HTML/SVG elements and event handling.

## HTML Elements

All standard tags available as `ps.<tag>(*children, **props)`:

### Layout

```python
ps.div(*children, className="", id="", style=...)
ps.span(*children, ...)
ps.section(*children, ...)
ps.article(*children, ...)
ps.aside(*children, ...)
ps.header(*children, ...)
ps.footer(*children, ...)
ps.main(*children, ...)
ps.nav(*children, ...)
```

### Text

```python
ps.h1(*children, ...)  # h1-h6
ps.p(*children, ...)
ps.strong(*children, ...)
ps.em(*children, ...)
ps.code(*children, ...)
ps.pre(*children, ...)
ps.blockquote(*children, ...)
ps.small(*children, ...)
ps.mark(*children, ...)
```

### Lists

```python
ps.ul(*children, ...)
ps.ol(*children, start=1, type="1", ...)
ps.li(*children, value=1, ...)
ps.dl(*children, ...)
ps.dt(*children, ...)
ps.dd(*children, ...)
```

### Forms

```python
ps.form(*children, onSubmit=handler, action="", method="", ...)
ps.input(value="", onChange=handler, type="text", placeholder="", disabled=False, ...)
ps.textarea(value="", onChange=handler, rows=3, cols=40, ...)
ps.select(*children, value="", onChange=handler, multiple=False, ...)
ps.option(*children, value="", selected=False, disabled=False, ...)
ps.button(*children, onClick=handler, type="button", disabled=False, ...)
ps.label(*children, htmlFor="", ...)
ps.fieldset(*children, disabled=False, ...)
ps.legend(*children, ...)
```

### Input Types

```python
ps.input(type="text", ...)
ps.input(type="password", ...)
ps.input(type="email", ...)
ps.input(type="number", min=0, max=100, step=1, ...)
ps.input(type="checkbox", checked=False, onChange=handler, ...)
ps.input(type="radio", name="group", checked=False, ...)
ps.input(type="file", accept=".pdf,.doc", multiple=False, ...)
ps.input(type="date", ...)
ps.input(type="time", ...)
ps.input(type="datetime-local", ...)
ps.input(type="range", min=0, max=100, ...)
ps.input(type="color", ...)
ps.input(type="search", ...)
ps.input(type="tel", ...)
ps.input(type="url", ...)
ps.input(type="hidden", value="...", ...)
```

### Media

```python
ps.img(src="", alt="", width=100, height=100, loading="lazy", ...)
ps.video(*children, src="", controls=True, autoplay=False, muted=False, ...)
ps.audio(*children, src="", controls=True, ...)
ps.source(src="", type="video/mp4", ...)
ps.picture(*children, ...)
ps.iframe(src="", width=600, height=400, ...)
ps.canvas(width=300, height=150, ...)
```

### Tables

```python
ps.table(*children, ...)
ps.thead(*children, ...)
ps.tbody(*children, ...)
ps.tfoot(*children, ...)
ps.tr(*children, ...)
ps.th(*children, colSpan=1, rowSpan=1, scope="col", ...)
ps.td(*children, colSpan=1, rowSpan=1, ...)
ps.caption(*children, ...)
```

### Links

```python
ps.a(*children, href="", target="_blank", rel="noopener", ...)
ps.Link(*children, to="/path", ...)  # Client-side nav
```

### Interactive

```python
ps.details(*children, open=False, ...)
ps.summary(*children, ...)
ps.dialog(*children, open=False, ...)
ps.menu(*children, ...)
```

### SVG

```python
ps.svg(*children, width=100, height=100, viewBox="0 0 100 100", ...)
ps.circle(cx=50, cy=50, r=40, fill="red", ...)
ps.rect(x=10, y=10, width=80, height=80, fill="blue", ...)
ps.path(d="M10 10 L90 90", stroke="black", ...)
ps.line(x1=0, y1=0, x2=100, y2=100, stroke="black", ...)
ps.polygon(points="50,15 100,100 0,100", fill="green", ...)
ps.polyline(points="0,0 50,50 100,0", fill="none", stroke="black", ...)
ps.ellipse(cx=50, cy=50, rx=40, ry=20, ...)
ps.text(*children, x=10, y=50, ...)
ps.g(*children, transform="translate(10,10)", ...)  # Group
ps.defs(*children, ...)
ps.use(href="#id", ...)
ps.clipPath(*children, id="clip", ...)
ps.mask(*children, id="mask", ...)
ps.pattern(*children, id="pattern", ...)
```

### Other

```python
ps.br()
ps.hr()
ps.fragment(*children)  # React fragment <>...</>
ps.slot(*children, name="", ...)
ps.template(*children, ...)
```

## Syntax Variants

```python
# Positional children
ps.div(ps.h1("Title"), ps.p("Body"))

# Bracket syntax
ps.div(className="container")[
    ps.h1("Title"),
    ps.p("Body"),
]

# Mixed
ps.div(className="wrap")[ps.span("text")]

# Conditional children (Python and/or)
ps.div(
    show_header and ps.h1("Header"),
    ps.p("Always visible"),
)
```

## Common Props

### Global Props

```python
id="unique-id"
className="class1 class2"
style=ps.CSSProperties(...)
key="unique-key"  # For list reconciliation
title="Tooltip text"
tabIndex=0
hidden=True
draggable=True
contentEditable=True
```

### ARIA

```python
aria_label="Description"
aria_describedby="id"
aria_hidden=True
aria_expanded=False
aria_selected=False
aria_disabled=True
role="button"
```

### Data Attributes

```python
data_testid="my-element"
data_custom="value"
```

## Styling

### CSS Properties

```python
ps.div(
    "Content",
    style=ps.CSSProperties(
        backgroundColor="red",
        color="white",
        padding="10px",
        margin="5px",
        fontSize="16px",
        fontWeight="bold",
        display="flex",
        justifyContent="center",
        alignItems="center",
        width="100%",
        height="50px",
        borderRadius="8px",
        boxShadow="0 2px 4px rgba(0,0,0,0.1)",
    ),
)
```

### Class Names

```python
# Static
ps.div(className="card shadow-lg")

# Dynamic
ps.div(className=f"btn {'active' if is_active else ''}")

# Multiple conditions
ps.div(className=" ".join(filter(None, [
    "base",
    "active" if is_active else None,
    "disabled" if is_disabled else None,
])))
```

## Events

### Event Props

```python
# Mouse
onClick=handler
onDoubleClick=handler
onMouseDown=handler
onMouseUp=handler
onMouseEnter=handler
onMouseLeave=handler
onMouseMove=handler
onMouseOver=handler
onMouseOut=handler
onContextMenu=handler

# Keyboard
onKeyDown=handler
onKeyUp=handler
onKeyPress=handler  # Deprecated

# Focus
onFocus=handler
onBlur=handler

# Form
onChange=handler
onInput=handler
onSubmit=handler
onReset=handler
onInvalid=handler

# Touch
onTouchStart=handler
onTouchEnd=handler
onTouchMove=handler
onTouchCancel=handler

# Drag
onDrag=handler
onDragStart=handler
onDragEnd=handler
onDragEnter=handler
onDragLeave=handler
onDragOver=handler
onDrop=handler

# Clipboard
onCopy=handler
onCut=handler
onPaste=handler

# Scroll
onScroll=handler

# Media
onPlay=handler
onPause=handler
onEnded=handler
onLoadedData=handler
onTimeUpdate=handler
onVolumeChange=handler

# Animation
onAnimationStart=handler
onAnimationEnd=handler
onAnimationIteration=handler
onTransitionEnd=handler

# Other
onLoad=handler
onError=handler
onWheel=handler
onToggle=handler
```

### Event Handling Patterns

```python
# Simple click (no event data needed)
ps.button("Click", onClick=lambda: do_action())
ps.button("Click", onClick=state.method)

# Extract input value
ps.input(
    value=state.text,
    onChange=lambda e: setattr(state, "text", e["target"]["value"]),
)

# Checkbox
ps.input(
    type="checkbox",
    checked=state.enabled,
    onChange=lambda e: setattr(state, "enabled", e["target"]["checked"]),
)

# Select
ps.select(
    value=state.choice,
    onChange=lambda e: setattr(state, "choice", e["target"]["value"]),
)[
    ps.option("Option A", value="a"),
    ps.option("Option B", value="b"),
]

# Keyboard
ps.input(
    onKeyDown=lambda e: submit() if e["key"] == "Enter" else None,
)

# Mouse position
ps.div(
    onClick=lambda e: print(e["clientX"], e["clientY"]),
)

# Form submit
ps.form(
    onSubmit=lambda e: handle_submit(),
)[...]

# Async handler
async def handle_click():
    await api.fetch_data()
    state.update()

ps.button("Load", onClick=handle_click)
```

### Event Object Structure

Events are serialized dicts:

```python
# Mouse event
{
    "type": "click",
    "target": {"id": "...", "value": "...", ...},
    "clientX": 100,
    "clientY": 200,
    "button": 0,
    "altKey": False,
    "ctrlKey": False,
    "metaKey": False,
    "shiftKey": False,
}

# Keyboard event
{
    "type": "keydown",
    "key": "Enter",
    "code": "Enter",
    "altKey": False,
    "ctrlKey": False,
    "metaKey": False,
    "shiftKey": False,
    "repeat": False,
}

# Change event
{
    "type": "change",
    "target": {
        "value": "new text",
        "checked": True,  # For checkboxes
        "selectedIndex": 0,  # For select
    },
}

# Form event
{
    "type": "submit",
    "target": {...},
}
```

## Built-in Components

### `ps.For` — List Iteration

```python
ps.For(
    items,
    lambda item, index: ps.li(item.name, key=str(item.id)),
)
```

### `ps.If` — Conditional

```python
ps.If(
    condition,
    then=ps.div("True branch"),
    else_=ps.div("False branch"),
)
```

### `ps.Link` — Client Navigation

```python
ps.Link("Home", to="/")
ps.Link("User", to=f"/users/{user_id}")
ps.Link("External", to="https://example.com", target="_blank")
```

### `ps.Outlet` — Route Child

```python
@ps.component
def Layout():
    return ps.div(
        ps.nav(...),
        ps.main(ps.Outlet()),  # Child routes render here
    )
```

### `ps.Form` — Declarative Form

```python
ps.Form(
    ps.input(name="email", type="email"),
    ps.input(name="password", type="password"),
    ps.button("Submit", type="submit"),
    on_submit=lambda data: print(data),
)
```

## Helpers

### `ps.repeat(count, fn)`

```python
ps.div(
    *ps.repeat(5, lambda i: ps.span(f"Item {i}")),
)
```

### `ps.later(delay, callback)`

```python
ps.later(5.0, lambda: state.refresh())  # Call after 5 seconds
```
