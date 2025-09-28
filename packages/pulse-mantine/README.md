# Pulse Mantine

`pulse-mantine` is a wrapper around the Mantine UI library, with customizations where necessary to make it work well with Pulse.

`pulse-mantine` currently implements:

- `@mantine/core`
- `@mantine/form` with a custom wrapper (see below)
- `@mantine/dates`
- `@mantine/charts`

Not all components are typed in Python yet, but you can still use them exactly like in the official Mantine examples.

Support for the other extensions is coming soon.

## Core Mantine

The `@mantine/core` components are nearly all usable as-is by calling the component and passing in the same props.

You can refer to the official documentation for usage examples and the API reference: https://mantine.dev/core/package/

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

Like `useForm`, `MantineForm` gives you access to methods to manipulate the form state:
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


This is primarily useful if you're working with nested forms or dynamic forms, where you need to add or remove fields.

### Validation rules

### Form actions

## Core

### Layout

[x] AppShell
[x] AspectRatio
[x] Center
[x] Container
[x] Flex
[x] Grid
[x] Group
[x] SimpleGrid
[x] Space
[x] Stack

### Inputs

[x] AngleSlider
[x] Checkbox
[x] Chip
[x] ColorInput
[x] ColorPicker
[x] Fieldset
[x] FileInput
[x] Input (shouldn't be used)
[x] JsonInput
[x] NativeSelect
[x] NumberInput
[x] PasswordInput
[x] PinInput
[x] Radio
[x] RangeSlider
[x] Rating
[x] SegmentedControl
[x] Slider
[x] Switch
[x] Textarea
[x] TextInput

### Combobox

[x] Autocomplete
[x] Combobox
[x] MultiSelect
[x] Pill
[x] PillsInput
[x] Select
[x] TagsInput

### Buttons

[x] ActionIcon
[x] Button
[x] CloseButton
[x] CopyButton -> we'll likely need a custom version on top
[x] FileButton
[x] UnstyledButton

### Navigation

[x] Anchor
[x] Breadcrumbs
[x] Burger
[x] NavLink
[x] Pagination
[x] Stepper
[x] TableOfContents
[x] Tabs
[x] Tree

### Feedback

[x] Alert
[x] Loader
[x] Notification
[x] Progress
[x] RingProgress
[x] SemiCircleProgress
[x] Skeleton

### Overlays

[x] Affix
[x] Dialog
[x] Drawer
[x] FloatingIndicator
[x] HoverCard
[x] LoadingOverlay
[x] Menu
[x] Modal
[x] Overlay
[x] Popover
[x] Tooltip

### Data display

[x] Accordion
[x] Avatar
[x] BackgroundImage
[x] Badge
[x] Card
[x] ColorSwatch
[x] Image
[x] Indicator
[x] Kbd
[x] NumberFormatter
[x] Spoiler
[x] ThemeIcon
[x] Timeline

### Typography

[x] Blockquote
[x] Code
[x] Highlight
[x] List
[x] Mark
[x] Table
[x] Text
[x] Title
[x] Typography

### Miscellaneous

[x] Box
[x] Collapse
[x] Divider
[x] FocusTrap
[x] Paper
[x] Portal
[x] ScrollArea
[x] Transition
[x] VisuallyHidden

## Dates (extension)

[x] Calendar
[x] CalendarHeader
[x] DateInput
[x] DatePicker
[x] DatePickerInput
[x] DatesProvider
[x] DateTimePicker
[x] Day
[x] DecadeLevel
[x] DecadeLevelGroup
[x] HiddenDatesInput
[x] LevelsGroup
[x] MiniCalendar
[x] Month
[x] MonthLevel
[x] MonthLevelGroup
[x] MonthPicker
[x] MonthPickerInput
[x] MonthsList
[x] PickerControl
[x] PickerInputBase
[x] TimeGrid
[x] TimeInput
[x] TimePicker
[x] TimeValue
[x] WeekdaysRow
[x] YearLevel
[x] YearLevelGroup
[x] YearPicker
[x] YearPickerInput
[x] YearsList

## Charts (extension)

[x] AreaChart
[x] BarChart
[x] BubbleChart
[x] ChartLegend
[x] ChartTooltip
[x] CompositeChart
[x] DonutChart
[x] FunnelChart
[x] Heatmap
[x] LineChart
[x] PieChart
[x] RadarChart
[x] RadialBarChart
[x] ScatterChart
[x] Sparkline
