# Practical Examples

Copy-paste starting points for common Pulse patterns.

## 1. Counter

Simple reactive counter with increment/decrement.

```python
import pulse as ps

class Counter(ps.State):
    count: int = 0

    def inc(self): self.count += 1
    def dec(self): self.count -= 1

@ps.component
def CounterApp():
    with ps.init():
        state = Counter()

    return ps.div(className="p-4 space-x-2")[
        ps.button("-", onClick=state.dec, className="btn"),
        ps.span(str(state.count), className="text-xl"),
        ps.button("+", onClick=state.inc, className="btn"),
    ]

app = ps.App([ps.Route("/", CounterApp)])
```

## 2. Todo List

Basic todo with add/remove functionality.

```python
import pulse as ps

class Todos(ps.State):
    items: list[str] = []
    draft: str = ""

    def update(self, value: str): self.draft = value

    def add(self):
        if self.draft.strip():
            self.items.append(self.draft.strip())
            self.draft = ""

    def remove(self, index: int): self.items.pop(index)

@ps.component
def TodoApp():
    with ps.init():
        state = Todos()

    return ps.div(className="p-4 space-y-4")[
        ps.div(className="flex gap-2")[
            ps.input(
                value=state.draft,
                onChange=lambda e: state.update(e["target"]["value"]),
                placeholder="Add todo...",
                className="input flex-1",
            ),
            ps.button("Add", onClick=state.add, className="btn-primary"),
        ],
        ps.ul(className="space-y-2")[
            ps.For(
                state.items,
                lambda item, idx: ps.li(className="flex justify-between")[
                    ps.span(item),
                    ps.button("x", onClick=lambda: state.remove(idx), className="btn-sm"),
                ],
            ),
        ],
    ]

app = ps.App([ps.Route("/", TodoApp)])
```

## 3. Data Table with Queries

Table with server-side pagination using `@ps.query`.

```python
import asyncio
import pulse as ps

class UserTable(ps.State):
    page: int = 1
    page_size: int = 10

    @ps.query
    async def users(self) -> dict:
        await asyncio.sleep(0.2)  # Simulate API
        offset = (self.page - 1) * self.page_size
        items = [{"id": i, "name": f"User {i}"} for i in range(offset, offset + self.page_size)]
        return {"items": items, "total": 100}

    @users.key
    def _key(self): return ("users", self.page, self.page_size)

    def prev(self): self.page = max(1, self.page - 1)
    def next(self): self.page += 1

@ps.component
def TableApp():
    with ps.init():
        state = UserTable()

    data = state.users.data or {"items": [], "total": 0}

    return ps.div(className="p-4 space-y-4")[
        ps.div(className="flex gap-2")[
            ps.button("Prev", onClick=state.prev, disabled=state.page == 1, className="btn"),
            ps.span(f"Page {state.page}"),
            ps.button("Next", onClick=state.next, className="btn"),
        ],
        ps.table(className="w-full")[
            ps.thead()[ps.tr()[ps.th("ID"), ps.th("Name")]],
            ps.tbody()[
                ps.For(data["items"], lambda u, _: ps.tr(key=u["id"])[ps.td(u["id"]), ps.td(u["name"])])
            ],
        ],
        ps.p(f"Loading...") if state.users.is_loading else None,
    ]

app = ps.App([ps.Route("/", TableApp)])
```

## 4. Auth Flow

Login form with session management and protected routes.

```python
import pulse as ps
from fastapi.responses import JSONResponse

@ps.component
def LoginPage():
    with ps.init():
        email = ps.Signal("")
        password = ps.Signal("")

    async def submit():
        res = await ps.call_api("/api/login", method="POST", body={
            "email": email(), "password": password()
        })
        if res.get("ok"):
            ps.navigate("/dashboard")

    return ps.div(className="max-w-sm mx-auto p-6 space-y-4")[
        ps.h1("Login", className="text-2xl font-bold"),
        ps.input(
            type="email", placeholder="Email",
            onChange=lambda e: email.write(e["target"]["value"]),
            className="input w-full",
        ),
        ps.input(
            type="password", placeholder="Password",
            onChange=lambda e: password.write(e["target"]["value"]),
            className="input w-full",
        ),
        ps.button("Sign in", onClick=submit, className="btn-primary w-full"),
    ]

@ps.component
def Dashboard():
    sess = ps.session()
    if not sess.get("user"):
        ps.redirect("/login")

    async def logout():
        await ps.call_api("/api/logout", method="POST")
        ps.navigate("/login")

    return ps.div(className="p-6")[
        ps.h1(f"Welcome, {sess.get('user')}", className="text-2xl"),
        ps.button("Sign out", onClick=logout, className="btn-secondary"),
    ]

app = ps.App([ps.Route("/login", LoginPage), ps.Route("/dashboard", Dashboard)])

@app.fastapi.post("/api/login")
async def api_login(request):
    body = await request.json()
    ps.session()["user"] = body.get("email", "guest")
    return JSONResponse({"ok": True})

@app.fastapi.post("/api/logout")
async def api_logout():
    ps.session().pop("user", None)
    return JSONResponse({"ok": True})
```

