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

## Synced Values (Dynamic Forms)

Access form values on server with `syncMode`:

```python
form = MantineForm(
    initialValues={"items": [{"name": ""}]},
    syncMode="change",  # sync on every change
    debounceMs=300,
)

# Access values reactively:
items = form.values.get("items") or []

def add_item():
    form.insert_list_item("items", {"name": ""})

def remove_item(i):
    form.remove_list_item("items", i)

return form.render(onSubmit=handle)[
    ps.For(
        list(range(len(items))),
        lambda i: Group(key=f"item-{i}")[
            TextInput(name=f"items.{i}.name"),
            Button("Remove", onClick=lambda: remove_item(i)),
        ],
    ),
    Button("Add Item", onClick=add_item),
]
```

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
import { createConnectedField, useFieldProps } from "pulse-mantine";

// HOC approach:
const ConnectedCustomInput = createConnectedField(CustomInput, {
    debounceOnChange: true,
    coerceEmptyString: true,
});

// Hook approach:
function MyInput(props) {
    const fieldProps = useFieldProps(props, { debounceOnChange: true });
    return <input {...fieldProps} />;
}
```

Options:
- `inputType`: "input" | "checkbox"
- `coerceEmptyString`: boolean
- `debounceOnChange`: boolean
