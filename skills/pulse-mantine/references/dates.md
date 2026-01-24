# Mantine Dates

Date and time picker components from `@mantine/dates`.

## Provider Setup

Wrap app with `DatesProvider` for locale configuration:

```python
from pulse_mantine import MantineProvider, DatesProvider

@ps.component
def App():
    return MantineProvider()[
        DatesProvider(settings={"locale": "en", "firstDayOfWeek": 0, "timezone": "UTC"})[
            Content()
        ]
    ]
```

## Date Pickers

### DateInput
Text input with date parsing.
```python
DateInput(
    name="date",
    label="Date",
    placeholder="Pick date",
    valueFormat="YYYY-MM-DD",  # dayjs format
    clearable=True,
    minDate=datetime(2024, 1, 1),
    maxDate=datetime(2024, 12, 31),
)
```

### DatePickerInput
Input that opens calendar dropdown.
```python
DatePickerInput(
    name="date",
    label="Date",
    placeholder="Pick date",
    type="default",  # "default" | "multiple" | "range"
    valueFormat="MMM D, YYYY",
    clearable=True,
    dropdownType="popover",  # "popover" | "modal"
    allowDeselect=True,
)
```

### DateTimePicker
Combined date and time picker.
```python
DateTimePicker(
    name="datetime",
    label="Date & Time",
    placeholder="Pick date and time",
    valueFormat="DD MMM YYYY hh:mm A",
    withSeconds=False,
)
```

### MonthPickerInput
Month selection.
```python
MonthPickerInput(
    name="month",
    label="Month",
    placeholder="Pick month",
    type="default",  # "default" | "multiple" | "range"
    valueFormat="MMMM YYYY",
)
```

### YearPickerInput
Year selection.
```python
YearPickerInput(
    name="year",
    label="Year",
    placeholder="Pick year",
    type="default",
    minDate=datetime(2020, 1, 1),
    maxDate=datetime(2030, 1, 1),
)
```

## Time Inputs

### TimeInput
Simple time input.
```python
TimeInput(
    name="time",
    label="Time",
    withSeconds=False,
)
```

### TimePicker
Time picker with dropdown.
```python
TimePicker(
    name="time",
    label="Time",
    format="12h",  # "12h" | "24h"
    withSeconds=True,
    clearable=True,
)
```

### TimeGrid
Grid of time slots.
```python
TimeGrid(
    data=[
        "9:00 AM", "9:30 AM", "10:00 AM",
        "10:30 AM", "11:00 AM", "11:30 AM",
    ],
    value=selected,
    onChange=set_selected,
    cols=3,
    simpleGridProps={"spacing": "xs"},
)
```

## Calendar Components

### Calendar
Full calendar display.
```python
Calendar(
    getDayProps=lambda date: {"selected": date == selected, "onClick": lambda: select(date)},
    minDate=datetime(2024, 1, 1),
    maxDate=datetime(2024, 12, 31),
    excludeDate=lambda d: d.weekday() in [5, 6],  # exclude weekends
    firstDayOfWeek=1,  # Monday
    weekendDays=[5, 6],
    hideOutsideDates=True,
    hideWeekdays=False,
)
```

### MiniCalendar
Compact calendar.
```python
MiniCalendar(
    value=selected_date,
    onChange=set_selected,
)
```

### DatePicker (inline)
Inline date picker (no input).
```python
DatePicker(
    type="default",  # "default" | "multiple" | "range"
    value=date,
    onChange=set_date,
    allowDeselect=True,
    numberOfColumns=2,  # side by side months
)
```

### MonthPicker (inline)
Inline month picker.
```python
MonthPicker(
    type="default",
    value=month,
    onChange=set_month,
)
```

### YearPicker (inline)
Inline year picker.
```python
YearPicker(
    type="range",
    value=[start_year, end_year],
    onChange=set_range,
)
```

## Common Props

All date pickers share these props:

