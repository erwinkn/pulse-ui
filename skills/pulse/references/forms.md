# Forms

Server-registered form handling with file upload support.

## `ps.Form` Component

Declarative form with automatic server registration. Handles submission via POST with `multipart/form-data`.

```python
async def handle_submit(data: ps.FormData):
    name = data.get("name")  # str
    bio = data.get("bio")    # str
    await save_user(name, bio)

@ps.component
def UserForm():
    return ps.Form(
        ps.input(name="name", type="text", placeholder="Name"),
        ps.textarea(name="bio", rows=3),
        ps.button("Submit", type="submit"),
        key="user-form",
        onSubmit=handle_submit,
    )
```

### Requirements

- `key` — Required, unique non-empty string within the render
- `onSubmit` — Required callable receiving `FormData`
- Cannot override `action`, `method`, `encType` props (auto-generated)

### Bracket Syntax

```python
ps.Form(key="my-form", onSubmit=handler)[
    ps.input(name="field", type="text"),
    ps.button("Submit", type="submit"),
]
```

## `ps.ManualForm` Class

Low-level form handler for custom implementations. Use when you need:
- Access to `is_submitting` state
- Custom form element styling
- Programmatic control over form props

### Creating with `ps.setup()`

```python
@ps.component
def CustomForm():
    with ps.init():
        state = MyState()

    manual_form = ps.setup(lambda: ps.ManualForm(state.handle_submit))

    return ps.div(
        ps.h3(f"Submitting: {manual_form.is_submitting}"),
        manual_form(
            ps.input(name="project", type="text"),
            ps.button("Submit", type="submit"),
            key="custom-form",
        ),
    )
```

### Using `props()` Method

Spread form props onto a custom form element:

```python
@ps.component
def ManualFormExample():
    manual_form = ps.setup(lambda: ps.ManualForm(handle_submit))
    form_props = manual_form.props()

    return ps.form(**form_props)[
        ps.input(name="field", type="text"),
        ps.button("Submit", type="submit"),
    ]
```

`props()` returns:

```python
{
    "action": str,      # Form submission URL
    "method": "POST",
    "encType": "multipart/form-data",
    "onSubmit": callable,  # Triggers is_submitting state
}
```

### `is_submitting` Property

Track submission state for loading indicators:

```python
ps.button(
    "Saving..." if manual_form.is_submitting else "Submit",
    type="submit",
    disabled=manual_form.is_submitting,
)
```

Automatically resets to `False` after `onSubmit` handler completes.

## FormData Handling

`FormData` is `dict[str, FormValue | list[FormValue]]` where `FormValue = str | UploadFile`.

### Accessing Fields

```python
async def handle_submit(data: ps.FormData):
    # Single text field
    name = data.get("name")  # str | None

    # Required field (raises if missing)
    email = data["email"]  # str

    # With type assertion
    age = int(data.get("age", "0"))
```

### Multiple Values

Fields with repeated names or `multiple` attribute return lists:

```python
async def handle_submit(data: ps.FormData):
    # Checkboxes with same name
    selected = data.get("options")  # str | list[str] | None

    # Always get as list
    options = data.get("options", [])
    if not isinstance(options, list):
        options = [options]
```

### Form with State

```python
class FormState(ps.State):
    submissions: list[dict] = []

    async def handle_submit(self, data: ps.FormData):
        self.submissions.append({
            "name": data.get("name"),
            "email": data.get("email"),
        })

@ps.component
def FormPage():
    with ps.init():
        state = FormState()

    return ps.div(
        ps.Form(
            ps.input(name="name", type="text"),
            ps.input(name="email", type="email"),
            ps.button("Submit", type="submit"),
            key="contact-form",
            onSubmit=state.handle_submit,
        ),
        ps.p(f"Total submissions: {len(state.submissions)}"),
    )
```

## File Uploads

### UploadFile Class

File inputs produce `UploadFile` objects (from Starlette):

```python
from fastapi import UploadFile  # or from starlette.datastructures

async def handle_submit(data: ps.FormData):
    avatar = data.get("avatar")
    if isinstance(avatar, UploadFile):
        print(f"Filename: {avatar.filename}")
        print(f"Content-Type: {avatar.content_type}")
        print(f"Size: {avatar.size}")

        # Read content
        content = await avatar.read()
        await avatar.seek(0)  # Reset for re-reading
```

### Single File Input

```python
ps.Form(
    ps.input(
        name="avatar",
        type="file",
        accept="image/*",  # Restrict to images
    ),
    ps.button("Upload", type="submit"),
    key="avatar-form",
    onSubmit=handle_upload,
)
```

### Multiple Files

