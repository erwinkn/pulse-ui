# Building a Task Manager with Pulse

Welcome to the comprehensive Pulse tutorial! In this guide, we'll build a complete task management application that demonstrates all the key concepts of the Pulse framework. By the end, you'll understand how to create interactive, full-stack Python applications with reactive state management.

## What We're Building

Our task manager will feature:
- ✅ Task creation with categories
- ✅ Real-time updates and state synchronization  
- ✅ Change history tracking for every modification
- ✅ Dynamic routing with individual task pages
- ✅ Query-based data loading with caching
- ✅ Component-based architecture with reusable pieces

## Prerequisites

- Python 3.8+ with basic Python knowledge
- Familiarity with web development concepts (HTML, CSS, basic JavaScript)
- Understanding of async/await in Python

## Getting Started

First, let's run the finished application to see what we're building:

```bash
python tutorial.py
```

Open your browser and explore the different features. Notice how the UI updates instantly, data persists across page navigation, and changes are tracked with timestamps.

---

# Chapter 1: Defining Your App

Every Pulse application starts with defining the app structure and routes.

## App Definition

```python
import pulse as ps
from pathlib import Path
from pulse.codegen import CodegenConfig

app = ps.App(
    routes=[
        ps.Layout(
            app_layout,
            children=[
                ps.Route("/", home),
                ps.Route("/task/:id", task_details),
                ps.Route("/settings", settings),
            ],
        )
    ],
    codegen=CodegenConfig(web_dir=Path(__file__).parent / "pulse-demo"),
)
```

**Key concepts:**
- `ps.App()` creates your application
- `ps.Layout()` defines a shared layout component for all child routes
- `ps.Route()` maps URL paths to components
- Dynamic routes use `:param` syntax (e.g., `/task/:id`)
- `CodegenConfig` specifies where to generate the frontend code

---

# Chapter 2: Components and Basic HTML

Components are the building blocks of your Pulse UI. They return HTML elements and can accept parameters.

## Your First Component

```python
@ps.component
def home():
    """A simple home page component."""
    return ps.div(
        ps.h1("Task Manager", className="text-3xl font-bold mb-6"),
        ps.p("Welcome to your task manager!"),
        className="p-6"
    )
```

**Key concepts:**
- `@ps.component` decorator creates a reusable UI component
- Use `ps.div`, `ps.h1`, `ps.p` etc. for HTML elements
- `className` sets CSS classes (Tailwind CSS syntax)
- Components return a tree of HTML elements

## Layout Component

```python
@ps.component
def app_layout():
    """Main application layout with navigation."""
    return ps.div(
        ps.header(
            ps.h1("Pulse Task Manager", className="text-2xl font-bold"),
            ps.nav(
                ps.Link("Tasks", to="/", className="nav-link"),
                ps.Link("Settings", to="/settings", className="nav-link"),
                className="flex space-x-4"
            ),
            className="p-4 bg-gray-800 text-white"
        ),
        ps.main(
            ps.Outlet(),  # This renders the matched route component
            className="min-h-screen bg-gray-100"
        )
    )
```

**Key concepts:**
- `ps.Link()` creates navigation links
- `ps.Outlet()` renders the matched child route component
- Layouts wrap all child routes with common UI elements

---

# Chapter 3: Adding Routes

Routes connect URL paths to components and enable navigation.

## Static Routes

```python
ps.Route("/", home),           # Home page at /
ps.Route("/settings", settings), # Settings page at /settings
```

## Dynamic Routes

```python
ps.Route("/task/:id", task_details),  # Matches /task/abc123, /task/xyz789, etc.
```

## Accessing Route Information

```python
@ps.component
def task_details():
    route = ps.route_info()
    task_id = route.pathParams.get("id", "")  # Extract :id parameter
    
    return ps.div(
        ps.h2(f"Task ID: {task_id}"),
        ps.p(f"Current path: {route.pathname}"),
        ps.p(f"Query params: {route.queryParams}"),
    )
```

**Key concepts:**
- `ps.route_info()` hook provides route information
- `route.pathParams` contains dynamic route parameters  
- `route.pathname`, `route.queryParams` provide additional route data

---

# Chapter 4: State Management

State is where Pulse shines. Define reactive state classes that automatically trigger re-renders when data changes.

## Creating a State Class

