# Pulse Mantine (Python)

Python bindings for Mantine UI components. Provides typed component wrappers for use in Pulse applications.

## Architecture

Auto-generated Python wrappers around Mantine React components. Components are lazy-loaded and rendered to VDOM, which syncs to the JS client.

```
Python Component Call → VDOM Node → WebSocket → React Mantine Component
```

## Folder Structure

```
src/pulse_mantine/
├── __init__.py           # Auto-generated exports (lazy loading)
├── version.py            # Package version
│
├── core/                 # Core Mantine components
│   ├── base.py           # MantineComponentProps base
│   ├── box.py            # Box, Mod
│   ├── provider.py       # MantineProvider, theme context
│   ├── theme.py          # MantineTheme, colors, spacing
│   ├── styles.py         # CSSVariables, StyleProp
│   ├── types.py          # MantineSize, MantineColor, etc.
│   │
│   ├── buttons/          # Button, ActionIcon, CloseButton, etc.
│   ├── inputs/           # TextInput, Checkbox, Select, Slider, etc.
│   ├── combobox/         # Autocomplete, MultiSelect, TagsInput, etc.
│   ├── layout/           # AppShell, Container, Flex, Grid, Stack, etc.
│   ├── data_display/     # Accordion, Avatar, Badge, Card, Image, etc.
│   ├── overlays/         # Modal, Drawer, Menu, Popover, Tooltip, etc.
│   ├── navigation/       # Anchor, Breadcrumbs, Pagination, Tabs, etc.
│   ├── feedback/         # Alert, Loader, Progress, Notifications, etc.
│   ├── typography/       # Text, Title, Code, List, Table, etc.
│   └── misc/             # Divider, Paper, ScrollArea, Collapse, etc.
│
├── charts/               # Mantine Charts (Recharts-based)
│   ├── area_chart.py     # AreaChart
│   ├── bar_chart.py      # BarChart
│   ├── line_chart.py     # LineChart
│   ├── pie_chart.py      # PieChart, DonutChart
│   ├── radar_chart.py    # RadarChart
│   ├── scatter_chart.py  # ScatterChart
│   ├── sparkline.py      # Sparkline
│   ├── heatmap.py        # Heatmap
│   └── ...
│
├── dates/                # Date/time components
│   ├── calendar.py       # Calendar
│   ├── date_picker.py    # DatePicker, DatePickerInput
│   ├── date_time_picker.py
│   ├── time_input.py     # TimeInput
│   ├── time_picker.py    # TimePicker
│   └── ...
│
└── form/                 # Form state management
    ├── form.py           # MantineForm - client-side form state
    ├── validators.py     # Built-in validators
    └── internal.py       # Form internals
```

## Key Concepts

### Components

All Mantine components are available as Python functions:

```python
from pulse_mantine import Button, TextInput, Stack

def my_form():
    return Stack([
        TextInput(label="Name", placeholder="Enter name"),
        Button("Submit", color="blue"),
    ])
```

### MantineProvider

Required wrapper for theming:

```python
from pulse_mantine import MantineProvider

def layout(children):
    return MantineProvider(
        theme={"primaryColor": "blue"},
        children=children,
    )
```

### Forms

Client-side form state with validation:

```python
from pulse_mantine import MantineForm, TextInput, IsEmail, IsNotEmpty

form = MantineForm(
    initial_values={"email": "", "name": ""},
    validation={
        "email": IsEmail(),
        "name": IsNotEmpty(),
    },
)

def contact_form():
    return form(
        TextInput(label="Email", **form.field("email")),
        TextInput(label="Name", **form.field("name")),
        Button("Submit", type="submit"),
    )
```

### Charts

Mantine Charts built on Recharts:

```python
from pulse_mantine import LineChart

data = [
    {"date": "Jan", "value": 100},
    {"date": "Feb", "value": 200},
]

def chart():
    return LineChart(data=data, dataKey="date", series=[{"name": "value"}])
```

## Validators

Built-in validators for forms:

- `IsEmail()`, `IsNotEmpty()`, `IsNumber()`, `IsInteger()`
- `HasLength(min, max)`, `Matches(regex)`
- `IsInRange(min, max)`, `IsDate()`, `IsBefore()`, `IsAfter()`
- `IsUrl()`, `IsUUID()`, `IsULID()`, `IsJSONString()`
- `StartsWith()`, `EndsWith()`, `MatchesField(field)`
- `MinItems()`, `MaxItems()`, `AllowedFileTypes()`, `MaxFileSize()`
- `RequiredWhen()`, `RequiredUnless()`

## Main Exports

**Layout**: `AppShell`, `Container`, `Flex`, `Grid`, `Stack`, `Group`, `Center`

**Inputs**: `TextInput`, `Textarea`, `NumberInput`, `Select`, `MultiSelect`, `Checkbox`, `Switch`, `Slider`, `DatePicker`, `ColorInput`

**Buttons**: `Button`, `ActionIcon`, `CloseButton`

**Display**: `Card`, `Badge`, `Avatar`, `Image`, `Table`, `Accordion`, `Timeline`

**Overlays**: `Modal`, `Drawer`, `Menu`, `Popover`, `Tooltip`, `HoverCard`

**Feedback**: `Alert`, `Loader`, `Progress`, `Notification`, `Skeleton`

**Navigation**: `Tabs`, `Breadcrumbs`, `Pagination`, `NavLink`, `Stepper`

**Charts**: `LineChart`, `BarChart`, `AreaChart`, `PieChart`, `RadarChart`

**Form**: `MantineForm` + validators
