# Pulse Mantine

Python and JavaScript bindings for [Mantine UI](https://mantine.dev/), a React component library.

## Overview

Provides typed Python wrappers for Mantine components, plus a custom form system with client-side validation.

**Implements:**
- `@mantine/core` - all UI components
- `@mantine/form` - custom wrapper with Python-JS validation sync
- `@mantine/dates` - date/time pickers
- `@mantine/charts` - charts (built on Recharts)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Python                                                         │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│  │ pulse_mantine  │──│ MantineForm     │──│ Validators       │  │
│  │ (components)   │  │ (state)         │  │ (dual-run)       │  │
│  └────────────────┘  └─────────────────┘  └──────────────────┘  │
│          │                    │                    │            │
│          └────────────────────┴────────────────────┘            │
│                              │                                  │
│                              ▼ VDOM                             │
└──────────────────────────────┼──────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│  JavaScript                  ▼                                  │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│  │ pulse-mantine  │──│ @mantine/form   │──│ Client validators│  │
│  │ (form bridge)  │  │ (useForm)       │  │ (JS)             │  │
│  └────────────────┘  └─────────────────┘  └──────────────────┘  │
│          │                                                      │
│          ▼                                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  @mantine/core, @mantine/dates, @mantine/charts            │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Structure

```
pulse-mantine/
├── python/              # Python bindings
│   └── src/pulse_mantine/
│       ├── core/        # @mantine/core components
│       ├── charts/      # @mantine/charts
│       ├── dates/       # @mantine/dates
│       └── form/        # MantineForm wrapper + validators
│
├── js/                  # JavaScript bridge
│   └── src/
│       ├── form/        # Form state management
│       ├── dates.tsx    # Date handling
│       └── notifications.tsx
│
└── TUTORIAL.md          # Detailed form usage guide
```

## Quick Start

```python
from pulse_mantine import (
    MantineProvider, Button, TextInput, Stack, MantineForm, IsEmail
)

@ps.component
def app():
    form = ps.states(lambda: MantineForm(
        initialValues={"email": ""},
        validate={"email": IsEmail("Invalid email")},
    ))

    return MantineProvider()[
        form.render(onSubmit=lambda v: print(v))[
            Stack()[
                TextInput(name="email", label="Email"),
                Button("Submit", type="submit"),
            ]
        ]
    ]
```

## Documentation

- **[TUTORIAL.md](./TUTORIAL.md)** - detailed guide for forms, validation, dynamic forms
- **[Mantine docs](https://mantine.dev/)** - official component reference
- **[python/README.md](./python/README.md)** - Python package details
- **[js/README.md](./js/README.md)** - JS package details
