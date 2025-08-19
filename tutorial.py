import asyncio
from dataclasses import dataclass, field
import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import pulse as ps


# Data Models and Helpers
# -----------------------


def generate_id() -> str:
    """Generate a simple unique ID based on timestamp."""
    return uuid4().hex


@dataclass
class TaskChange:
    """Represents a change made to a task."""

    field: str  # 'title', 'category', 'completed'
    old_value: str
    new_value: str
    timestamp: datetime = dataclasses.field(default_factory=datetime.now)


@dataclass
class Task:
    """Simple task data model with change history."""

    title: str
    category_id: str
    completed: bool = False
    id: str = field(default_factory=generate_id)
    created_at: datetime = dataclasses.field(default_factory=datetime.now)
    changes: list[TaskChange] = dataclasses.field(default_factory=list)


class Category:
    """Simple category data model."""

    def __init__(self, name: str, color: str = "blue"):
        self.id = generate_id()
        self.name = name
        self.color = color


# Fake API simulation
# -------------------


async def fake_save_tasks(tasks: list[Task]) -> bool:
    """Simulate saving tasks to a server."""
    await asyncio.sleep(0.5)  # Simulate network delay
    return True


async def fake_load_tasks() -> list[Task]:
    """Simulate loading tasks from a server."""
    await asyncio.sleep(0.4)
    # In reality, this would fetch from a database
    # For demo, we'll return the global state data
    return task_manager().tasks


async def fake_load_task_by_id(task_id: str) -> Optional[Task]:
    """Simulate loading a single task from server."""
    await asyncio.sleep(0.3)
    # In reality, this would fetch from a database
    tasks = task_manager().tasks
    return next((t for t in tasks if t.id == task_id), None)


# Global Application State
# ------------------------


class AppState(ps.State):
    """Global application state that persists across all routes."""

    theme: str = "light"
    last_save: Optional[datetime] = None

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"

    def save_triggered(self):
        """Called when auto-save is triggered."""
        self.last_save = datetime.now()


# Task Manager State
# ------------------


