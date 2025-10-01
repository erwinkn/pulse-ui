# Pulse Mantine

`pulse-mantine` is a wrapper around the Mantine UI library, with customizations where necessary to make it work well with Pulse.

`pulse-mantine` currently implements:

- `@mantine/core`
- `@mantine/form` with a custom wrapper (see below)
- `@mantine/dates`
- `@mantine/charts`

Support for the other extensions is coming soon.

## Core Mantine

The `@mantine/core` components are all usable as-is by calling the component and passing in the same props.

You can refer to the official documentation for usage examples and the API reference: https://mantine.dev/core/package/.

Not all components are typed in Python yet, but you can still use them exactly like in the official Mantine examples.

If you notice any problem, please submit an issue, I have not tested all components yet.


## Forms

Forms are the most customized area of `pulse-mantine`. There are two reasons for this:

1. Mantine forms mostly operate through the `useForm` hook and imperative calls to JavaScript functions, not through components and props.
2. Forms benefit heavily from fast client-side validation.

`pulse-mantine` addresses both challenges by providing a custom `MantineForm` wrapper, making Mantine inputs automatically register into forms, and providing additional validation built-ins that run fully in JavaScript.

### Building forms

We replace the `useForm` hook with a `MantineForm` state. You can either instantiate this state directly or inherit from it to build your own state.

A form then requires three things:

- A `MantineForm` instance
- Calling `MantineForm.render()` to set up the form
- Giving a name to all inputs inside the form. The name defines their path in the form's data structure.

By following these steps, the input components will automatically detect they are within a form and register themselves.

Let's see how Mantine's standard form example translates to Pulse.

```tsx
import { Button, Checkbox, Group, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";

function Demo() {
  const form = useForm({
    mode: "uncontrolled",
    initialValues: {
      email: "",
      termsOfService: false,
    },

    validate: {
      email: (value) => (/^\S+@\S+$/.test(value) ? null : "Invalid email"),
    },
  });

  return (
    <form onSubmit={form.onSubmit((values) => console.log(values))}>
      <TextInput
        withAsterisk
        label="Email"
        placeholder="your@email.com"
        key={form.key("email")}
        {...form.getInputProps("email")}
      />

      <Checkbox
        mt="md"
        label="I agree to sell my privacy"
        key={form.key("termsOfService")}
        {...form.getInputProps("termsOfService", { type: "checkbox" })}
      />

      <Group justify="flex-end" mt="md">
        <Button type="submit">Submit</Button>
      </Group>
    </form>
  );
}
```

The equivalent version in `pulse-mantine` is the following.

```python
import pulse as ps
from pulse_mantine import (
    Button,
    Checkbox,
    Group,
    IsEmail,
    MantineForm,
    TextInput,
)


@ps.component
def Demo():
    form = ps.states(
        lambda: MantineForm(
            mode="uncontrolled",
            initialValues={"email": "", "termsofService": False},
            validate={
                # Equivalent to Mantine's built-in `isEmail` validator
                "email": IsEmail("Invalid email")
            },
        )
    )

    # `MantineForm.render` accepts all the regular <form> attributes
    return form.render(
        # Will print `{ "email": "your@email.com", "termsOfService": True, }`
        onSubmit=lambda values: print(values),
    )[
        TextInput(
            # Setting the name will register this field like
            # `{...form.getInputProps('email')}` in the original example
            name="email",
            withAsterisk=True,
            label="Email",
            placeholder="your@email.com",
        ),
        Checkbox(
            # Same thing, registers as the "termsOfService" field
            name="termsOfService",
            mt="md",
            label="I agree to sell my privacy",
        ),
        Group(justify="flex-end", mt="md")[Button("Submit", type="submit")],
    ]
```

You can find this example at [`examples/pulse-mantine/01-basic-form.py`](../../examples/pulse-mantine/01-basic-form.py).

