from pathlib import Path
import pulse as ps
from pulse_mantine import (
    MantineProvider,
    LineChart,
    AreaChart,
    PieChart,
    ChartLegend,
    ChartTooltip,
)


line_data = [
    {"name": "Jan", "uv": 4000, "pv": 2400},
    {"name": "Feb", "uv": 3000, "pv": 1398},
    {"name": "Mar", "uv": 2000, "pv": 9800},
    {"name": "Apr", "uv": 2780, "pv": 3908},
    {"name": "May", "uv": 1890, "pv": 4800},
    {"name": "Jun", "uv": 2390, "pv": 3800},
    {"name": "Jul", "uv": 3490, "pv": 4300},
]

pie_data = [
    {"name": "Group A", "value": 400, "color": "blue"},
    {"name": "Group B", "value": 300, "color": "green"},
    {"name": "Group C", "value": 300, "color": "grape"},
    {"name": "Group D", "value": 200, "color": "orange"},
]


@ps.component
def MantineChartsDemo():
    return MantineProvider()[
        ps.div(className="container mx-auto p-6 space-y-8")[
            ps.h1("Mantine Charts Demo", className="text-2xl font-bold"),
            ps.div(className="grid grid-cols-1 lg:grid-cols-2 gap-8")[
                ps.div(className="space-y-2")[
                    ps.h2("LineChart"),
                    LineChart(
                        h=300,
                        data=line_data,
                        series=[
                            {"name": "pv", "color": "blue"},
                            {"name": "uv", "color": "green"},
                        ],
                        withLegend=True,
                        withTooltip=True,
                    ),
                ],
                ps.div(className="space-y-2")[
                    ps.h2("AreaChart"),
                    AreaChart(
                        h=300,
                        data=line_data,
                        series=[
                            {"name": "pv", "color": "indigo"},
                            {"name": "uv", "color": "teal"},
                        ],
                        type="gradient",
                        withLegend=True,
                        withTooltip=True,
                    ),
                ],
                ps.div(className="space-y-2 lg:col-span-2")[
                    ps.h2("PieChart"),
                    PieChart(h=300, data=pie_data, withTooltip=True, withLabels=True),
                ],
            ],
        ]
    ]


app = ps.App(
    [ps.Route("/", MantineChartsDemo)],
)