class TaskManagerState(ps.State):
    """Main state for the task manager."""

    tasks: list[Task]
    categories: list[Category]
    new_task_title: str = ""
    new_task_category_id: str = ""  # For category selection when adding
    selected_category_id: str = ""  # For filtering view ("" = all categories)
    has_unsaved_changes: bool = False

    def __init__(self):
        # Initialize with some demo categories
        work_category = Category("Work", "blue")
        personal_category = Category("Personal", "green")
        shopping_category = Category("Shopping", "purple")
        health_category = Category("Health", "red")
        education_category = Category("Education", "yellow")
        social_category = Category("Social", "pink")
        projects_category = Category("Projects", "indigo")
        self.categories = [
            work_category,
            personal_category,
            shopping_category,
            health_category,
            education_category,
            social_category,
            projects_category,
        ]

        # Initialize with some demo tasks
        self.tasks = [
            Task("Review pull requests", work_category.id, False),
            Task("Update documentation", work_category.id, True),
            Task("Buy groceries", personal_category.id, False),
        ]
        self.selected_category_id = ""  # show all tasks by default
        self.new_task_category_id = work_category.id  # Default to Work category

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
            "completion_rate": (completed / total * 100) if total > 0 else 0,
        }

    @ps.computed
    def selected_category(self) -> Optional[Category]:
        """Currently selected category."""
        if not self.selected_category_id:
            return None
        return next(
            (c for c in self.categories if c.id == self.selected_category_id), None
        )

    @ps.computed
    def new_task_category(self) -> Optional[Category]:
        """Category selected for new task."""
        return next(
            (c for c in self.categories if c.id == self.new_task_category_id), None
        )

    def get_category_by_id(self, category_id: str) -> Optional[Category]:
        """Helper to get category by ID."""
        return next((c for c in self.categories if c.id == category_id), None)

    @ps.effect
    def detect_unsaved_changes(self):
        _ = self.tasks  # register dependency
        self.has_unsaved_changes = True

    def _add_task_change(self, task: Task, field: str, old_value: str, new_value: str):
        """Helper to record task changes."""
        change = TaskChange(field, old_value, new_value)
        task.changes.append(change)

    def add_task(self):
        """Add a new task - demonstrates synchronous state batching."""
        if not self.new_task_title.strip() or not self.new_task_category_id:
            return

        # Multiple state changes are automatically batched into single render
        new_task = Task(self.new_task_title.strip(), self.new_task_category_id)
        self.tasks = [*self.tasks, new_task]
        self.new_task_title = ""  # Clear input

    def toggle_task(self, task_id: str):
        """Toggle task completion status with change tracking."""
        updated_tasks = []
        for t in self.tasks:
            if t.id == task_id:
                new_completed = not t.completed
                new_task = Task(
                    t.title,
                    t.category_id,
                    new_completed,
                    t.id,
                    t.created_at,
                    t.changes.copy(),
                )
                self._add_task_change(
                    new_task, "completed", str(t.completed), str(new_completed)
                )
                updated_tasks.append(new_task)
            else:
                updated_tasks.append(t)
        self.tasks = updated_tasks

    def delete_task(self, task_id: str):
        """Delete a task."""
        self.tasks = [t for t in self.tasks if t.id != task_id]

    def select_category(self, category_id: str):
        """Select a different category for filtering."""
        self.selected_category_id = category_id
        # When changing filter, also update the default category for new tasks
        if category_id:
            self.new_task_category_id = category_id

    def set_new_task_category(self, category_id: str):
        """Set category for new task."""
        self.new_task_category_id = category_id

    def edit_task_title(self, task_id: str, new_title: str):
        """Edit a task's title with change tracking."""
        updated_tasks = []
        for t in self.tasks:
            if t.id == task_id:
                new_task = Task(
                    new_title,
                    t.category_id,
                    t.completed,
                    t.id,
                    t.created_at,
                    t.changes.copy(),
                )
                self._add_task_change(new_task, "title", t.title, new_title)
                updated_tasks.append(new_task)
            else:
                updated_tasks.append(t)
        self.tasks = updated_tasks

    def edit_task_category(self, task_id: str, new_category_id: str):
        """Edit a task's category with change tracking."""
        updated_tasks = []
        for t in self.tasks:
            if t.id == task_id:
                old_cat = self.get_category_by_id(t.category_id)
                new_cat = self.get_category_by_id(new_category_id)
                new_task = Task(
                    t.title,
                    new_category_id,
                    t.completed,
                    t.id,
                    t.created_at,
                    t.changes.copy(),
                )
                self._add_task_change(
                    new_task,
                    "category",
                    old_cat.name if old_cat else "Unknown",
                    new_cat.name if new_cat else "Unknown",
                )
                updated_tasks.append(new_task)
            else:
                updated_tasks.append(t)
        self.tasks = updated_tasks

    async def save_tasks(self):
        """Async event handler for manual save."""
        success = await fake_save_tasks(self.tasks)
        if success:
            self.has_unsaved_changes = False
            app_state().save_triggered()

    @ps.effect
    def log_task_changes(self):
        """Effect that logs when tasks change."""
        task_count = len(self.tasks)
        has_changes = self.has_unsaved_changes

        print(f"Tasks changed: {task_count} total, unsaved changes: {has_changes}")
        # Note: Once Pulse supports async effects, this could automatically save changes


# Create global state accessors
app_state = ps.global_state(AppState)
task_manager = ps.global_state(TaskManagerState)


# Query States (demonstrate loading data with queries)
# ----------------------------------------------------


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
        return (
            "tasks",
            len(task_manager().tasks),
        )  # Invalidate when task count changes


