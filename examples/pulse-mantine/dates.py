from pathlib import Path
import pulse as ps
from pulse_mantine import (
    MantineProvider,
    DatePickerInput,
    DateTimePicker,
    TimeInput,
    Calendar,
    MonthPickerInput,
    DatesProvider,
)


@ps.component
def MantineDatesDemo():
    return MantineProvider()[
        ps.div(className="container mx-auto p-6 space-y-6")[
            ps.h1("Mantine Dates Demo", className="text-2xl font-bold"),
            DatesProvider(settings={"locale": "en", "firstDayOfWeek": 1})[
                ps.div(className="grid grid-cols-1 md:grid-cols-2 gap-6")[
                    ps.div(
                        ps.h2("DatePickerInput"),
                        DatePickerInput(label="Pick date", placeholder="Select date"),
                        className="space-y-2",
                    ),
                    ps.div(
                        ps.h2("DateTimePicker"),
                        DateTimePicker(
                            label="Pick date & time",
                            placeholder="Select date and time",
                        ),
                        className="space-y-2",
                    ),
                    ps.div(
                        ps.h2("TimeInput"),
                        TimeInput(label="Time", withSeconds=False),
                        className="space-y-2",
                    ),
                    ps.div(
                        ps.h2("MonthPickerInput"),
                        MonthPickerInput(label="Month", placeholder="Select month"),
                        className="space-y-2",
                    ),
                    ps.div(
                        ps.h2("Calendar"),
                        Calendar(),
                        className="space-y-2",
                    ),
                ]
            ],
        ]
    ]


app = ps.App(
    [ps.Route("/", MantineDatesDemo)],
)