```python
class TaskManagerState(ps.State):
    """Main state for the task manager."""
    tasks: list[Task]
    new_task_title: str = ""
    selected_category_id: str = ""
    
    def __init__(self):
        self.tasks = []
    
    def add_task(self):
        """Add a new task."""
        if not self.new_task_title.strip():
            return
        
        new_task = Task(self.new_task_title.strip(), self.selected_category_id)
        self.tasks = [*self.tasks, new_task]  # Create new list
        self.new_task_title = ""  # Clear input
```

**Key concepts:**
- Inherit from `ps.State` to create reactive state
- Type annotations create reactive properties
- State changes automatically trigger UI re-renders
- Always create new objects/lists instead of mutating existing ones

## Using State in Components

```python
@ps.component
def home():
    state = ps.states(TaskManagerState)  # Get state instance
    
    return ps.div(
        ps.input(
            type="text",
            placeholder="Enter task title...",
            value=state.new_task_title,
            onChange=lambda e: setattr(state, 'new_task_title', e["target"]["value"]),
        ),
        ps.button(
            "Add Task",
            onClick=state.add_task,
            disabled=not state.new_task_title.strip(),
        ),
    )
```

**Key concepts:**
- `ps.states()` hook creates/retrieves state instances
- Event handlers can be methods on state classes
- `onChange`, `onClick` connect user interactions to state changes

## Event Handlers and Callbacks

```python
def toggle_task(self, task_id: str):
    """Toggle task completion status."""
    self.tasks = [
        Task(t.title, t.category_id, not t.completed) if t.id == task_id 
        else t for t in self.tasks
    ]

# In component:
ps.button("Toggle", onClick=lambda: state.toggle_task(task.id))
```

**Key concepts:**
- Event handlers receive parameters via lambda functions or direct method references
- Multiple synchronous state changes are automatically batched into a single re-render

## Component Re-renders

When state changes, Pulse automatically re-renders components that use that state. This happens efficiently - only components that actually read the changed data will re-render.

---

# Chapter 5: The ps.states Hook

The `ps.states()` hook is crucial for proper state management in components.

## Why ps.states is Needed

```python
# ❌ Wrong - creates new state on every render
@ps.component 
def bad_component():
    state = TaskManagerState()  # New instance every time!
    return ps.div(f"Count: {state.count}")

# ✅ Correct - stable state instance
@ps.component
def good_component():
    state = ps.states(TaskManagerState)  # Same instance across renders
    return ps.div(f"Count: {state.count}")
```

## Multiple State Instances

```python
@ps.component
def multi_state_component():
    # Get multiple state instances at once
    task_state, query_state = ps.states(
        TaskManagerState(),
        TaskListQueryState()
    )
    
    return ps.div(
        f"Tasks: {len(task_state.tasks)}",
        f"Query calls: {query_state.calls}",
    )
```

**Key concepts:**
- Call `ps.states()` only once per component render
- State instances persist across component re-renders
- Can initialize multiple state instances in a single call

## Internal Fields

Fields starting with `_` are internal and non-reactive:

```python
class TaskManagerState(ps.State):
    tasks: list[Task]  # Reactive - triggers re-renders
    _internal_cache: dict = {}  # Non-reactive - for internal use
    
    def __init__(self):
        self._helper_data = "not reactive"  # Internal field
```

**Key concepts:**
- Reactive properties: declared with type annotations, trigger re-renders
- Internal fields: start with `_`, don't trigger re-renders, used for implementation details

---

# Chapter 6: Global States

Global states persist across different components and routes, perfect for shared application data.

## Creating Global State

```python
class AppState(ps.State):
    """Global application state that persists across all routes."""
    theme: str = "light"
    last_save: Optional[datetime] = None
    
    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"

# Create global state accessor
app_state = ps.global_state(AppState)
task_manager = ps.global_state(TaskManagerState)
```

## Using Global State

```python
@ps.component
def home():
    # Access global state - same instance across all components/routes
    state = task_manager()
    app = app_state()
    
    return ps.div(
        ps.span(f"Theme: {app.theme}"),
        ps.span(f"Tasks: {len(state.tasks)}"),
    )

@ps.component 
def settings():
    # Same global state instances
    app = app_state()
    
    return ps.button(
        "Toggle Theme",
        onClick=app.toggle_theme,
    )
```