## 5. Real-time Chat

Bidirectional communication using channels.

```python
import pulse as ps
from pulse.js.pulse import usePulseChannel

useState = ps.Import("useState", "react")
useEffect = ps.Import("useEffect", "react")

class ChatRoom(ps.State):
    messages: list[dict] = []

    def __init__(self):
        self.channel = ps.channel()
        self._cleanup = self.channel.on("client:send", self._on_send)

    def _on_send(self, payload: dict):
        msg = {"user": payload.get("user", "Anon"), "text": payload["text"]}
        self.messages.append(msg)
        self.channel.emit("server:message", msg)

    def on_dispose(self): self._cleanup()

@ps.javascript(jsx=True)
def ChatWidget(*, channelId: str):
    bridge = usePulseChannel(channelId)
    messages, setMessages = useState([])
    draft, setDraft = useState("")

    def subscribe():
        def onMsg(m): setMessages(lambda prev: [*prev, m])
        return bridge.on("server:message", onMsg)

    useEffect(subscribe, [bridge])

    def send():
        if draft.strip():
            bridge.emit("client:send", {"text": draft})
            setDraft("")

    return ps.div(className="space-y-4")[
        ps.div(className="h-64 overflow-y-auto border p-2")[
            ps.For(messages, lambda m, i: ps.div(f"{m['user']}: {m['text']}", key=str(i)))
        ],
        ps.div(className="flex gap-2")[
            ps.input(value=draft, onChange=lambda e: setDraft(e.target.value), className="input flex-1"),
            ps.button("Send", onClick=send, className="btn-primary"),
        ],
    ]

@ps.component
def ChatApp():
    with ps.init():
        room = ChatRoom()

    return ps.div(className="max-w-lg mx-auto p-4")[
        ps.h1("Chat Room", className="text-2xl font-bold mb-4"),
        ChatWidget(channelId=room.channel.id),
    ]

app = ps.App([ps.Route("/", ChatApp)])
```

## 6. File Upload Form

Form with file input and server-side handling.

```python
import pulse as ps
from fastapi import UploadFile

class UploadState(ps.State):
    uploads: list[dict] = []

    async def handle_upload(self, data: ps.FormData):
        file: UploadFile | None = data.get("file")
        if file:
            content = await file.read()
            self.uploads.append({
                "name": file.filename,
                "size": len(content),
                "type": file.content_type,
            })

@ps.component
def UploadApp():
    with ps.init():
        state = UploadState()

    return ps.div(className="max-w-md mx-auto p-6 space-y-6")[
        ps.h1("File Upload", className="text-2xl font-bold"),
        ps.Form(onSubmit=state.handle_upload)[
            ps.input(name="file", type="file", className="mb-4"),
            ps.button("Upload", type="submit", className="btn-primary"),
        ],
        ps.div(className="space-y-2")[
            ps.For(
                state.uploads,
                lambda f, i: ps.div(key=str(i), className="p-2 border rounded")[
                    ps.p(f["name"], className="font-medium"),
                    ps.p(f"{f['size']} bytes - {f['type']}", className="text-sm text-gray-500"),
                ],
            ),
        ],
    ]

app = ps.App([ps.Route("/", UploadApp)])
```

## 7. Infinite Scroll

Load more data on demand using `@ps.infinite_query`.

```python
import asyncio
import pulse as ps
from pulse.queries.infinite_query import Page

class Feed(ps.State):
    @ps.infinite_query(initial_page_param=0, max_pages=10)
    async def items(self, page: int):
        await asyncio.sleep(0.2)  # Simulate API
        return {
            "items": [{"id": f"{page}-{i}", "text": f"Item {page * 10 + i}"} for i in range(10)],
            "next": page + 1 if page < 5 else None,
        }

    @items.get_next_page_param
    def _next(self, pages: list[Page]) -> int | None:
        return pages[-1].data["next"] if pages else None

@ps.component
def FeedApp():
    with ps.init():
        state = Feed()

    query = state.items
    all_items = [item for page in (query.pages or []) for item in page["items"]]

    async def load_more():
        await query.fetch_next_page()

    return ps.div(className="max-w-md mx-auto p-4 space-y-4")[
        ps.h1("Infinite Feed", className="text-2xl font-bold"),
        ps.ul(className="space-y-2")[
            ps.For(all_items, lambda item, _: ps.li(item["text"], key=item["id"], className="p-2 border"))
        ],
        ps.button(
            "Loading..." if query.is_fetching_next_page else "Load more",
            onClick=load_more,
            disabled=not query.has_next_page or query.is_fetching_next_page,
            className="btn-primary w-full",
        ) if query.has_next_page else ps.p("No more items", className="text-center text-gray-500"),
    ]

app = ps.App([ps.Route("/", FeedApp)])
```
