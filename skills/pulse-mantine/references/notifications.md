# Notifications API

Global toast notification system with imperative API.

## Setup

Add `Notifications` container to your layout (once):

```python
from pulse_mantine import MantineProvider, Notifications

@ps.component
def Layout():
    return MantineProvider()[
        Notifications(position="top-right"),  # container
        Content(),
    ]
```

## Position Options

```python
Notifications(
    position="top-right",  # default
    # Options: "top-left", "top-right", "top-center",
    #          "bottom-left", "bottom-right", "bottom-center"
    zIndex=9999,
    autoClose=5000,  # default auto-close ms (false to disable)
    limit=5,  # max visible notifications
    containerWidth=440,
)
```

## Show Notifications

```python
from pulse_mantine import notifications

# Basic
notifications.show(message="Hello!")

# With options
notifications.show(
    id="my-notification",  # optional, for update/hide
    title="Success",
    message="File uploaded successfully",
    color="green",
    icon=IconCheck(),
    autoClose=5000,  # ms, or False to disable
    withCloseButton=True,
    loading=False,
    withBorder=False,
    radius="md",
    onClose=lambda: print("closed"),
    onOpen=lambda: print("opened"),
)
```

## Update Notifications

```python
# Show loading notification
notifications.show(
    id="upload",
    title="Uploading",
    message="Please wait...",
    loading=True,
    autoClose=False,
    withCloseButton=False,
)

# Update when done
notifications.update(
    id="upload",
    title="Complete",
    message="File uploaded!",
    color="green",
    icon=IconCheck(),
    loading=False,
    autoClose=3000,
)
```

## Hide Notifications

```python
# Hide specific notification
notifications.hide(id="my-notification")

# Hide all visible notifications
notifications.clean()

# Clear queued notifications (not yet visible)
notifications.cleanQueue()
```

## Query State

```python
# Check if notification is visible
is_visible = notifications.isVisible(id="my-notification")

# Check if notification is queued
is_queued = notifications.isQueued(id="my-notification")

# Get visible notification IDs
visible = notifications.getVisible()

# Get queued notification IDs
queued = notifications.getQueued()

# Get full state
state = notifications.getState()
```

## Update State

```python
notifications.updateState(
    queue=[...],  # pending notifications
    notifications=[...],  # visible notifications
)
```

## Common Patterns

### Success/Error
```python
def on_submit(values):
    try:
        save(values)
        notifications.show(
            title="Saved",
            message="Changes saved successfully",
            color="green",
        )
    except Exception as e:
        notifications.show(
            title="Error",
            message=str(e),
            color="red",
        )
```

### Loading State
```python
async def upload_file(file):
    notifications.show(
        id="upload",
        title="Uploading",
        message=f"Uploading {file.name}...",
        loading=True,
        autoClose=False,
    )

    try:
        await do_upload(file)
        notifications.update(
            id="upload",
            title="Complete",
            message="Upload successful",
            color="green",
            loading=False,
            autoClose=3000,
        )
    except Exception as e:
        notifications.update(
            id="upload",
            title="Failed",
            message=str(e),
            color="red",
            loading=False,
        )
```

### Progress Updates
```python
def on_progress(progress):
    notifications.update(
        id="upload",
        message=f"Uploading... {progress}%",
    )
```

### With Actions
```python
notifications.show(
    title="New message",
    message=Group()[
        Text("You have a new message"),
        Button("View", size="xs", onClick=view_message),
    ],
    autoClose=False,
)
```

## Full API Reference

### notifications.show(...)
| Prop | Type | Description |
|------|------|-------------|
| `id` | `str` | Unique identifier (auto-generated if not provided) |
| `title` | `str \| Component` | Notification title |
| `message` | `str \| Component` | Notification body |
| `color` | `str` | Mantine color |
| `icon` | `Component` | Left icon |
| `loading` | `bool` | Show loading spinner |
| `autoClose` | `int \| bool` | Auto-close delay in ms, or False |
| `withCloseButton` | `bool` | Show close button |
| `withBorder` | `bool` | Add border |
| `radius` | `str` | Border radius |
| `className` | `str` | CSS class |
| `style` | `dict` | Inline styles |
| `onClose` | `callable` | Called when closed |
| `onOpen` | `callable` | Called when opened |

### notifications.update(id, ...)
Same props as `show()`, but `id` is required.

### notifications.hide(id)
Hide a specific notification by ID.

### notifications.clean()
Hide all visible notifications.

### notifications.cleanQueue()
Clear all queued (not yet visible) notifications.