**Key concepts:**
- `ps.global_state()` creates session-wide state that persists across routes
- Multiple components can access the same global state instance
- Changes in global state update all components that use it

---

# Chapter 7: Computed Properties

Computed properties are derived values that automatically update when their dependencies change.

## Basic Computeds

```python
class TaskManagerState(ps.State):
    tasks: list[Task]
    selected_category_id: str = ""
    
    @ps.computed
    def filtered_tasks(self) -> list[Task]:
        """Tasks filtered by selected category."""
        if not self.selected_category_id:
            return self.tasks
        return [t for t in self.tasks if t.category_id == self.selected_category_id]
    
    @ps.computed
    def task_stats(self) -> dict:
        """Computed statistics about tasks."""
        total = len(self.filtered_tasks)
        completed = sum(1 for t in self.filtered_tasks if t.completed)
        return {
            "total": total,
            "completed": completed,
            "remaining": total - completed,
            "completion_rate": (completed / total * 100) if total > 0 else 0
        }
```

## Using Computeds in Components

```python
@ps.component
def task_stats_display():
    state = ps.states(TaskManagerState)
    stats = state.task_stats  # Automatically recalculates when tasks change
    
    return ps.div(
        ps.div(f"Total: {stats['total']}", className="stat-box"),
        ps.div(f"Completed: {stats['completed']}", className="stat-box"),
        ps.div(f"Remaining: {stats['remaining']}", className="stat-box"),
        ps.div(f"{stats['completion_rate']:.1f}%", className="stat-box"),
        className="grid grid-cols-4 gap-2"
    )
```

**Key concepts:**
- `@ps.computed` decorator creates derived values
- Computeds automatically recalculate when dependencies change
- Dependencies are established by reading state properties inside the computed
- Computeds cache their results - they only recalculate when dependencies change

---

# Chapter 8: Queries (Async Data Loading)

Queries handle asynchronous data loading with caching, loading states, and error handling.

## Creating a Query

```python
class TaskListQueryState(ps.State):
    """State for loading task list via query."""
    calls: int = 0

    @ps.query
    async def tasks(self) -> list[Task]:
        """Query to load all tasks."""
        self.calls += 1
        print(f"Loading all tasks (call #{self.calls})...")
        return await fake_load_tasks()

    @tasks.key
    def _tasks_key(self):
        """Cache key - query refetches when this changes."""
        return ("tasks", len(task_manager().tasks))
```

## Using Queries in Components

```python
@ps.component
def home():
    query_state = ps.states(TaskListQueryState)
    tasks_query = query_state.tasks
    
    if tasks_query.is_loading:
        return ps.div("Loading tasks...", className="loading-spinner")
    
    tasks = tasks_query.data or []
    
    return ps.div(
        ps.div(f"Loaded {len(tasks)} tasks"),
        ps.button("Refresh", onClick=tasks_query.refetch),
        *[task_item(task) for task in tasks]
    )
```

## Query Keys and Cache Invalidation

```python
class TaskDetailQueryState(ps.State):
    task_id: str = ""
    
    def __init__(self, task_id: str):
        self.task_id = task_id

    @ps.query
    async def task(self) -> Optional[Task]:
        return await fake_load_task_by_id(self.task_id)

    @task.key  
    def _task_key(self):
        # Invalidate when the specific task changes
        task = next((t for t in task_manager().tasks if t.id == self.task_id), None)
        change_count = len(task.changes) if task else 0
        return ("task", self.task_id, change_count)
```

**Key concepts:**
- `@ps.query` decorator creates async data loading functions
- `@query.key` defines cache keys - query refetches when key changes
- `query.is_loading`, `query.data` provide loading state and results
- `query.refetch()` manually triggers a new fetch
- Queries cache results based on their key

---

# Chapter 9: Async Event Handlers

Handle asynchronous operations in event handlers, like API calls or complex computations.

## Async Event Handler Example

```python
class TaskManagerState(ps.State):
    is_saving: bool = False
    
    async def save_tasks(self):
        """Async event handler for manual save."""
        self.is_saving = True
        try:
            success = await fake_save_tasks(self.tasks)
            if success:
                self.has_unsaved_changes = False
                app_state().save_triggered()
        finally:
            self.is_saving = False
```

## Automatic Batching