class TaskDetailQueryState(ps.State):
    """State for loading individual task details."""

    calls: int = 0
    task_id: str = ""

    def __init__(self, task_id: str):
        self.task_id = task_id

    @ps.query
    async def task(self) -> Optional[Task]:
        """Query to load a specific task."""
        self.calls += 1
        print(f"Loading task {self.task_id} (call #{self.calls})...")
        return await fake_load_task_by_id(self.task_id)

    @task.key
    def _task_key(self):
        # Invalidate when the specific task changes
        task = next((t for t in task_manager().tasks if t.id == self.task_id), None)
        change_count = len(task.changes) if task else 0
        return ("task", self.task_id, change_count)


# Components
# ----------


class TaskItemState(ps.State):
    """State for individual task items - demonstrates component-level state."""

    is_editing: bool = False
    edit_title: str = ""

    def start_editing(self, current_title: str):
        """Start editing mode."""
        self.is_editing = True
        self.edit_title = current_title

    def cancel_editing(self):
        """Cancel editing mode."""
        self.is_editing = False
        self.edit_title = ""

    def save_edit(self, task_id: str, onSave):
        """Save the edited title."""
        if self.edit_title.strip():
            onSave(task_id, self.edit_title.strip())
        self.is_editing = False
        self.edit_title = ""


@ps.component
def TaskItem(task: Task, category: Optional[Category], onToggle, onDelete, onEdit=None):
    """Reusable task item component with its own editing state."""
    state = ps.states(TaskItemState)

    # Effect that logs when this task item mounts
    ps.effects(lambda: print(f"TaskItem mounted for: {task.title}"))

    if state.is_editing and onEdit:
        # Editing mode
        return ps.div(
            ps.div(
                ps.input(
                    type="text",
                    value=state.edit_title,
                    onChange=lambda e: setattr(
                        state, "edit_title", e["target"]["value"]
                    ),
                    className="flex-1 p-2 border rounded mr-2",
                ),
                ps.button(
                    "Save",
                    onClick=lambda: state.save_edit(task.id, onEdit),
                    className="btn-primary mr-2",
                ),
                ps.button(
                    "Cancel", onClick=state.cancel_editing, className="btn-secondary"
                ),
                className="flex items-center",
            ),
            className="p-3 border rounded mb-2 bg-yellow-50 shadow-sm",
        )

    # Normal view mode
    return ps.div(
        ps.div(
            ps.input(
                type="checkbox",
                checked=task.completed,
                onChange=lambda: onToggle(task.id),
                className="mr-3",
            ),
            ps.div(
                ps.span(
                    task.title,
                    className="font-medium "
                    + ("line-through text-gray-500" if task.completed else ""),
                ),
                ps.div(
                    ps.small(
                        f"Category: {category.name if category else 'Unknown'}",
                        className="text-gray-500",
                    ),
                    ps.small(
                        f" • Created: {task.created_at.strftime('%H:%M')}",
                        className="text-gray-400",
                    ),
                    ps.small(
                        f" • {len(task.changes)} changes", className="text-gray-400"
                    )
                    if task.changes
                    else None,
                    className="text-xs",
                ),
                className="flex-1",
            ),
            ps.div(
                ps.Link("View", to=f"/task/{task.id}", className="link mr-2"),
                ps.button(
                    "Edit",
                    onClick=lambda: state.start_editing(task.title),
                    className="btn-secondary-sm mr-2",
                )
                if onEdit
                else None,
                ps.button(
                    "Delete",
                    onClick=lambda: onDelete(task.id),
                    className="btn-secondary-sm",
                ),
                className="flex items-center",
            ),
            className="flex items-start gap-3",
        ),
        className="p-3 border rounded mb-2 bg-white shadow-sm",
    )


class CategoryFilterState(ps.State):
    """State for category filtering component."""

    show_all: bool = False

    def toggle_show_all(self):
        """Toggle showing all categories."""
        self.show_all = not self.show_all


