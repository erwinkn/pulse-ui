# Refs

Server-side handles for imperative DOM operations. Unlike React refs (client-only), Pulse refs send commands over WebSocket.

## Creating Refs

```python
import pulse as ps

@ps.component
def AutoFocusInput():
    input_ref = ps.ref()

    async def focus_on_mount():
        await input_ref.wait_mounted()
        input_ref.focus()

    return ps.input(ref=input_ref, placeholder="Auto-focused")
```

**Outside render (requires active render session):**
```python
handle = ps.ref()
```

**Ref callback:**
```python
def on_ref(value: ps.Ref | None):
    if value:
        value.focus()

ps.input(ref=on_ref)
```

**With lifecycle callbacks:**
```python
input_ref = ps.ref(
    on_mount=lambda: print("Input mounted"),
    on_unmount=lambda: print("Input unmounted"),
)
```

**With key for loops:**
```python
for item_id in items:
    ref = ps.ref(key=item_id)  # Required in loops
```

## Fire-and-Forget Methods

These methods send commands to the client without waiting for a response. They're synchronous—call and move on.

### Focus & Blur

```python
input_ref.focus()                        # Focus element
input_ref.focus(prevent_scroll=True)     # Focus without scrolling
input_ref.blur()                         # Remove focus
```

### Click, Submit, Reset

```python
button_ref.click()      # Programmatic click
form_ref.submit()       # Submit form
form_ref.reset()        # Reset form
```

### Scroll Operations

```python
# Scroll element into view
element_ref.scroll_into_view()
element_ref.scroll_into_view(behavior="smooth", block="center")

# Scroll within element
container_ref.scroll_to(top=0, left=0, behavior="smooth")
container_ref.scroll_by(top=100)  # Scroll down 100px
```

**Options:**
- `behavior`: `"auto"` | `"smooth"`
- `block`: `"start"` | `"center"` | `"end"` | `"nearest"`
- `inline`: `"start"` | `"center"` | `"end"` | `"nearest"`

### Selection

```python
input_ref.select()                              # Select all text
input_ref.set_selection_range(0, 5)             # Select first 5 chars
input_ref.set_selection_range(0, 5, direction="forward")
```

## Request-Response Methods

These methods send a request and await the response. Must be called from async functions.

### Measure Element

```python
rect = await element_ref.measure()
# Returns: {"x", "y", "width", "height", "top", "right", "bottom", "left"}
print(f"Element size: {rect['width']}x{rect['height']}")
```

### Get/Set Value

```python
# For inputs
value = await input_ref.get_value()
await input_ref.set_value("New value")

# Or use get_prop/set_prop
value = await input_ref.get_prop("value")
await input_ref.set_prop("value", "New value")
```

### Get/Set Text Content

```python
text = await div_ref.get_text()
await div_ref.set_text("Updated content")
```

### Get/Set Properties

```python
# Read-only properties
scroll_top = await container_ref.get_prop("scrollTop")
client_height = await container_ref.get_prop("clientHeight")
is_checked = await checkbox_ref.get_prop("checked")

# Writable properties
await input_ref.set_prop("value", "text")
await checkbox_ref.set_prop("checked", True)
await input_ref.set_prop("disabled", True)
```

**Gettable properties:** `value`, `checked`, `disabled`, `readOnly`, `selectedIndex`, `selectionStart`, `selectionEnd`, `selectionDirection`, `scrollTop`, `scrollLeft`, `scrollHeight`, `scrollWidth`, `clientWidth`, `clientHeight`, `offsetWidth`, `offsetHeight`, `innerText`, `textContent`, `className`, `id`, `name`, `type`, `tabIndex`

**Settable properties:** `value`, `checked`, `disabled`, `readOnly`, `selectedIndex`, `selectionStart`, `selectionEnd`, `selectionDirection`, `scrollTop`, `scrollLeft`, `className`, `id`, `name`, `type`, `tabIndex`

### Get/Set Attributes

```python
href = await link_ref.get_attr("href")
await div_ref.set_attr("data-status", "active")
await div_ref.remove_attr("data-status")
```

### Set Styles

```python
await element_ref.set_style({
    "backgroundColor": "red",
    "font-size": "16px",  # Kebab-case works too
    "opacity": 0.5,       # Numbers work
    "display": None,      # None removes the style
})
```

## Lifecycle

### Check Mount Status

```python
if input_ref.mounted:
    input_ref.focus()
```

### Wait for Mount

```python
await input_ref.wait_mounted()          # Wait indefinitely
await input_ref.wait_mounted(timeout=2.0)  # With timeout
```

### Mount/Unmount Handlers

```python
ref = ps.ref(
    on_mount=lambda: print("Mounted"),
    on_unmount=lambda: print("Unmounted"),
)

# Or add handlers after creation
remove_handler = ref.on_mount(lambda: print("Mounted"))
remove_handler()  # Remove handler
```

## Error Handling

```python
from pulse import RefNotMounted, RefTimeout

# RefNotMounted - calling methods before mount
try:
    input_ref.focus()  # Raises if not mounted
except RefNotMounted:
    print("Ref not mounted yet")

# RefTimeout - wait_mounted timeout
try:
    await input_ref.wait_mounted(timeout=1.0)
except RefTimeout:
    print("Timed out waiting for mount")
```

**Best practice:** Use `wait_mounted()` before operations, or check `mounted` property:

```python
async def safe_focus(ref):
    try:
        await ref.wait_mounted(timeout=2.0)
        ref.focus()
    except RefTimeout:
        pass  # Element never mounted
```

## Common Patterns

### Auto-Focus on Mount

```python
@ps.component
def AutoFocusInput():
    ref = ps.ref(on_mount=lambda: ref.focus())
    return ps.input(ref=ref)
```

### Scroll to Element

```python
async def scroll_to_item(ref):
    await ref.wait_mounted()
    ref.scroll_into_view(behavior="smooth", block="center")
```

### Measure Before Positioning

```python
async def position_tooltip(target_ref, tooltip_ref):
    rect = await target_ref.measure()
    await tooltip_ref.set_style({
        "top": f"{rect['bottom']}px",
        "left": f"{rect['left']}px",
    })
```

### Conditional Ref Operations

```python
@ps.component
def ConditionalFocus():
    with ps.init():
        state = FormState()

    input_ref = ps.ref()

    async def validate_and_focus():
        if not state.is_valid:
            await input_ref.wait_mounted(timeout=1.0)
            input_ref.focus()

    return ps.div(
        ps.input(ref=input_ref, value=state.value),
        ps.button("Validate", onClick=validate_and_focus),
    )
```

## When to Use Refs vs State

| Use Refs | Use State |
|----------|-----------|
| Focus/blur inputs | Input values |
| Scroll positions | UI toggles |
| Measure elements | Data display |
| Trigger animations | Form data |
| DOM manipulations | App logic |

**Rule of thumb:** Use state for data, refs for DOM operations that can't be expressed declaratively.

## See Also

- `state.md` — Reactive state management
- `hooks.md` — Hook patterns for initialization
- `channels.md` — Real-time bidirectional communication