```python
def add_task(self):
    """Synchronous writes are automatically batched."""
    if not self.new_task_title.strip():
        return
    
    # All these changes happen in a single render update:
    new_task = Task(self.new_task_title.strip(), self.selected_category_id)
    self.tasks = [*self.tasks, new_task]
    self.new_task_title = ""
    self.has_unsaved_changes = True
```

**Key concepts:**
- Event handlers can be async functions
- Synchronous state writes within a single function are automatically batched
- Async operations can span multiple render cycles
- Use loading states to show progress during async operations

---

# Chapter 10: Effects

Effects run side effects in response to state changes. Use them sparingly - most state changes should be handled through event handlers, computeds, and queries.

## State-Level Effects

```python
class TaskManagerState(ps.State):
    tasks: list[Task]
    has_unsaved_changes: bool = False
    
    @ps.effect
    def log_task_changes(self):
        """Effect that logs when tasks change."""
        task_count = len(self.tasks)
        has_changes = self.has_unsaved_changes
        
        print(f"Tasks changed: {task_count} total, unsaved changes: {has_changes}")
        # Note: Once Pulse supports async effects, this could automatically save changes
```

**Key concepts:**
- `@ps.effect` decorator creates side effects that run when dependencies change
- Dependencies are established by reading state properties inside the effect  
- Effects are for logging, analytics, cleanup - not for modifying other state
- Most of the time, you don't need effects - use event handlers instead

**⚠️ Important:** Effects should not be needed most of the time. Event handlers, computeds, and queries should handle nearly everything. Only use effects for side effects like logging, external API calls, or cleanup operations.

---

# Chapter 11: Hooks

Hooks provide access to framework functionality and component lifecycle events.

## Core Hooks Overview

```python
@ps.component
def example_component():
    # ps.states - component state management (use once per component)
    state = ps.states(TaskManagerState)
    
    # ps.setup - initialization with stable data capture
    meta = ps.setup(lambda data: {"processed": data}, some_prop)
    
    # ps.effects - mount-only side effects
    ps.effects(lambda: print("Component mounted!"))
    
    # ps.route_info - access route information
    route = ps.route_info()
    
    # ps.session_context - access session data
    session = ps.session_context()
    
    return ps.div("Hello from component!")
```

## ps.setup Hook

```python
@ps.component
def user_profile(user_id: str):
    # ps.setup captures and processes props on mount
    meta = ps.setup(lambda uid: {
        "user_id": uid,
        "cache_key": f"user-{uid}",
        "initialized_at": datetime.now()
    }, user_id)
    
    # meta is stable across re-renders
    state = ps.states(UserProfileState(meta["user_id"]))
    
    return ps.div(f"Profile for user {meta['user_id']}")
```

## ps.effects Hook

```python
@ps.component
def analytics_component():
    state = ps.states(ComponentState)
    
    # Mount-only effects
    ps.effects(
        lambda: print("Component mounted"),
        lambda: setup_analytics_tracking(),
        lambda: print("Ready for user interaction")
    )
    
    return ps.div("Component with analytics")
```

## ps.session_context Hook

```python
@ps.component
def user_info():
    session = ps.session_context()
    
    return ps.div(
        ps.div(f"User agent: {session.get('user_agent', 'Unknown')}"),
        ps.div(f"IP: {session.get('ip', 'Unknown')}"),
        ps.div(f"Connected: {session.get('connected_at', 'Never')}"),
    )
```

**Key concepts:**
- `ps.setup`, `ps.states`, and `ps.effects` should be called once per component
- `ps.setup` is for stable data processing that shouldn't change between renders
- `ps.effects` is for mount-only side effects like logging or external setup
- `ps.route_info` and `ps.session_context` provide framework data

---

# Chapter 12: Component Architecture

Build reusable components that encapsulate their own state and behavior.

## Reusable Component with State