@ps.component
def CategorySelector(categories: list[Category], selected_id: str, onSelect):
    """Category selection component with its own filter state."""
    state = ps.states(CategoryFilterState)

    # Effect that runs when component mounts
    ps.effects(lambda: print("CategorySelector mounted"))

    visible_categories = categories if state.show_all else categories[:3]

    return ps.div(
        ps.div(
            ps.h3("Filter by Category", className="text-lg font-semibold mb-3"),
            ps.button(
                f"{'Hide' if state.show_all else 'Show All'} ({len(categories)})",
                onClick=state.toggle_show_all,
                className="btn-secondary-sm ml-2",
            )
            if len(categories) > 3
            else None,
            className="flex items-center justify-between",
        ),
        ps.div(
            ps.button(
                "All Categories",
                onClick=lambda: onSelect(""),
                className=f"btn-{'primary' if selected_id == '' else 'secondary'} mr-2 mb-2",
            ),
            *ps.For(
                visible_categories,
                lambda cat: ps.button(
                    cat.name,
                    onClick=lambda: onSelect(cat.id),
                    className=f"btn-{'primary' if cat.id == selected_id else 'secondary'} mr-2 mb-2",
                    key=cat.id,
                ),
            ),
            className="flex flex-wrap",
        ),
        className="mb-6",
    )


# Pages
# -----


@ps.component
def home():
    """Main task manager page with query-based task loading."""
    # Use global state so it persists across routes
    state = task_manager()

    # Use query to load tasks (even though they come from global state)
    query_state = ps.states(TaskListQueryState)
    tasks_query = query_state.tasks

    # Hook for accessing route info
    route = ps.route_info()

    # Mount-only effect using ps.effects
    ps.effects(lambda: print("Task manager mounted!"))

    selected_cat = state.selected_category
    category_name = selected_cat.name if selected_cat else "All Categories"

    # Use query data if available, fallback to state
    display_tasks = tasks_query.data if tasks_query.data else state.tasks
    filtered_tasks = (
        display_tasks
        if not state.selected_category_id
        else [t for t in display_tasks if t.category_id == state.selected_category_id]
    )

    return ps.div(
        ps.h1("Task Manager", className="text-3xl font-bold mb-6"),
        # Category selector
        CategorySelector(
            categories=state.categories,
            selected_id=state.selected_category_id,
            onSelect=state.select_category,
        ),
        # Task statistics
        ps.div(
            ps.h3(f"{category_name} Tasks", className="text-xl font-bold mb-2"),
            ps.div(
                ps.div(
                    f"Total: {state.task_stats['total']}",
                    className="text-center p-2 bg-blue-100 rounded",
                ),
                ps.div(
                    f"Completed: {state.task_stats['completed']}",
                    className="text-center p-2 bg-green-100 rounded",
                ),
                ps.div(
                    f"Remaining: {state.task_stats['remaining']}",
                    className="text-center p-2 bg-yellow-100 rounded",
                ),
                ps.div(
                    f"{state.task_stats['completion_rate']:.1f}%",
                    className="text-center p-2 bg-purple-100 rounded",
                ),
                className="grid grid-cols-4 gap-2 mb-4",
            ),
        ),
        # Add task form
        ps.div(
            ps.h3("Add New Task", className="text-lg font-semibold mb-3"),
            ps.div(
                ps.input(
                    type="text",
                    placeholder="Enter task title...",
                    value=state.new_task_title,
                    onChange=lambda e: setattr(
                        state, "new_task_title", e["target"]["value"]
                    ),
                    className="flex-1 p-2 border rounded mr-2",
                ),
                ps.select(
                    ps.option("Select category...", value="", disabled=True),
                    *[
                        ps.option(cat.name, value=cat.id, key=cat.id)
                        for cat in state.categories
                    ],
                    value=state.new_task_category_id,
                    onChange=lambda e: state.set_new_task_category(
                        e["target"]["value"]
                    ),
                    className="p-2 border rounded mr-2 min-w-40",
                ),
                ps.button(
                    "Add Task",
                    onClick=state.add_task,
                    className="btn-primary",
                    disabled=not (
                        state.new_task_title.strip() and state.new_task_category_id
                    ),
                ),
                className="flex items-center",
            ),
            className="mb-6",
        ),
        # Query loading indicator
        ps.div(
            "Loading tasks..."
            if tasks_query.is_loading
            else ps.div(
                ps.span(
                    f"Loaded {len(display_tasks)} tasks",
                    className="text-sm text-gray-600 mr-2",
                ),
                ps.button(
                    "Refresh", onClick=tasks_query.refetch, className="btn-secondary-sm"
                ),
            ),
            className="mb-4",
        ),
        # Task list with keys for proper reconciliation
        ps.div(
            ps.h3("Tasks", className="text-lg font-semibold mb-3"),
            ps.div(
                *[
                    TaskItem(
                        task=task,
                        category=state.get_category_by_id(task.category_id),
                        onToggle=state.toggle_task,
                        onDelete=state.delete_task,
                        onEdit=state.edit_task_title,  # Enable editing
                        key=task.id,  # Important: keys for dynamic lists
                    )
                    for task in filtered_tasks
                ]
                if filtered_tasks
                else [
                    ps.div(
                        "No tasks in this category yet. Add one above!",
                        className="text-gray-500 italic p-4",
                    )
                ]
            ),
            className="mb-6",
        ),
        # Manual save button (async operation)
        ps.div(
            ps.button("Save Tasks", onClick=state.save_tasks, className="btn-primary"),
            ps.span(
                f" (Unsaved changes: {state.has_unsaved_changes})",
                className="text-sm text-gray-500 ml-2",
            ),
            className="mb-4",
        ),
        # Debug info
        ps.div(
            ps.small(f"Route: {route.pathname}", className="text-gray-400"),
            className="text-xs",
        ),
        className="p-6 max-w-4xl mx-auto",
    )


