import pulse as ps


class Todos(ps.State):
    items: list[str] = []
    draft: str = ""

    def update(self, value: str):
        self.draft = value

    def add(self):
        text = self.draft.strip()
        if text:
            self.items.append(text)
            self.draft = ""

    def remove(self, index: int):
        if 0 <= index < len(self.items):
            self.items.pop(index)


@ps.component
def TodoApp():
    state = ps.states(Todos)

    return ps.div(className="min-h-screen bg-slate-950 text-slate-100 p-8")[
        ps.div(className="mx-auto max-w-sm space-y-4")[
            ps.div(className="space-y-1 text-center")[
                ps.h1("Todo list", className="text-2xl font-semibold"),
                ps.p(
                    "Add items and manage them with Pulse state.",
                    className="text-sm text-slate-400",
                ),
            ],
            ps.div(className="flex gap-2")[
                ps.input(
                    value=state.draft,
                    onChange=lambda event: state.update(event["target"]["value"]),
                    placeholder="What needs doing?",
                    className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2",
                ),
                ps.button(
                    "Add",
                    onClick=lambda: state.add(),
                    className="rounded bg-emerald-500 px-4 py-2 font-medium text-slate-900",
                ),
            ],
            ps.ul(className="space-y-2")[
                ps.For(
                    state.items,
                    lambda item, idx: ps.li(
                        className="flex items-center justify-between gap-3 rounded border border-slate-800 bg-slate-900 px-3 py-2",
                    )[
                        ps.span(item, className="truncate"),
                        ps.button(
                            "Done",
                            onClick=lambda: state.remove(idx),
                            className="rounded border border-emerald-500 px-2 py-1 text-xs text-emerald-300",
                        ),
                    ],
                ),
            ],
        ],
    ]


app = ps.App([ps.Route("/", TodoApp)])
