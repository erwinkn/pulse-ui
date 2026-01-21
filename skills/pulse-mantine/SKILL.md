# Pulse Mantine

Mantine UI components for Pulse apps. Provides pre-styled React components.

## Installation

```bash
uv add pulse-mantine
```

## Usage

```python
import pulse as ps
from pulse_mantine import Button, TextInput, Card, Stack, Group

@ps.component
def LoginForm():
    state = ps.init(LoginState)
    return Card(
        Stack(
            TextInput(label="Email", value=state.email, on_change=lambda v: setattr(state, "email", v)),
            TextInput(label="Password", type="password", value=state.password, on_change=lambda v: setattr(state, "password", v)),
            Group(
                Button("Login", on_click=state.login),
                Button("Cancel", variant="outline"),
            ),
        )
    )
```

## Common Components

- `Button`, `ActionIcon`: Clickable actions
- `TextInput`, `NumberInput`, `Select`, `Checkbox`: Form inputs
- `Card`, `Paper`: Container elements
- `Stack`, `Group`, `Grid`: Layout components
- `Modal`, `Drawer`: Overlays
- `Table`, `Tabs`, `Accordion`: Data display

## Rules

- Import components from `pulse_mantine`
- Props mirror Mantine React props
- Use `Stack` for vertical layout, `Group` for horizontal
- Wrap forms in `Card` or `Paper` for visual grouping
