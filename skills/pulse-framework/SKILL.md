# Pulse Framework

Full-stack Python framework for interactive web apps. Runs on React with WebSocket-driven UI updates.

## Key APIs

- `ps.App`, `ps.Route`: Define app and routes
- `ps.State`: Reactive state class
- `@ps.component`: Decorator for components
- `ps.init()`: Hook to preserve state across renders
- `ps.setup()`: Run setup function once on first render
- `ps.query`: Async data fetching with loading states

## Commands

```bash
uv run pulse run app.py  # Start dev server on :8000
make all                 # Format, lint, typecheck, test
```

## Patterns

### Component with State

```python
import pulse as ps

class CounterState(ps.State):
    count: int = 0

@ps.component
def Counter():
    state = ps.init(CounterState)
    return ps.div(
        ps.button("Increment", on_click=lambda: setattr(state, "count", state.count + 1)),
        ps.span(f"Count: {state.count}"),
    )
```

### Query for Data Fetching

```python
@ps.component
def UserList():
    users = ps.query(fetch_users)
    if users.is_loading:
        return ps.div("Loading...")
    return ps.ul([ps.li(u.name) for u in users.data])
```

## Rules

- Use `@ps.component` for all components
- Define state as classes inheriting from `ps.State`
- Use `ps.init()` to preserve state across renders
- Run `make all` before committing