```python
class TaskItemState(ps.State):
    """State for individual task items."""
    is_editing: bool = False
    edit_title: str = ""
    
    def start_editing(self, current_title: str):
        self.is_editing = True
        self.edit_title = current_title
    
    def cancel_editing(self):
        self.is_editing = False
        self.edit_title = ""
    
    def save_edit(self, task_id: str, onSave):
        if self.edit_title.strip():
            onSave(task_id, self.edit_title.strip())
        self.is_editing = False
        self.edit_title = ""

@ps.component  
def TaskItem(task: Task, category: Optional[Category], onToggle, onDelete, onEdit=None):
    """Reusable task item component with its own editing state."""
    state = ps.states(TaskItemState)
    
    # Mount effect
    ps.effects(lambda: print(f"TaskItem mounted for: {task.title}"))
    
    if state.is_editing and onEdit:
        # Editing mode
        return ps.div(
            ps.input(
                type="text",
                value=state.edit_title,
                onChange=lambda e: setattr(state, 'edit_title', e["target"]["value"]),
                className="flex-1 p-2 border rounded mr-2",
            ),
            ps.button("Save", onClick=lambda: state.save_edit(task.id, onEdit)),
            ps.button("Cancel", onClick=state.cancel_editing),
            className="p-3 border rounded bg-yellow-50"
        )
    
    # Normal view mode  
    return ps.div(
        ps.input(
            type="checkbox",
            checked=task.completed,
            onChange=lambda: onToggle(task.id),
        ),
        ps.span(task.title, className="flex-1"),
        ps.button("Edit", onClick=lambda: state.start_editing(task.title)),
        ps.button("Delete", onClick=lambda: onDelete(task.id)),
        className="p-3 border rounded bg-white flex items-center gap-3"
    )
```

## Component Composition

```python
@ps.component
def home():
    state = task_manager()
    
    return ps.div(
        CategorySelector(
            categories=state.categories,
            selected_id=state.selected_category_id,
            onSelect=state.select_category
        ),
        TaskStats(stats=state.task_stats, category_name="Work"),
        ps.div(
            *[TaskItem(
                task=task,
                category=state.get_category_by_id(task.category_id),
                onToggle=state.toggle_task,
                onDelete=state.delete_task,
                onEdit=state.edit_task_title,
                key=task.id  # Important for proper reconciliation
            ) for task in state.filtered_tasks]
        )
    )
```

**Key concepts:**
- Components can have their own internal state using `ps.states()`
- Pass callbacks as props to handle events in parent components
- Use `ps.effects()` for component-specific mount effects
- Each component instance gets its own state instance

---

# Chapter 13: Keys and Dynamic Lists

When rendering dynamic lists, use keys to help Pulse properly track and update components.

## Why Keys Matter

```python
# ❌ Without keys - components may not update correctly
@ps.component
def bad_task_list():
    state = ps.states(TaskManagerState)
    
    return ps.div(
        *[TaskItem(task=task, onDelete=state.delete_task) 
          for task in state.tasks]  # No keys!
    )

# ✅ With keys - proper component tracking
@ps.component 
def good_task_list():
    state = ps.states(TaskManagerState)
    
    return ps.div(
        *[TaskItem(
            task=task, 
            onDelete=state.delete_task,
            key=task.id  # Unique key for each item
        ) for task in state.tasks]
    )
```

## Using ps.For for Dynamic Lists

```python
@ps.component
def category_buttons():
    state = ps.states(TaskManagerState)
    
    return ps.div(
        *ps.For(
            state.categories,
            lambda cat: ps.button(
                cat.name,
                onClick=lambda: state.select_category(cat.id),
                key=cat.id  # ps.For automatically handles keys
            )
        )
    )
```

## ps.For vs List Comprehensions

```python
# List comprehension - you manage keys manually
buttons = [ps.button(cat.name, onClick=lambda: select(cat.id), key=cat.id) 
           for cat in categories]

# ps.For - automatic key management
buttons = ps.For(
    categories,
    lambda cat: ps.button(cat.name, onClick=lambda: select(cat.id))
)
```

