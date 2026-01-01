# Pulse Lucide

Python bindings for Lucide React icons. Auto-generated from lucide-react.

## Architecture

Lazy-loaded Python wrappers around lucide-react icon components. Icons are instantiated on first access.

```
Python Icon → ReactComponent → VDOM → pulse-client → lucide-react
```

## Folder Structure

```
src/pulse_lucide/
├── __init__.py    # Auto-generated icon exports (1600+ icons)
└── props.py       # LUCIDE_PROPS_SPEC - icon prop definitions

scripts/
└── generate.py    # Generates __init__.py from lucide-react
```

## Usage

```python
from pulse_lucide import Heart, Search, Settings, ChevronRight

def toolbar():
    return ps.div([
        Heart(size=24, color="red"),
        Search(size=20),
        Settings(size=20, strokeWidth=1.5),
    ])
```

## Props

All icons accept these props:

- `size` - icon size (number or string)
- `color` - stroke color
- `strokeWidth` - line thickness (default: 2)
- `absoluteStrokeWidth` - maintain stroke width regardless of size

## Icon Count

1600+ icons available. Full list at [lucide.dev/icons](https://lucide.dev/icons).

Common icons:
- Navigation: `ChevronLeft`, `ChevronRight`, `ArrowUp`, `ArrowDown`, `Menu`, `X`
- Actions: `Search`, `Plus`, `Minus`, `Edit`, `Trash`, `Save`, `Download`, `Upload`
- Status: `Check`, `AlertCircle`, `Info`, `HelpCircle`, `Bell`, `Star`
- Files: `File`, `Folder`, `FileText`, `Image`, `Video`, `Music`
- User: `User`, `Users`, `UserPlus`, `Settings`, `LogIn`, `LogOut`

## Generation

Icons are auto-generated from lucide-react:

```bash
uv run scripts/generate.py
```
