# Pulse Recharts

Python bindings for Recharts React charting library.

## Architecture

Typed Python wrappers around Recharts components. Charts are rendered to VDOM and sent to the client.

```
Python Chart → VDOM → pulse-client → recharts (React)
```

## Folder Structure

```
src/pulse_recharts/
├── __init__.py     # Public exports
├── charts.py       # Chart containers (LineChart, BarChart, etc.)
├── cartesian.py    # Cartesian components (XAxis, YAxis, Line, Bar, etc.)
├── general.py      # General components (Tooltip, Legend, Label, etc.)
├── common.py       # Common types (DataKey, Margin, etc.)
└── shapes.py       # Shape components (Curve)
```

## Usage

```python
from pulse_recharts import (
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
    ResponsiveContainer
)

data = [
    {"name": "Jan", "uv": 4000, "pv": 2400},
    {"name": "Feb", "uv": 3000, "pv": 1398},
    {"name": "Mar", "uv": 2000, "pv": 9800},
]

def chart():
    return ResponsiveContainer(width="100%", height=300, children=[
        LineChart(data=data, children=[
            CartesianGrid(strokeDasharray="3 3"),
            XAxis(dataKey="name"),
            YAxis(),
            Tooltip(),
            Legend(),
            Line(type="monotone", dataKey="pv", stroke="#8884d8"),
            Line(type="monotone", dataKey="uv", stroke="#82ca9d"),
        ])
    ])
```

## Components

### Chart Containers
- `LineChart`, `BarChart`, `AreaChart`
- `PieChart`, `RadarChart`, `RadialBarChart`
- `ScatterChart`, `FunnelChart`, `ComposedChart`

### Cartesian
- `XAxis`, `YAxis` - axes
- `CartesianGrid` - grid lines
- `Line`, `Bar`, `Area` - data series

### General
- `ResponsiveContainer` - responsive wrapper
- `Tooltip` - hover tooltips
- `Legend` - chart legend
- `Label`, `LabelList` - data labels
- `Text` - text rendering

### Shapes
- `Curve` - curve shapes

## Roadmap

- [ ] Area, Scatter series components
- [ ] ZAxis, Brush, ReferenceLine
- [ ] Polar components (Pie, Radar, RadialBar axes)
- [ ] All shape components (Dot, Rectangle, Sector)
- [ ] Custom render function support
