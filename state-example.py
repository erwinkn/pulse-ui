#!/usr/bin/env python3
"""
Example demonstrating Pulse's reactive state system.

This example shows how to:
1. Define reactive state classes using pulse.State
2. Use pulse.init() for route initialization  
3. Render routes with automatic state tracking
4. Trigger re-renders when state changes
"""

import pulse as ps


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


@app.route("/")
def home():
    # Initialize state - only called once per route
    state = ps.init(lambda: CounterState())
    
    return ps.div(
        ps.h1(f"Welcome to {state.name}!"),
        ps.p(f"Current count: {state.count}"),
        ps.button(
            "Increment", 
            onclick=lambda: setattr(state, 'count', state.count + 1),
            disabled=not state.enabled
        ),
        ps.button(
            "Reset", 
            onclick=lambda: setattr(state, 'count', 0)
        ),
        ps.label(
            ps.input(
                type="checkbox", 
                checked=state.enabled,
                onchange=lambda: setattr(state, 'enabled', not state.enabled)
            ),
            "Enable counter"
        )
    )


@app.route("/todos")
def todos():
    # Initialize todo state
    state = ps.init(lambda: TodoState())
    
    # Filter items based on state
    if state.filter_completed:
        visible_items = [item for item in state.items if item.get('completed', False)]
    else:
        visible_items = state.items
    
    return ps.div(
        ps.h1("Todo List"),
        ps.div(
            ps.input(
                type="text", 
                placeholder="Add new todo...",
                onkeydown=lambda e: add_todo(state, e.target.value) if e.key == 'Enter' else None
            ),
            ps.button(
                "Add Todo",
                onclick=lambda: add_todo(state, "New Todo")
            )
        ),
        ps.label(
            ps.input(
                type="checkbox",
                checked=state.filter_completed,
                onchange=lambda: setattr(state, 'filter_completed', not state.filter_completed)
            ),
            "Show only completed"
        ),
        ps.ul(*[
            ps.li(
                ps.span(item['text'], style={"text-decoration": "line-through" if item.get('completed') else "none"}),
                ps.button("Toggle", onclick=lambda i=i: toggle_todo(state, i)),
                ps.button("Delete", onclick=lambda i=i: delete_todo(state, i)),
                key=f"todo-{i}"
            ) for i, item in enumerate(visible_items)
        ])
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
        new_items[index]['completed'] = not new_items[index].get('completed', False)
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
    updates_received = []
    
    def on_update(updates):
        """Callback to receive VDOM updates."""
        print(f"Received {len(updates)} VDOM updates:")
        for update in updates:
            print(f"  - {update['type']}: {update.get('path', 'root')}")
            print("  --- Payload ---")
            print(update['data'])
        updates_received.extend(updates)
    
    # Render the home route
    print("\n1. Rendering home route...")
    active_route = app.render_route("/", on_update)
    print(f"Initial VDOM: {active_route.vdom.tag if active_route.vdom else 'None'}")
    
    # Access the state and modify it
    print("\n2. Accessing and modifying state...")
    if active_route.state:
        print(f"Initial count: {active_route.state.count}")
        print(f"Initial name: {active_route.state.name}")
        
        # Modify state - this should trigger a re-render
        active_route.state.count = 5
        print(f"Updated count to: {active_route.state.count}")
        
        # Modify name - this should also trigger a re-render  
        active_route.state.name = "Updated Counter"
        print(f"Updated name to: {active_route.state.name}")
    
    print(f"\n3. Total updates received: {len(updates_received)}")
    
    # Test todo route
    print("\n4. Testing todo route...")
    todo_route = app.render_route("/todos", lambda updates: print(f"Todo updates: {len(updates)}"))
    
    if todo_route.state:
        print("Adding some todo items...")
        add_todo(todo_route.state, "Learn Pulse")
        add_todo(todo_route.state, "Build awesome apps") 
        print(f"Todo items: {len(todo_route.state.items)}")
        
        # Toggle filter
        todo_route.state.filter_completed = True
        print(f"Filter completed: {todo_route.state.filter_completed}")
    
    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    demo_reactive_system()