```python
# Value/onChange
value=date_value,
onChange=set_date,
defaultValue=datetime.now(),

# Constraints
minDate=datetime(2024, 1, 1),
maxDate=datetime(2024, 12, 31),
excludeDate=lambda d: d.weekday() == 6,  # exclude Sundays

# Display
valueFormat="MMMM D, YYYY",
locale="en",
firstDayOfWeek=0,  # 0=Sunday, 1=Monday
weekendDays=[0, 6],
hideOutsideDates=True,
hideWeekdays=False,

# Input props
label="Date",
placeholder="Pick a date",
description="Select your date",
error="Invalid date",
withAsterisk=True,
clearable=True,
disabled=False,
readOnly=False,

# Dropdown props
dropdownType="popover",  # or "modal"
popoverProps={"shadow": "md"},
modalProps={"title": "Pick date"},
```

## Type Variants

### Single Date
```python
DatePickerInput(type="default", value=date, onChange=set_date)
```

### Multiple Dates
```python
DatePickerInput(
    type="multiple",
    value=[date1, date2, date3],  # list of dates
    onChange=set_dates,
)
```

### Date Range
```python
DatePickerInput(
    type="range",
    value=[start_date, end_date],  # [start, end] tuple
    onChange=set_range,
    allowSingleDateInRange=True,
)
```

## Date Format Strings

Uses dayjs format:

| Token | Output | Description |
|-------|--------|-------------|
| `YYYY` | 2024 | 4-digit year |
| `YY` | 24 | 2-digit year |
| `MMMM` | January | Full month |
| `MMM` | Jan | Short month |
| `MM` | 01 | 2-digit month |
| `M` | 1 | Month number |
| `DD` | 01 | 2-digit day |
| `D` | 1 | Day number |
| `dddd` | Monday | Full weekday |
| `ddd` | Mon | Short weekday |
| `HH` | 00-23 | 24-hour |
| `hh` | 01-12 | 12-hour |
| `mm` | 00-59 | Minutes |
| `ss` | 00-59 | Seconds |
| `A` | AM/PM | Uppercase |
| `a` | am/pm | Lowercase |

## Form Integration

All date inputs work with MantineForm:

```python
form = MantineForm(
    initialValues={
        "startDate": None,
        "endDate": None,
    },
    validate={
        "startDate": IsDate("Invalid date"),
        "endDate": [
            IsDate("Invalid date"),
            IsAfter("startDate", error="Must be after start date"),
        ],
    },
)

form.render(onSubmit=handle)[
    DatePickerInput(name="startDate", label="Start"),
    DatePickerInput(name="endDate", label="End"),
]
```

## Examples

### Date Range Picker
```python
@ps.component
def DateRangePicker():
    with ps.init():
        form = MantineForm(
            initialValues={"range": [None, None]},
            validate={
                "range": lambda v: None if v and v[0] and v[1] else "Select range",
            },
        )

    return form.render(onSubmit=print)[
        DatePickerInput(
            name="range",
            type="range",
            label="Select date range",
            placeholder="Pick dates",
            clearable=True,
        ),
        Button("Submit", type="submit"),
    ]
```

### Appointment Scheduler
```python
@ps.component
def AppointmentPicker():
    with ps.init():
        form = MantineForm(
            initialValues={"date": None, "time": None},
        )

    return form.render(onSubmit=handle)[
        Stack(gap="md")[
            DatePickerInput(
                name="date",
                label="Date",
                excludeDate=lambda d: d.weekday() in [5, 6],  # weekdays only
                minDate=datetime.now(),
            ),
            TimeGrid(
                data=["9:00 AM", "10:00 AM", "11:00 AM", "2:00 PM", "3:00 PM"],
                cols=3,
            ),
        ],
    ]
```

### Multi-Calendar Range
```python
DatePickerInput(
    type="range",
    label="Trip Dates",
    numberOfColumns=2,
    popoverProps={"width": "auto"},
)
```