```python
ps.Form(
    ps.input(
        name="attachments",
        type="file",
        multiple=True,
        accept=".pdf,.doc,.docx",
    ),
    ps.button("Upload", type="submit"),
    key="docs-form",
    onSubmit=handle_uploads,
)

async def handle_uploads(data: ps.FormData):
    files = data.get("attachments", [])
    if not isinstance(files, list):
        files = [files]

    for f in files:
        if isinstance(f, UploadFile):
            content = await f.read()
            await save_file(f.filename, content)
```

### Accept Attribute

Restrict file types:

```python
accept="image/*"                    # All images
accept="image/png,image/jpeg"       # Specific types
accept=".pdf,.doc,.docx"            # By extension
accept="video/*,audio/*"            # Media files
```

### Reading File Content

```python
async def process_file(data: ps.FormData):
    file = data.get("document")
    if not isinstance(file, UploadFile):
        return

    # Read as bytes
    content = await file.read()

    # Read as text (if text file)
    await file.seek(0)
    text = (await file.read()).decode("utf-8")

    # Stream for large files
    await file.seek(0)
    async for chunk in file:
        process_chunk(chunk)
```

## Form Validation Patterns

### Client-Side Validation

Use HTML5 validation attributes:

```python
ps.Form(
    ps.input(name="email", type="email", required=True),
    ps.input(name="age", type="number", min=0, max=120, required=True),
    ps.input(name="username", pattern="[a-z0-9]+", minLength=3, maxLength=20),
    ps.button("Submit", type="submit"),
    key="validated-form",
    onSubmit=handle_submit,
)
```

### Server-Side Validation

Validate in the submit handler:

```python
class FormState(ps.State):
    error: str | None = None

    async def handle_submit(self, data: ps.FormData):
        email = data.get("email", "")
        if not email or "@" not in email:
            self.error = "Invalid email address"
            return

        username = data.get("username", "")
        if await is_username_taken(username):
            self.error = "Username already exists"
            return

        self.error = None
        await create_user(email, username)
```

### Error Display

```python
@ps.component
def FormWithErrors():
    with ps.init():
        state = FormState()

    return ps.div(
        state.error and ps.div(
            state.error,
            className="text-red-500 mb-4",
        ),
        ps.Form(
            ps.input(name="email", type="email"),
            ps.button("Submit", type="submit"),
            key="form",
            onSubmit=state.handle_submit,
        ),
    )
```

### Field-Level Errors

```python
class FormState(ps.State):
    errors: dict[str, str] = {}

    async def handle_submit(self, data: ps.FormData):
        self.errors = {}

        if not data.get("name"):
            self.errors["name"] = "Name is required"

        if not data.get("email"):
            self.errors["email"] = "Email is required"

        if self.errors:
            return

        await save_data(data)

@ps.component
def FormPage():
    with ps.init():
        state = FormState()

    return ps.Form(
        ps.div(
            ps.input(name="name", type="text"),
            state.errors.get("name") and ps.span(
                state.errors["name"],
                className="text-red-500 text-sm",
            ),
        ),
        ps.div(
            ps.input(name="email", type="email"),
            state.errors.get("email") and ps.span(
                state.errors["email"],
                className="text-red-500 text-sm",
            ),
        ),
        ps.button("Submit", type="submit"),
        key="form",
        onSubmit=state.handle_submit,
    )
```

## Integration with pulse-mantine

For advanced forms with built-in validation, use `MantineForm` from pulse-mantine:

```python
from pulse_mantine import MantineForm, TextInput, Button, IsEmail, HasLength

@ps.component
def SignupForm():
    with ps.init():
        form = MantineForm(
            initialValues={"email": "", "password": ""},
            validate={
                "email": IsEmail("Invalid email"),
                "password": HasLength(min=8, error="Min 8 characters"),
            },
        )

    return form.render(onSubmit=lambda v: print(v))[
        TextInput(name="email", label="Email"),
        TextInput(name="password", label="Password", type="password"),
        Button("Submit", type="submit"),
    ]
```

`MantineForm` provides:
- Client-side validation with instant feedback
- Server-side validation via `ServerValidation`
- Form state methods (`set_values`, `set_errors`, `reset`)
- Dynamic form support with `syncMode`

See the [pulse-mantine forms documentation](/docs/packages/pulse-mantine/forms) for details.

## Type Reference

```python
# Type aliases
FormValue = str | UploadFile
FormData = dict[str, FormValue | list[FormValue]]

# Event handler type
EventHandler1[FormData]  # (FormData) -> None | Awaitable[None]
```

## Summary

| Feature | `ps.Form` | `ps.ManualForm` |
|---------|-----------|-----------------|
| Simple forms | Yes | Overkill |
| Submitting state | No | `is_submitting` |
| Custom form element | No | `props()` method |
| File uploads | Yes | Yes |
| Validation | HTML5 / server | HTML5 / server |

## See Also

- `dom.md` - Form elements and event handling
- `state.md` - Form state management patterns
- `hooks.md` - ps.setup for ManualForm initialization