@ps.component
def task_details():
    """Dynamic route page showing individual task details and change history."""
    route = ps.route_info()
    task_id = route.pathParams.get("id", "")

    # Use query to load task details
    query_state = ps.states(TaskDetailQueryState(task_id))
    task_query = query_state.task

    # Also get global state for actions
    state = task_manager()

    if task_query.is_loading:
        return ps.div(
            ps.h2("Loading task...", className="text-2xl font-bold mb-4"),
            ps.div(ps.Link("← Back to Tasks", to="/", className="link")),
            className="p-6 max-w-4xl mx-auto",
        )

    task = task_query.data
    if not task:
        return ps.div(
            ps.h2("Task Not Found", className="text-2xl font-bold mb-4"),
            ps.p("The requested task doesn't exist or has been deleted."),
            ps.div(ps.Link("← Back to Tasks", to="/", className="link")),
            className="p-6 max-w-4xl mx-auto",
        )

    category = state.get_category_by_id(task.category_id)

    return ps.div(
        ps.h2(f"Task: {task.title}", className="text-2xl font-bold mb-4"),
        ps.div(ps.Link("← Back to Tasks", to="/", className="link mb-4 inline-block")),
        # Task details
        ps.div(
            ps.h3("Task Details", className="text-lg font-semibold mb-3"),
            ps.div(
                ps.div(f"Title: {task.title}", className="mb-2"),
                ps.div(
                    f"Category: {category.name if category else 'Unknown'}",
                    className="mb-2",
                ),
                ps.div(
                    f"Status: {'✓ Completed' if task.completed else '○ Pending'}",
                    className="mb-2",
                ),
                ps.div(
                    f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}",
                    className="mb-2",
                ),
                ps.div(f"Total changes: {len(task.changes)}", className="mb-4"),
                className="text-sm",
            ),
            ps.div(
                ps.button(
                    f"Mark as {'Completed' if not task.completed else 'Pending'}",
                    onClick=lambda: state.toggle_task(task.id),
                    className="btn-primary mr-2",
                ),
                ps.button(
                    "Refresh", onClick=task_query.refetch, className="btn-secondary"
                ),
            ),
            className="p-4 bg-gray-50 rounded mb-6",
        ),
        # Change history
        ps.div(
            ps.h3("Change History", className="text-lg font-semibold mb-3"),
            ps.div(
                *[
                    ps.div(
                        ps.div(
                            ps.span(
                                f"{change.field.title()} changed",
                                className="font-semibold mr-2",
                            ),
                            ps.span(
                                f"{change.timestamp.strftime('%H:%M:%S')}",
                                className="text-xs text-gray-500",
                            ),
                            className="flex justify-between items-center mb-1",
                        ),
                        ps.div(
                            ps.span(
                                f"From: {change.old_value}",
                                className="text-red-600 mr-4",
                            ),
                            ps.span(
                                f"To: {change.new_value}", className="text-green-600"
                            ),
                            className="text-sm",
                        ),
                        className="p-3 border rounded mb-2 bg-white",
                        key=f"{change.timestamp.isoformat()}-{change.field}",
                    )
                    for change in reversed(task.changes)
                ]  # Show newest first
                if task.changes
                else [
                    ps.div(
                        "No changes recorded yet.", className="text-gray-500 italic p-4"
                    )
                ]
            ),
            className="mb-6",
        ),
        # Query debug info
        ps.div(
            ps.small(
                f"Query calls made: {query_state.calls}", className="text-gray-400"
            ),
            className="text-xs",
        ),
        className="p-6 max-w-4xl mx-auto",
    )


