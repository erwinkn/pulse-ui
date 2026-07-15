# Mantine Forms

Form state management with client-side and server-side validation.

## Basic Setup

```python
from pulse_mantine import MantineForm, TextInput, Button, IsEmail, IsNotEmpty

@ps.component
def MyForm():
    with ps.init():
        form = MantineForm(
            initialValues={"email": "", "name": ""},
            validate={
                "email": IsEmail("Invalid email"),
                "name": IsNotEmpty("Name required"),
            },
        )

    async def handle_submit(values):
        print("Submitted:", values)

    return form.render(onSubmit=handle_submit)[
        TextInput(name="email", label="Email"),
        TextInput(name="name", label="Name"),
        Button("Submit", type="submit"),
    ]
```

## MantineForm Props

```python
MantineForm(
    mode="controlled",  # "controlled" | "uncontrolled"
    initialValues={"field": "value"},
    initialErrors={"field": "Error"},
    initialDirty={"field": True},
    initialTouched={"field": True},
    validate={...},  # validation schema
    validateInputOnBlur=True,  # or list of field names
    validateInputOnChange=True,  # or list of field names
    clearInputErrorOnChange=True,
    touchTrigger="change",  # "change" | "focus"
    syncMode="none",  # "none" | "blur" | "change"
    debounceMs=300,  # debounce for text inputs
    onSyncValues=handler,  # called with values dict on every sync (see Synced Values)
)
```

## Form Rendering

```python
form.render(
    onSubmit=handler,  # receives form values dict
    # Plus any HTML form props
)[
    # Children with name="" prop auto-register
    TextInput(name="email"),
    Select(name="country"),
]
```

Supported form fields with `name=` participate in form state, sync, and validation. This includes:

- List-valued `MultiSelect`, `TagsInput`, and `CheckboxGroup`
- `Autocomplete` (connected since pulse-mantine 0.1.39)

Low-level composition primitives are not form fields. Examples:

- `PillsInput` and `PillsInputField`
- `ChipGroup`
- `ComboboxSearch`

Connect a custom component explicitly with `useField`/`createConnectedField`
when needed.

## Validation

### Built-in Validators

**String:**
```python
IsNotEmpty(error="Required")
IsEmail(error="Invalid email")
Matches(pattern=r"^\d{5}$", error="Invalid ZIP", flags="i")
HasLength(min=3, max=20, error="3-20 chars")
HasLength(exact=6, error="Must be 6 chars")
StartsWith(value="https://", error="Must start with https://")
EndsWith(value=".com", error="Must end with .com")
IsUrl(error="Invalid URL", protocols=["https"], require_protocol=True)
IsJSONString(error="Invalid JSON")
```

**Number:**
```python
IsNumber(error="Must be number")
IsInteger(error="Must be integer")
IsInRange(min=0, max=100, error="0-100")
```

**Date:**
```python
IsDate(error="Invalid date")
IsISODate(error="Must be ISO date", with_time=True)
IsBefore(field="endDate", error="Must be before end", inclusive=True)
IsAfter(field="startDate", error="Must be after start", inclusive=True)
```

**ID:**
```python
IsUUID(error="Invalid UUID", version=4)
IsULID(error="Invalid ULID")
```

**Array:**
```python
IsArrayNotEmpty(error="Select at least one")
MinItems(count=2, error="Select at least 2")
MaxItems(count=5, error="Max 5 items")
```

**File:**
```python
AllowedFileTypes(mime_types=["image/*"], extensions=[".jpg", ".png"], error="Invalid file")
MaxFileSize(bytes=5_000_000, error="Max 5MB")
```

**Conditional:**
```python
RequiredWhen(field="hasAccount", equals=True, error="Required when has account")
RequiredWhen(field="type", in_values=["A", "B"], error="Required for type A or B")
RequiredWhen(field="age", truthy=True, error="Required when age set")
RequiredUnless(field="guest", equals=True, error="Required unless guest")
MatchesField(field="password", error="Passwords must match")
```

### Multiple Validators

```python
validate = {
    "username": [
        IsNotEmpty("Username required"),
        HasLength(min=3, max=20, error="3-20 characters"),
        Matches(r"^[a-z0-9_]+$", error="Lowercase, numbers, underscore only"),
    ],
}
```

### Nested Validation

```python
validate = {
    "address": {
        "street": IsNotEmpty("Street required"),
        "city": IsNotEmpty("City required"),
        "zip": [IsNotEmpty(), Matches(r"^\d{5}$", error="Invalid ZIP")],
    },
}
```

### Server Validation

```python
from pulse_mantine import ServerValidation

class MyForm(MantineForm):
    def __init__(self):
        super().__init__(
            initialValues={"username": ""},
            validate={
                "username": [
                    IsNotEmpty("Required"),
                    ServerValidation(
                        self.check_username,
                        debounce_ms=300,
                        run_on="blur",  # "change" | "blur" | "submit"
                    ),
                ],
            },
        )

    async def check_username(self, value, values, path):
        # Check database, external API, etc.
        if await is_username_taken(value):
            return "Username already taken"
        return None  # No error
```

