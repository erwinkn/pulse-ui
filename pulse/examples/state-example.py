#!/usr/bin/env python3
"""
Example demonstrating Pulse's reactive state system.

This example shows how to:
1. Define reactive state classes using pulse.State
2. Use pulse.init() for route initialization
3. Render routes with automatic state tracking
4. Trigger re-renders when state changes
"""

import json
import pulse as ps
from pulse.app import VDOMUpdate


# Define reactive state classes using dataclass-style syntax
class CounterState(ps.State):
    count: int = 0
    name: str = "My Counter"
    enabled: bool = True


class TodoState(ps.State):
    items: list = []
    filter_completed: bool = False


# Create the app
app = ps.App()


RENDER_CALLBACKS = True


@app.route("/")
def home():
    # Initialize state - only called once per route
    state = ps.init(lambda: CounterState())
    if RENDER_CALLBACKS:
        print("Rendering callbacks")
    else:
        print("Not rendering callbacks")

    return ps.div(
        ps.h1(f"Welcome to {state.name}!"),
        ps.p(f"Current count: {state.count}"),
        ps.button(
            "Increment",
            onclick=lambda: setattr(state, "count", state.count + 1)
            if RENDER_CALLBACKS
            else None,
            disabled=not state.enabled,
        ),
        ps.button("Reset", onclick=lambda: setattr(state, "count", 0)),
        ps.label(
            ps.input(
                type="checkbox",
                checked=state.enabled,
                onchange=lambda: setattr(state, "enabled", not state.enabled)
                if RENDER_CALLBACKS
                else None,
            ),
            "Enable counter",
        ),
    )


@app.route("/todos")
def todos():
    # Initialize todo state
    state = ps.init(lambda: TodoState())

    # Filter items based on state
    if state.filter_completed:
        visible_items = [item for item in state.items if item.get("completed", False)]
    else:
        visible_items = state.items

    return ps.div(
        ps.h1("Todo List"),
        ps.div(
            ps.input(
                type="text",
                placeholder="Add new todo...",
                onkeydown=lambda e: add_todo(state, e.target.value)
                if e.key == "Enter"
                else None,
            ),
            ps.button("Add Todo", onclick=lambda: add_todo(state, "New Todo")),
        ),
        ps.label(
            ps.input(
                type="checkbox",
                checked=state.filter_completed,
                onchange=lambda: setattr(
                    state, "filter_completed", not state.filter_completed
                ),
            ),
            "Show only completed",
        ),
        ps.ul(
            *[
                ps.li(
                    ps.span(
                        item["text"],
                        style={
                            "text-decoration": "line-through"
                            if item.get("completed")
                            else "none"
                        },
                    ),
                    ps.button("Toggle", onclick=lambda i=i: toggle_todo(state, i)),
                    ps.button("Delete", onclick=lambda i=i: delete_todo(state, i)),
                    key=f"todo-{i}",
                )
                for i, item in enumerate(visible_items)
            ]
        ),
    )


def add_todo(state: TodoState, text: str):
    """Add a new todo item."""
    if text.strip():
        new_items = state.items.copy()
        new_items.append({"text": text.strip(), "completed": False})
        state.items = new_items


def toggle_todo(state: TodoState, index: int):
    """Toggle completion status of a todo item."""
    new_items = state.items.copy()
    if 0 <= index < len(new_items):
        new_items[index]["completed"] = not new_items[index].get("completed", False)
        state.items = new_items


def delete_todo(state: TodoState, index: int):
    """Delete a todo item."""
    new_items = state.items.copy()
    if 0 <= index < len(new_items):
        new_items.pop(index)
        state.items = new_items


def demo_reactive_system():
    """
    Demonstrate the reactive state system by programmatically rendering routes
    and triggering state changes.
    """
    print("=== Pulse Reactive State System Demo ===")

    # Track updates received
    update_batches = []

    def index_update(update: VDOMUpdate):
        """Callback to receive VDOM updates."""
        print(f"Received {len(update.operations)} VDOM operations:")
        for op in update.operations:
            print(f"  - {op['type']}: {json.dumps(op, indent=2)}")
        print(
            f"  - Callbacks: add({', '.join(update.add_callbacks)}); remove({', '.join(update.remove_callbacks)})"
        )
        update_batches.append(update)

    # Render the home route
    session = app.create_session("test")
    print("\n1. Rendering home route...")
    disconnect_index_update = session.connect(index_update)
    vdom = session.render("/")
    assert session.current_route == "/"
    print(f"Initial VDOM: {vdom.tag if vdom else 'None'}")

    # Access the state and modify it
    print("\n2. Accessing and modifying state...")
    if state := session.ctx.init.state:
        print("Route state:", state)
        print(f"Initial count: {state.count}")
        print(f"Initial name: {state.name}")

        # Modify state - this should trigger a re-render
        global RENDER_CALLBACKS
        RENDER_CALLBACKS = False
        state.count = 5
        print(f"Updated count to: {state.count}")

        # Modify name - this should also trigger a re-render
        state.name = "Updated Counter"
        print(f"Updated name to: {state.name}")

    print(f"\n3. Total updates received: {len(update_batches)}")
    disconnect_index_update()

    # Test todo route
    print("\n4. Testing todo route...")

    def todo_update(update: VDOMUpdate):
        return print(f"Todo update batch: {len(update.operations)} ops")

    disconnect_todo_update = session.connect(todo_update)
    session.render("/todos")

    assert session.current_route == "/todos"
    if state := session.ctx.init.state:
        print("Adding some todo items...")
        add_todo(state, "Learn Pulse")
        add_todo(state, "Build awesome apps")
        print(f"Todo items: {len(state.items)}")

        # Toggle filter
        state.filter_completed = True
        print(f"Filter completed: {state.filter_completed}")
    disconnect_todo_update()

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    demo_reactive_system()