For efficiency, the form state lives on the client and is only sent to the server on submit or on server validation (see [Validation rules](#validation-rules)).

### Validation

Any good form requires validation. `pulse-mantine` ships with all the built-in Mantine validators:

- `IsNotEmpty`
- `IsEmail`
- `Matches`
- `IsInRange`
- `HasLength`
- `MatchesField`
- `IsJSONString`
- `IsNotEmptyHTML`

Note that `Matches` runs the RegEx both on the client and the server. Since JavaScript and Python regular expressions differ slightly, you have the option of specifying a different RegEx for the client.

In addition, the following built-in validators are available:

- `IsUrl`, `IsUUID` and `IsULID`
- `IsNumber` and `IsInteger`
- `StartsWith` and `EndsWith`
- `IsDate` and `IsISODate`
- `IsBefore` and `IsAfter` compare two values while coercing numerical or date-like strings.
- `MinItems`, `MaxItems`, `IsArrayNotempty` for arrays.
- `AllowedFileTypes` and `MaxFileSize` for files.
- `RequiredWhen` and `RequiredUnless`: conditionally require a field based on another field's value. Both accept `equals`, `not_equals`, `in_values`, and `not_in_values` conditions.

All validators accept an `error` argument to customize the error message (and sometimes additional error arguments, if there are multiple possible error sources).

These built-in validators run both on the client, for instant feedback, and on the server on form submission, for security.

You can find an example with the following validation schema in [`examples/pulse-mantine/02-validation.py`](../../examples/pulse-mantine/02-validation.py):

```python
validate = {
  "username": [
      IsNotEmpty("Username is required"),
      HasLength(min=3, max=16, error="3-16 characters"),
      Matches(
          r"^[a-z0-9_]+$", error="Lowercase letters, numbers, underscore"
      ),
  ],
  "email": IsEmail("Enter a valid email"),
  "password": HasLength(min=8, error="Min 8 characters"),
  "start": IsDate("Pick a start date"),
  "end": [
      IsDate("Pick an end date"),
      IsAfter(
          "start",
          inclusive=True,
          error="End date must be on or after start",
      ),
  ],
  "deadline": [
      IsDate("Set a deadline"),
      IsBefore("end", error="Deadline must be before the end date"),
      IsAfter("start", error="Deadline must after the start date"),
  ],
}
```

Contrary to Mantine, each field can accept a list of validators, they will be run in succession.

While not demonstrated here, to add validators for the root of an array, add an entry for `'formRootRule'` into a level of the validation dictionary. This is a string key, no special import is needed. See the [official documentation](https://mantine.dev/form/validation/#formrootrule) on `formRootRule` for more detail.

You can decide when validation runs by passing in the regular Mantine configuration options to the `MantineForm` constructor:

- [`validateInputOnChange`](https://mantine.dev/form/validation/#validate-fields-on-change) to validate all or specific inputs on change
- [`validateInputonBlur`](https://mantine.dev/form/validation/#validate-fields-on-blur) to validate all or specific inputs on blur (= when the user defocuses the input)

### Server validation

The above validators are helpful, but you may need to check a field against your database or run more complex logic on the server. For this, Pulse introduces a `ServerValidation` validator. It can be applied to any field and accepts any synchronous or asynchronous function with this signature.

```python
def server_validation_function(value, values, path):
  ...
```

Here, `value` refers to the field's current value, `values` to the current form values and `path` to the field's path within the form (equal to its ame).

`ServerValidation` accepts two optional arguments:

- `debounceMs`, which is used to debounce server validation calls for change events of text inputs
  - For example: a user is typing into a text input and a server validator is supposed to run on each change. `debounceMs` is set to 300ms. Instead of firing a server validation call on every key stroke, the application will wait until it has been at least 300ms since the last user's key stroke before calling the server validator.
  - If not specified, it defaults to the `debounceMs` passed to the `MantineForm` constructor, which has a default value of 300 ms.
- `runs_on`, which can take a value of `submit`, `blur`, or `change`
  - By default, a server validator runs when the field it targets is validated, according to the form's settings
  - However, let's say you have a text input with built-in validators for minimum number of characters and disallowing special characters, plus a server validator to check for duplicates in the database. You likely want the built-in validators to run in the browser on every keystroke, but run the server validator only when the user stops typing. One option is to add a debounce delay (described above). Another option is to set `runs_on="blur"` or `runs_on="submit"` to only run the server validation when the user clicks out of the field, or when they submit the form.

### Form actions

Like `useForm`, `MantineForm` gives you access to methods to manipulate the form state:

- `get_form_values()` (async)
- `set_values(values)`
- `set_field_value(path, values)`
- `insert_list_item(path, item, index=None)`
- `remove_list_item(path, index)`
- `reorder_list_item(path, from_index, to_index)`
- `set_errors(errors)`
- `set_field_error(path, error)`
- `clear_errors(*paths)`
- `set_touched(touched)`
- `validate()`
- `reset(initial_values=None)`

They are called [form actions](https://mantine.dev/form/actions/).

You can use them for:

- Retrieve the form values.
- Setting form errors on submit, in addition to the standard form validation.
- Resetting the form or manually triggering validation.
- Creating dynamic forms with lists of items that can be added, reordered, or removed.

### Dynamic forms

Speaking of dynamic forms, we're still missing something for the most complex use cases.

Sure you can call `MantineForm.insert_list_item()` to add an item into the client-side form, but how do you render the fields for it? So far, the form values weren't available on the server.

For this use case, MantineForm has an optional synchronization mode. You can pass `syncMode="change"` to `MantineForm` (`"blur"` and `"none"` are the other accepted values).

With this option, on every change or blur event, the form values will be synchronized to the server and become accessible through the `MantineForm.values` property.

Similary to server validations, the `debounceMs` option is used to debounce text input updates when `syncMode="change"` and defaults to 300ms. It's a reasonable default to avoid syncing the form on every keystroke while someone is typing.

Once this synchronization is set up, form actions like `MantineForm.insert_list_item` will also update `MantineForm.values`, which you can use to render your dynamic form.

`MantineForm.values` is reactive, so your Pulse application and effects will automatically update if they change, like a regular state value.

You can find a detailed example in [examples/pulse-mantine/04-dynamic-form.py](../../examples/pulse-mantine/04-dynamic-form.py).

### Uncontrolled forms

For large forms, Mantine recommends to use [uncontrolled mode](https://mantine.dev/form/uncontrolled/), the default mode being _controlled_.

This is difference impacts how the form works in React:
- Controlled: the form values live in React state and are passed to the input elements using `value=...`. On every update, the React state is updated, the React components rerender, and the inputs receive new values. If your form is big and the user's computer is slow, having React rerender on every keystroke may slow down the form and degrade user experience.
- Uncontrolled: the form values are not kept in React state and the inputs do not receive `value=...`. Blur and change events can still be handled for validation, but this avoids React rerenders and is generally much more performant.

All the features described above should work for both controlled and uncontrolled forms, including client-server synchronization. 

Dynamic forms will require a little special attention, as all your dynamic form items should have unique keys. Otherwise, you may see inputs getting mixed up when you add/remove/reorder form items.

## Dates

The `@mantine/dates` components are all usable as-is by calling the component and passing in the same props.

You can refer to the official documentation for usage examples and the API reference: https://mantine.dev/dates/getting-started/.

Not all components are typed in Python yet, but you can still use them exactly like in the official Mantine examples.

If you notice any problem, please submit an issue, I have not tested all components yet.

## Charts

The `@mantine/charts` components are all usable as-is by calling the component and passing in the same props.

You can refer to the official documentation for usage examples and the API reference: https://mantine.dev/dates/getting-started/.

Not all components are typed in Python yet, but you can still use them exactly like in the official Mantine examples.

If you notice any problem, please submit an issue, I have not tested all components yet.

Mantine charts are based on Recharts, so you can also look at [`pulse-recharts`](https://github.com/erwinkn/pulse-ui/tree/main/packages/pulse-recharts) for advanced use cases where direct Recharts usage is required.