## Form Actions

### Get Values
```python
values = await form.get_form_values()
```

### Set Values
```python
form.set_values({"email": "new@example.com", "name": "John"})
form.set_field_value("email", "updated@example.com")
```

Both methods update visible inputs in controlled and uncontrolled modes (see Server Write-Backs).

### List Operations (Dynamic Forms)
```python
form.insert_list_item("members", {"name": ""})  # append
form.insert_list_item("members", {"name": ""}, index=0)  # at index
form.remove_list_item("members", index=2)
form.reorder_list_item("members", frm=0, to=2)
```

### Errors
```python
form.set_errors({"email": "Error", "name": "Error"})
form.set_field_error("email", "Invalid")
form.clear_errors()  # all
form.clear_errors("email", "name")  # specific fields
```

### Touched State
```python
form.set_touched({"email": True})
```

### Validation & Reset
```python
form.validate()  # trigger validation
form.reset()  # to initialValues
form.reset(initial_values={"email": ""})  # with new initial values
```

### Submission State
```python
Button(
    "Saving..." if form.is_submitting else "Save",
    type="submit",
    loading=form.is_submitting,
)
```

## Server Write-Backs

`form.set_values()` and `form.set_field_value()` update the visible inputs in both `mode="controlled"` and `mode="uncontrolled"`:

- Controlled inputs update in place through React state.
- Uncontrolled inputs remount: every `name=`-connected input is keyed with Mantine's `form.key(path)`, which changes after a programmatic update, so the input re-reads the new value on mount. Custom JS inputs get the same behavior via `useField` / `createConnectedField` (see JS Exports).

**Before pulse-mantine 0.1.42**, uncontrolled inputs did NOT visually update from server `set_values` / `set_field_value` — form state changed but the DOM kept the old text. On older versions, use `mode="controlled"` for any form the server writes back to (or force a remount yourself with a fresh `key` on the input).

### Dynamic list rows need identity keys (uncontrolled)

`insert_list_item` / `remove_list_item` / `reorder_list_item` do not bump Mantine's input keys. In uncontrolled mode, index-based row keys (`key=f"item-{i}"`) leave stale text in the remaining inputs after a remove or reorder: React reuses the old row's DOM while form state has shifted. Store a stable id in each item and use it as the row key:

```python
import uuid

def add_item():
    form.insert_list_item("items", {"id": uuid.uuid4().hex, "name": ""})

items = form.values.get("items") or []  # requires syncMode="change"/"blur"
return form.render(onSubmit=handle)[
    ps.For(
        list(range(len(items))),
        lambda i: Group(key=items[i]["id"])[
            TextInput(name=f"items.{i}.name"),
        ],
    ),
    Button("Add", onClick=add_item),
]
```

With identity row keys, inputs remount with the right values after a shift because their field path (and therefore `form.key`) changes.

### NumberInput and programmatic writes

Mantine's `NumberInput` manages its displayed text internally; in practice a programmatic write that coincides with a remount (e.g. a paste-fill that also changes row keys) can fail to show up. When programmatic writes must land reliably, prefer `TextInput(name=..., inputMode="numeric")` and coerce to a number on the server.

## Async Initial Values

`initialValues` are captured when `MantineForm` is constructed, and the client form initializes once per mount. A form created with empty `initialValues` before async data arrives stays empty — recreating the Python instance alone (e.g. `ps.init(key=...)`) does not help, because the already-mounted client form keeps its values. Two robust patterns:

```python
# 1. Mount the form only once data is loaded (first mount sees real values)
@ps.component
def Page():
    record = load_record()
    if record is None:
        return Loader()
    return RecordForm(record)

@ps.component
def RecordForm(record: dict):
    with ps.init():
        form = MantineForm(initialValues=record)
    ...

# 2. Create the form empty, write values when data arrives
#    (uncontrolled needs pulse-mantine >= 0.1.42 to show the update)
form.set_values(record)
```

To swap `initialValues` wholesale, recreate the form with `ps.init(key=...)` AND pass the same key to `form.render(key=...)` so the client form remounts and re-initializes.

## File Uploads

`FileInput(name=...)` (or `Dropzone(name=...)`, see `references/dropzone.md`) inside a MantineForm submits files with the rest of the form. On submit, the handler receives them as `ps.UploadFile` at their field path:

```python
form = MantineForm(initialValues={"title": "", "attachment": None}, syncMode="change")

async def handle_submit(values):
    file: ps.UploadFile = values["attachment"]
    data = await file.read()

return form.render(onSubmit=handle_submit)[
    TextInput(name="title"),
    FileInput(name="attachment", label="Attachment"),
    Button("Submit", type="submit"),
]
```

