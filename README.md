# Pulse

> [!WARNING]
> Pulse is close to feature-complete, but not yet ready for broader usage. I'm currently using for private applications, in order to nail down the design. If you wish to follow along, please say hi

Pulse is a full-stack Python framework to build interactive web applications, with full access to the JavaScript ecosystem. Think of it as building a React application, but in Python.

Actually, Pulse is based on React and interoperates easily with all React libraries, giving you access to the largest JavaScript ecosystem.

Pulse's guiding principles are:

- **Simplicity.** It's "just Python". Pulse tries really hard to avoid surprises and magic.
- **Performance.** Pulse starts fast, renders fast, _feels_ fast. You should only be limited by your architecture and network latency.
- **Seamless client-server integration.** You can fetch data and render a page from it, Pulse only sends what is displayed and you never have to think about it.
- **High ceiling.** You can build any online application in Pulse.
- **Essentials built-in.** Pulse is not prescriptive, but it aims to be comprehensive. It won't tell you how to build your authentication, but it will provide you with forms, queries, middleware, and all the hooks needed to extend the framework.
- **JavaScript as a first class citizen.** JavaScript code is never hidden, interoperability is easy. You can live anywhere between Python-only to working side-by-side with web developers.
- **Excellent developer experience.** In addition to a great API, Pulse's dev server provides hot reloads and built-in development tooling, like latency controls.

There is a tutorial at https://github.com/erwinkn/pulse-ui-tutorial. Real docs are coming soon as well, stay tuned!

## Example

Here's a simple TODO list example using Tailwind CSS for styling. 

```python
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

```

## Comparisons

It may be easier to understand Pulse by comparing it to frameworks you already know:

| Framework                 | Comparison with Pulse                                                                                                                                                                                                                                                       |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Flask / Django            | Traditional Python web frameworks that handle routing and server-side rendering. Pulse builds on these patterns but adds real-time interactivity and client-side rendering without writing JavaScript.                                                                      |
| Streamlit                 | Like Streamlit, Pulse lets you build web UIs in pure Python. But Pulse gives you full control over your application architecture and styling, integrates with the React ecosystem, and scales better for complex applications.                                              |
| Reflex                    | Similar goals of building React-like apps in Python. Pulse embraces a simpler mental model of "write regular Python code", whereas Reflex wants to compile your whole Python code to React. In addition, Pulse treats JavaScript interoperability as a first-class citizen. |
| Phoenix LiveView (Elixir) | LiveView pioneered server-driven UI updates over WebSocket. Pulse brings similar capabilities to Python while embracing React's component model and ecosystem.                                                                                                              |
| React                     | Pulse uses React under the hood and provides full access to the React ecosystem. The key difference is that you write your components in Python, your code runs on the server, and controls your user's browser through WebSockets.                                         |
