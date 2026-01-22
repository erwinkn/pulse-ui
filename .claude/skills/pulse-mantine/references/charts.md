# Mantine Charts

Chart components from `@mantine/charts`, built on Recharts.

## Data Format

All charts expect data as list of dicts:

```python
data = [
    {"date": "Jan", "sales": 100, "profit": 40},
    {"date": "Feb", "sales": 150, "profit": 60},
    {"date": "Mar", "sales": 200, "profit": 80},
]
```

## Line Chart

```python
LineChart(
    h=300,
    data=data,
    dataKey="date",  # x-axis key
    series=[
        {"name": "sales", "color": "blue.6"},
        {"name": "profit", "color": "green.6"},
    ],
    curveType="linear",  # "linear" | "natural" | "monotone" | "step"
    withLegend=True,
    legendProps={"verticalAlign": "bottom"},
    withTooltip=True,
    tooltipAnimationDuration=200,
    withDots=True,
    dotProps={"r": 4},
    strokeWidth=2,
    connectNulls=True,
    gridAxis="xy",  # "x" | "y" | "xy" | "none"
    tickLine="xy",
    withXAxis=True,
    withYAxis=True,
    xAxisLabel="Month",
    yAxisLabel="Amount",
    unit="$",
    valueFormatter=lambda v: f"${v:,.0f}",
)
```

## Area Chart

```python
AreaChart(
    h=300,
    data=data,
    dataKey="date",
    series=[
        {"name": "sales", "color": "blue.6"},
        {"name": "profit", "color": "green.6"},
    ],
    type="default",  # "default" | "stacked" | "percent" | "split"
    curveType="linear",
    withLegend=True,
    withGradient=True,  # gradient fill
    gradientStops=[
        {"offset": 0, "color": "blue.6", "opacity": 0.8},
        {"offset": 100, "color": "blue.6", "opacity": 0.1},
    ],
    fillOpacity=0.4,
    strokeWidth=2,
)
```

## Bar Chart

```python
BarChart(
    h=300,
    data=data,
    dataKey="date",
    series=[
        {"name": "sales", "color": "blue.6"},
        {"name": "profit", "color": "green.6"},
    ],
    type="default",  # "default" | "stacked" | "percent" | "waterfall"
    orientation="vertical",  # "vertical" | "horizontal"
    withLegend=True,
    barProps={"radius": 4},  # rounded corners
    withBarValueLabel=True,
    barValueLabelProps={"position": "top"},
)
```

## Pie Chart

```python
pie_data = [
    {"name": "USA", "value": 400, "color": "blue.6"},
    {"name": "India", "value": 300, "color": "green.6"},
    {"name": "Japan", "value": 200, "color": "orange.6"},
]

PieChart(
    h={300},
    data=pie_data,
    withLabels=True,
    labelsType="value",  # "value" | "percent"
    labelsPosition="outside",  # "inside" | "outside"
    withTooltip=True,
    strokeWidth=1,
    strokeColor="white",
)
```

## Donut Chart

```python
DonutChart(
    h={300},
    data=pie_data,
    withLabels=True,
    thickness={30},  # ring thickness
    chartLabel="Total: 900",  # center label
    paddingAngle={5},  # gap between segments
)
```

## Scatter Chart

```python
scatter_data = [
    {"x": 10, "y": 20, "z": 100},  # z for bubble size
    {"x": 20, "y": 30, "z": 150},
    {"x": 30, "y": 10, "z": 200},
]

ScatterChart(
    h=300,
    data={"Product A": scatter_data, "Product B": other_data},
    dataKey={"x": "x", "y": "y"},
    xAxisLabel="Price",
    yAxisLabel="Sales",
    withLegend=True,
)
```

## Bubble Chart

```python
BubbleChart(
    h=300,
    data=bubble_data,
    dataKey={"x": "gdp", "y": "lifeExpectancy", "z": "population"},
    range=[10, 60],  # bubble size range
    xAxisLabel="GDP",
    yAxisLabel="Life Expectancy",
)
```

## Radar Chart

```python
radar_data = [
    {"skill": "React", "you": 80, "average": 60},
    {"skill": "Python", "you": 90, "average": 70},
    {"skill": "SQL", "you": 70, "average": 65},
    {"skill": "Design", "you": 50, "average": 55},
]

RadarChart(
    h=300,
    data=radar_data,
    dataKey="skill",
    series=[
        {"name": "you", "color": "blue.6", "opacity": 0.2},
        {"name": "average", "color": "gray.6", "opacity": 0.1},
    ],
    withPolarGrid=True,
    withPolarAngleAxis=True,
    withPolarRadiusAxis=True,
)
```

## Radial Bar Chart

```python
radial_data = [
    {"name": "Apples", "value": 47, "color": "red.6"},
    {"name": "Oranges", "value": 33, "color": "orange.6"},
    {"name": "Grapes", "value": 20, "color": "grape.6"},
]

RadialBarChart(
    h={300},
    data=radial_data,
    dataKey="value",
    withLabels=True,
    withLegend=True,
)
```