- Files are stripped from value-sync payloads, so file fields don't break `syncMode="change"`/`"blur"`. `form.values` never contains files (a multi-file field syncs as `[]`); files arrive only on submit. Requires pulse-mantine >= 0.1.41 with pulse >= 0.1.99 — before that, file values in a synced form broke sync and submission.
- Multi-file fields (`FileInput(multiple=True)`, Dropzone) submit as a list of `UploadFile`.
- Validate with `AllowedFileTypes` / `MaxFileSize` (run client-side).

## Synced Values (Dynamic Forms)

Access form values on server with `syncMode`:

```python
import uuid

def new_item():
    return {"id": uuid.uuid4().hex, "name": ""}

form = MantineForm(
    initialValues={"items": [new_item()]},
    syncMode="change",  # sync on every change
    debounceMs=300,
)

# Access values reactively:
items = form.values.get("items") or []

def add_item():
    form.insert_list_item("items", new_item())

def remove_item(i):
    form.remove_list_item("items", i)

return form.render(onSubmit=handle)[
    ps.For(
        list(range(len(items))),
        lambda i: Group(key=items[i]["id"])[  # identity key, see Server Write-Backs
            TextInput(name=f"items.{i}.name"),
            Button("Remove", onClick=lambda: remove_item(i)),
        ],
    ),
    Button("Add Item", onClick=add_item),
]
```

### Sync Transport

Value sync travels over the Pulse WebSocket channel, not HTTP. A `POST /_pulse/forms/{render_id}/{form_id}` in the network tab is a native form submission (multipart/form-data) — a submit button, or Enter pressed in a text input, which submits the form by default HTML behavior. It is not the sync path and fires regardless of `syncMode`.

### `onSyncValues` Callback

```python
def on_sync(values: dict):
    print("synced:", values)

form = MantineForm(
    initialValues={"items": []},
    syncMode="change",
    debounceMs=300,
    onSyncValues=on_sync,
)
```

Called with the full values dict every time the client pushes a sync: after the (debounced) change or on blur per `syncMode`, and after server write-backs (`set_values`, `set_field_value`, list operations, `reset` — the client echoes the resulting values back). Fires after `form.values` has been updated, as a background task. Does nothing with `syncMode="none"`. File values are stripped (see File Uploads). Added in pulse-mantine 0.1.40.

## Field Name Paths

Use dot notation for nested fields:
```python
TextInput(name="address.street")
TextInput(name="members.0.name")  # array index
```

## Full Example

```python
from pulse_mantine import (
    MantineForm, TextInput, PasswordInput, Checkbox,
    Select, Button, Stack, Group,
    IsNotEmpty, IsEmail, HasLength, MatchesField, ServerValidation
)

class SignupForm(MantineForm):
    def __init__(self):
        super().__init__(
            mode="uncontrolled",
            initialValues={
                "username": "",
                "email": "",
                "password": "",
                "confirmPassword": "",
                "country": "",
                "terms": False,
            },
            validate={
                "username": [
                    IsNotEmpty("Username required"),
                    HasLength(min=3, max=20, error="3-20 characters"),
                    ServerValidation(self.check_username, run_on="blur"),
                ],
                "email": [IsNotEmpty("Email required"), IsEmail("Invalid email")],
                "password": HasLength(min=8, error="Min 8 characters"),
                "confirmPassword": [
                    IsNotEmpty("Confirm password"),
                    MatchesField("password", error="Passwords must match"),
                ],
                "terms": lambda v: None if v else "Must accept terms",
            },
            validateInputOnBlur=True,
        )

    async def check_username(self, value, values, path):
        taken = {"admin", "root", "system"}
        if value and value.lower() in taken:
            return "Username taken"
        return None

@ps.component
def Signup():
    with ps.init():
        form = SignupForm()

    async def handle_submit(values):
        print("Creating account:", values)

    return form.render(onSubmit=handle_submit)[
        Stack(gap="md")[
            TextInput(name="username", label="Username", withAsterisk=True),
            TextInput(name="email", label="Email", withAsterisk=True),
            PasswordInput(name="password", label="Password", withAsterisk=True),
            PasswordInput(name="confirmPassword", label="Confirm", withAsterisk=True),
            Select(
                name="country",
                label="Country",
                data=["USA", "Canada", "UK"],
            ),
            Checkbox(name="terms", label="I accept terms"),
            Group(justify="flex-end")[
                Button("Sign Up", type="submit"),
            ],
        ],
    ]
```

## JS Exports (Custom Inputs)

Create custom inputs that integrate with forms:

```tsx
// In JS:
import { createConnectedField, useField } from "pulse-mantine";

// HOC approach:
const ConnectedCustomInput = createConnectedField(CustomInput, {
    debounceOnChange: true,
    coerceEmptyString: true,
});

// Hook approach:
function MyInput(props) {
    const { inputProps, key } = useField(props, { debounceOnChange: true });
    return <input key={key} {...inputProps} />;
}
```

The returned `key` keeps custom uncontrolled inputs in sync after programmatic form actions. `createConnectedField` applies it automatically.

Options:
- `inputType`: "input" | "checkbox"
- `coerceEmptyString`: boolean
- `debounceOnChange`: boolean