**Key concepts:**
- Use `key` prop for items in dynamic lists to enable proper reconciliation
- `ps.For` is recommended for dynamic lists - it handles keys automatically  
- Without proper keys, component state might not update correctly when lists change
- Keys should be unique and stable (don't use array indices)

**Recommendation:** Use `ps.For` over list comprehensions for dynamic content, especially when components have internal state that should persist across re-orders.

---

# Chapter 14: Dynamic Routes and Layouts

Create dynamic routes that respond to URL parameters and build flexible layout systems.

## Dynamic Route Parameters

```python
# Route definition
ps.Route("/task/:id", task_details),

@ps.component
def task_details():
    """Show individual task details."""
    route = ps.route_info()
    task_id = route.pathParams.get("id", "")
    
    # Load task data based on route parameter
    query_state = ps.states(TaskDetailQueryState(task_id))
    task_query = query_state.task
    
    if not task_query.data:
        return ps.div("Task not found")
    
    task = task_query.data
    
    return ps.div(
        ps.h2(f"Task: {task.title}"),
        ps.div(f"Status: {'✓ Completed' if task.completed else '○ Pending'}"),
        ps.Link("← Back to Tasks", to="/"),
    )
```

## Nested Layouts

```python
@ps.component
def app_layout():
    """Main application layout."""
    app = app_state()
    
    return ps.div(
        ps.header(
            ps.h1("Pulse Task Manager"),
            ps.nav(
                ps.Link("Tasks", to="/"),
                ps.Link("Settings", to="/settings"),
            ),
            className="bg-gray-800 text-white p-4"
        ),
        ps.main(
            ps.Outlet(),  # Child route content goes here
            className="container mx-auto p-4"
        )
    )

# Route structure
ps.Layout(
    app_layout,
    children=[
        ps.Route("/", home),
        ps.Route("/task/:id", task_details),  
        ps.Route("/settings", settings),
    ]
)
```

**Key concepts:**
- Use `:param` syntax in routes for dynamic segments
- Access parameters via `ps.route_info().pathParams`
- `ps.Outlet()` in layouts renders the matched child route
- Layouts provide consistent structure across different pages

---

# Chapter 15: Complete Application Structure

Let's put it all together and see how a complete Pulse application is structured.

## File Organization

```
tutorial.py                 # Main application file
├── Data Models            # Task, Category, TaskChange classes
├── Global State           # AppState, TaskManagerState + global accessors  
├── Query States           # TaskListQueryState, TaskDetailQueryState
├── Components            # TaskItem, CategorySelector (reusable UI)
├── Pages                 # home, task_details, settings (route components)
├── Layout               # app_layout (shared UI structure)  
└── App Definition       # Routes and app configuration
```

## State Architecture

```python
# Global States (persist across routes)
app_state = ps.global_state(AppState)          # App-wide settings
task_manager = ps.global_state(TaskManagerState)  # Task data

# Local States (component-specific)
class TaskItemState(ps.State):       # Individual task editing
class CategoryFilterState(ps.State): # Category visibility toggle
class TaskListQueryState(ps.State):  # Query for loading all tasks
class TaskDetailQueryState(ps.State): # Query for loading one task
```

## Component Hierarchy

```
app_layout                    # Layout with navigation
├── home                     # Main task manager page
│   ├── CategorySelector     # Filter by category (has own state)
│   ├── TaskStats           # Computed statistics display
│   ├── AddTaskForm         # Form with category dropdown
│   └── TaskItem[]          # List of tasks (each has own state)
├── task_details            # Individual task page
│   ├── TaskInfo           # Task details and actions
│   └── ChangeHistory      # List of all modifications
└── settings               # App settings page
    ├── ThemeToggle        # Global theme state
    └── SessionInfo        # Session context display
```

## Data Flow Patterns

1. **User Interaction** → **Event Handler** → **State Change** → **UI Update**
2. **Route Navigation** → **Component Mount** → **Query Execution** → **Data Display**
3. **Global State Change** → **All Dependent Components Re-render**
4. **Computed Property Access** → **Dependency Tracking** → **Auto-recalculation**

---

# Chapter 16: Best Practices and Patterns

## State Management Best Practices

```python
# ✅ Do: Create new objects instead of mutating
def add_task(self):
    self.tasks = [*self.tasks, new_task]  # New list

# ❌ Don't: Mutate existing objects
def add_task(self):
    self.tasks.append(new_task)  # Mutates existing list

# ✅ Do: Use computed properties for derived data
@ps.computed
def filtered_tasks(self) -> list[Task]:
    return [t for t in self.tasks if t.category_id == self.selected_category_id]

# ❌ Don't: Manually sync derived state
def select_category(self, category_id: str):
    self.selected_category_id = category_id
    self.filtered_tasks = [t for t in self.tasks if t.category_id == category_id]
```

## Component Design Patterns

```python
# ✅ Do: Keep components focused and reusable
@ps.component
def TaskItem(task: Task, onToggle, onDelete):
    """Single responsibility: display and edit one task."""
    
# ✅ Do: Use callbacks for parent-child communication
def parent_component():
    return TaskItem(task=task, onToggle=handle_toggle, onDelete=handle_delete)

# ✅ Do: Use keys for dynamic lists
*[TaskItem(task=t, key=t.id) for t in tasks]

# ✅ Do: Call ps.states() once per component
state = ps.states(MyState)
```

## Query and Async Patterns

```python
# ✅ Do: Use queries for data loading
@ps.query
async def load_data(self):
    return await api_call()

# ✅ Do: Handle loading states
if query.is_loading:
    return ps.div("Loading...")

# ✅ Do: Use meaningful cache keys
@load_data.key
def _cache_key(self):
    return ("data", self.user_id, self.last_modified)
```

## Performance Tips

- **Use keys properly** - Essential for list reconciliation performance
- **Avoid unnecessary state** - Only make data reactive if UI depends on it  
- **Leverage computeds** - Cache expensive calculations automatically
- **Use global state judiciously** - For truly shared data across routes/components
- **Structure components well** - Small, focused components re-render more efficiently

---

# Chapter 17: Advanced Patterns

## Change Tracking Pattern

```python
@dataclass
class TaskChange:
    field: str
    old_value: str  
    new_value: str
    timestamp: datetime = field(default_factory=datetime.now)

class TaskManagerState(ps.State):
    def _add_task_change(self, task: Task, field: str, old_value: str, new_value: str):
        change = TaskChange(field, old_value, new_value)
        task.changes.append(change)
    
    def toggle_task(self, task_id: str):
        # Create new task with change history
        updated_tasks = []
        for t in self.tasks:
            if t.id == task_id:
                new_task = Task(t.title, t.category_id, not t.completed, t.id, t.created_at, t.changes.copy())
                self._add_task_change(new_task, "completed", str(t.completed), str(not t.completed))
                updated_tasks.append(new_task)
            else:
                updated_tasks.append(t)
        self.tasks = updated_tasks
```

## Query Invalidation Pattern

```python
class TaskDetailQueryState(ps.State):
    @ps.query
    async def task(self) -> Optional[Task]:
        return await load_task(self.task_id)
    
    @task.key
    def _task_key(self):
        # Invalidate query when task changes
        task = find_task_in_global_state(self.task_id)
        change_count = len(task.changes) if task else 0
        return ("task", self.task_id, change_count)
```

## Form Handling Pattern

```python
class FormState(ps.State):
    title: str = ""
    category_id: str = ""
    is_valid: bool = False
    
    @ps.computed
    def validation_errors(self) -> list[str]:
        errors = []
        if not self.title.strip():
            errors.append("Title is required")
        if not self.category_id:
            errors.append("Category is required") 
        return errors
    
    @ps.computed
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0

@ps.component
def task_form():
    form = ps.states(FormState)
    
    return ps.div(
        ps.input(
            value=form.title,
            onChange=lambda e: setattr(form, 'title', e["target"]["value"]),
            className="border " + ("border-red-500" if "Title" in form.validation_errors else "border-gray-300")
        ),
        ps.select(
            value=form.category_id,
            onChange=lambda e: setattr(form, 'category_id', e["target"]["value"])
        ),
        ps.button(
            "Submit",
            onClick=submit_form,
            disabled=not form.is_valid
        ),
        *[ps.div(error, className="text-red-500") for error in form.validation_errors]
    )
```

---

# Next Steps

Congratulations! You've learned all the core concepts of Pulse:

✅ **App Structure** - Routes, layouts, and component organization  
✅ **Components** - Reusable UI building blocks  
✅ **State Management** - Reactive state classes and global state  
✅ **Event Handling** - Sync and async event handlers with automatic batching  
✅ **Computeds** - Derived values that update automatically  
✅ **Queries** - Async data loading with caching and loading states  
✅ **Effects** - Side effects that respond to state changes  
✅ **Hooks** - Framework integration points  
✅ **Keys & Lists** - Proper reconciliation for dynamic content

## Try These Exercises

1. **Add Categories CRUD** - Let users create, edit, and delete categories
2. **Task Search** - Add a search filter that works with category filtering  
3. **Due Dates** - Add due date tracking with overdue highlighting
4. **Task Drag & Drop** - Reorder tasks or move between categories
5. **Real Backend** - Replace the fake API with a real database

## Learn More

- **Pulse Documentation** - Dive deeper into advanced features
- **Example Applications** - See more complex Pulse apps in action
- **Community** - Join discussions and share your Pulse projects

Happy coding with Pulse! 🚀