@ps.component
def settings():
    """Settings page demonstrating global state."""
    app = app_state()
    session = ps.session_context()

    return ps.div(
        ps.h2("Settings", className="text-2xl font-bold mb-4"),
        ps.div(ps.Link("← Back to Tasks", to="/", className="link mb-4 inline-block")),
        ps.div(
            ps.h3("Theme", className="text-lg font-semibold mb-3"),
            ps.div(f"Current theme: {app.theme}", className="mb-2"),
            ps.button(
                "Toggle Theme", onClick=app.toggle_theme, className="btn-primary"
            ),
            className="mb-6",
        ),
        # Session context demo
        ps.div(
            ps.h3("Session Info", className="text-lg font-semibold mb-3"),
            ps.div(
                *[ps.div(f"{key}: {value}") for key, value in session.items()]
                if session
                else [ps.div("No session data available")],
                className="text-sm text-gray-600",
            ),
            className="p-4 bg-gray-50 rounded",
        ),
        className="p-6 max-w-4xl mx-auto",
    )


# Layout
# ------


@ps.component
def app_layout():
    """Main application layout with navigation."""
    app = app_state()

    return ps.div(
        # Header with navigation
        ps.header(
            ps.div(
                ps.h1("Pulse Task Manager", className="text-2xl font-bold"),
                ps.div(
                    ps.span(f"Theme: {app.theme}", className="mr-4 text-sm"),
                    ps.span(
                        f"Last save: {app.last_save.strftime('%H:%M:%S') if app.last_save else 'Never'}",
                        className="text-sm",
                    ),
                ),
                className="flex justify-between items-center p-4 bg-gray-800 text-white",
            ),
            ps.nav(
                ps.Link("Tasks", to="/", className="nav-link"),
                ps.Link("Settings", to="/settings", className="nav-link"),
                className="flex space-x-4 p-3 bg-gray-700 text-white",
            ),
        ),
        # Main content
        ps.main(
            ps.Outlet(),  # This renders the matched route component
            className="min-h-screen bg-gray-100",
        ),
    )


# Application Definition
# ---------------------

app = ps.App(
    routes=[
        ps.Layout(
            app_layout,
            children=[
                ps.Route("/", home),
                ps.Route(
                    "/task/:id", task_details
                ),  # Dynamic route for individual tasks
                ps.Route("/settings", settings),
            ],
        )
    ],
    codegen=ps.CodegenConfig(web_dir=Path(__file__).parent / "pulse-demo"),
)