## Funnel Chart

```python
funnel_data = [
    {"name": "Visits", "value": 5000, "color": "blue.6"},
    {"name": "Leads", "value": 3000, "color": "cyan.6"},
    {"name": "Qualified", "value": 1500, "color": "teal.6"},
    {"name": "Closed", "value": 500, "color": "green.6"},
]

FunnelChart(
    h={300},
    data=funnel_data,
    withLabels=True,
    withTooltip=True,
)
```

## Composite Chart

Mix multiple chart types:

```python
CompositeChart(
    h=300,
    data=data,
    dataKey="date",
    series=[
        {"name": "sales", "color": "blue.6", "type": "bar"},
        {"name": "trend", "color": "red.6", "type": "line"},
    ],
    withLegend=True,
)
```

## Sparkline

Compact inline chart:

```python
Sparkline(
    w={200},
    h={60},
    data=[10, 20, 40, 20, 40, 10, 50],
    curveType="linear",
    color="blue.6",
    fillOpacity={0.2},
    strokeWidth={2},
    trendColors={"positive": "green.6", "negative": "red.6", "neutral": "gray.6"},
)
```

## Heatmap

```python
heatmap_data = [
    {"x": "Mon", "y": "9am", "value": 10},
    {"x": "Mon", "y": "10am", "value": 20},
    {"x": "Tue", "y": "9am", "value": 30},
    # ...
]

Heatmap(
    h={300},
    data=heatmap_data,
    dataKey={"x": "x", "y": "y", "value": "value"},
    colors=["blue.1", "blue.3", "blue.5", "blue.7", "blue.9"],
    withTooltip=True,
    withLegend=True,
)
```

## Common Props

### Sizing
```python
h=300,  # height (required)
w="100%",  # width (optional, defaults to 100%)
```

### Legend
```python
withLegend=True,
legendProps={
    "verticalAlign": "bottom",  # "top" | "bottom"
    "align": "center",  # "left" | "center" | "right"
},
```

### Tooltip
```python
withTooltip=True,
tooltipAnimationDuration=200,
tooltipProps={"wrapperStyle": {...}},
```

### Axis
```python
withXAxis=True,
withYAxis=True,
xAxisLabel="Label",
yAxisLabel="Label",
xAxisProps={...},
yAxisProps={...},
gridAxis="xy",  # "x" | "y" | "xy" | "none"
tickLine="xy",  # "x" | "y" | "xy" | "none"
```

### Formatting
```python
unit="$",  # append to values
valueFormatter=lambda v: f"${v:,.0f}",  # custom format
```

### Reference Lines
```python
referenceLines=[
    {"y": 500, "label": "Target", "color": "red.6"},
    {"x": "Mar", "label": "Launch", "color": "green.6"},
],
```

## Custom Tooltip/Legend

```python
from pulse_mantine import ChartTooltip, ChartLegend

LineChart(
    ...,
    tooltipProps={
        "content": ChartTooltip(
            formatter=lambda payload, label: f"{label}: {payload['value']}"
        ),
    },
    legendProps={
        "content": ChartLegend(formatter=lambda entry: entry["value"].upper()),
    },
)
```

## Series Configuration

Each series in the `series` list:

```python
series=[
    {
        "name": "sales",       # data key
        "label": "Total Sales", # legend label (optional)
        "color": "blue.6",
        "strokeDasharray": "5 5",  # dashed line
    },
]
```

## Example: Dashboard Chart

```python
@ps.component
def SalesChart():
    data = [
        {"month": "Jan", "revenue": 4000, "profit": 2400, "target": 3000},
        {"month": "Feb", "revenue": 3000, "profit": 1398, "target": 3000},
        {"month": "Mar", "revenue": 5000, "profit": 3800, "target": 3000},
        {"month": "Apr", "revenue": 4780, "profit": 3908, "target": 3500},
        {"month": "May", "revenue": 5890, "profit": 4800, "target": 3500},
        {"month": "Jun", "revenue": 4390, "profit": 3800, "target": 4000},
    ]

    return Card(withBorder=True, p="md")[
        Title(order=4, mb="md")["Monthly Performance"],
        CompositeChart(
            h=300,
            data=data,
            dataKey="month",
            series=[
                {"name": "revenue", "color": "blue.6", "type": "bar"},
                {"name": "profit", "color": "green.6", "type": "bar"},
                {"name": "target", "color": "red.6", "type": "line", "strokeDasharray": "5 5"},
            ],
            withLegend=True,
            legendProps={"verticalAlign": "bottom"},
            withTooltip=True,
            valueFormatter=lambda v: f"${v:,}",
            referenceLines=[{"y": 3500, "color": "gray.5", "label": "Avg Target"}],
        ),
    ]
```
