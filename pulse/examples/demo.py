"""
Complex Pulse UI Demo: Task Management Dashboard

This demo showcases advanced Pulse features including:
- Complex state management with multiple State classes
- Form handling and validation
- CRUD operations
- Multiple routes and navigation
- Interactive components
- Real-time statistics
- Responsive design with Tailwind CSS
"""

import pulse as ps
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class Task:
    id: int
    title: str
    description: str
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    due_date: Optional[datetime] = None
    assigned_to: Optional[str] = None


@dataclass
class User:
    id: int
    name: str
    email: str
    avatar: str
    role: str


class AppState(ps.State):
    """Main application state"""

    tasks: List[Task] = []
    users: List[User] = []
    current_user_id: int = 1
    next_task_id: int = 1
    filter_status: str = "all"
    filter_priority: str = "all"
    search_query: str = ""

    def add_task(self, title: str, description: str, priority: str, due_date: str = ""):
        """Add a new task"""
        due = datetime.fromisoformat(due_date) if due_date else None

        task = Task(
            id=self.next_task_id,
            title=title,
            description=description,
            priority=TaskPriority(priority),
            status=TaskStatus.TODO,
            created_at=datetime.now(),
            due_date=due,
            assigned_to=self.get_current_user().name,
        )

        self.tasks.append(task)
        self.next_task_id += 1
        print(f"✅ Added task: {title}")

    def update_task_status(self, task_id: int, status: str):
        """Update task status"""
        for task in self.tasks:
            if task.id == task_id:
                task.status = TaskStatus(status)
                print(f"📝 Updated task {task_id} status to {status}")
                break
        # Trigger re-render by updating the list
        self.tasks = self.tasks[:]

    def delete_task(self, task_id: int):
        """Delete a task"""
        self.tasks = [task for task in self.tasks if task.id != task_id]
        print(f"🗑️ Deleted task {task_id}")

    def get_current_user(self) -> User:
        """Get the current user"""
        return next(
            (user for user in self.users if user.id == self.current_user_id),
            self.users[0],
        )

    def get_filtered_tasks(self) -> List[Task]:
        """Get tasks based on current filters"""
        filtered = self.tasks

        # Filter by status
        if self.filter_status != "all":
            filtered = [t for t in filtered if t.status.value == self.filter_status]

        # Filter by priority
        if self.filter_priority != "all":
            filtered = [t for t in filtered if t.priority.value == self.filter_priority]

        # Filter by search query
        if self.search_query:
            query = self.search_query.lower()
            filtered = [
                t
                for t in filtered
                if query in t.title.lower() or query in t.description.lower()
            ]

        return filtered

    def get_task_stats(self):
        """Get task statistics"""
        total = len(self.tasks)
        completed = len([t for t in self.tasks if t.status == TaskStatus.COMPLETED])
        in_progress = len([t for t in self.tasks if t.status == TaskStatus.IN_PROGRESS])
        todo = len([t for t in self.tasks if t.status == TaskStatus.TODO])

        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "todo": todo,
            "completion_rate": round((completed / total * 100) if total > 0 else 0, 1),
        }


class FormState(ps.State):
    """Form state for task creation"""

    title: str = ""
    description: str = ""
    priority: str = "medium"
    due_date: str = ""
    show_form: bool = False
    errors: dict = {}

    def toggle_form(self):
        """Toggle form visibility"""
        self.show_form = not self.show_form
        if not self.show_form:
            self.reset_form()

    def reset_form(self):
        """Reset form fields"""
        self.title = ""
        self.description = ""
        self.priority = "medium"
        self.due_date = ""
        self.errors = {}

    def validate(self) -> bool:
        """Validate form data"""
        errors = {}

        if not self.title.strip():
            errors["title"] = "Title is required"
        elif len(self.title) < 3:
            errors["title"] = "Title must be at least 3 characters"

        if not self.description.strip():
            errors["description"] = "Description is required"

        self.errors = errors
        return len(errors) == 0


def init_sample_data(state: AppState):
    """Initialize with sample data"""
    # Add sample users
    state.users = [
        User(1, "Alice Johnson", "alice@example.com", "👩‍💻", "Developer"),
        User(2, "Bob Smith", "bob@example.com", "👨‍🎨", "Designer"),
        User(3, "Carol Wilson", "carol@example.com", "👩‍💼", "Manager"),
    ]

    # Add sample tasks
    sample_tasks = [
        (
            "Implement user authentication",
            "Add login/logout functionality with JWT",
            "high",
        ),
        ("Design landing page", "Create wireframes and mockups for homepage", "medium"),
        ("Write API documentation", "Document all REST endpoints", "low"),
        ("Fix responsive layout", "Mobile view needs adjustment", "high"),
        (
            "Set up CI/CD pipeline",
            "Configure automated testing and deployment",
            "medium",
        ),
    ]

    for i, (title, desc, priority) in enumerate(sample_tasks):
        state.add_task(title, desc, priority)
        # Mark some as completed or in progress
        if i == 0:
            state.update_task_status(i + 1, "completed")
        elif i == 1:
            state.update_task_status(i + 1, "in_progress")


def priority_badge(priority: TaskPriority):
    """Render priority badge"""
    colors = {
        TaskPriority.LOW: "bg-green-100 text-green-800",
        TaskPriority.MEDIUM: "bg-yellow-100 text-yellow-800",
        TaskPriority.HIGH: "bg-red-100 text-red-800",
    }

    return ps.span(
        priority.value.title(),
        className=f"px-2 py-1 text-xs font-medium rounded-full {colors[priority]}",
    )


def status_badge(status: TaskStatus):
    """Render status badge"""
    colors = {
        TaskStatus.TODO: "bg-gray-100 text-gray-800",
        TaskStatus.IN_PROGRESS: "bg-blue-100 text-blue-800",
        TaskStatus.COMPLETED: "bg-green-100 text-green-800",
    }

    labels = {
        TaskStatus.TODO: "To Do",
        TaskStatus.IN_PROGRESS: "In Progress",
        TaskStatus.COMPLETED: "Completed",
    }

    return ps.span(
        labels[status],
        className=f"px-2 py-1 text-xs font-medium rounded-full {colors[status]}",
    )


def task_card(task: Task, state: AppState):
    """Render a task card"""

    def handle_status_change(new_status):
        def handler():
            state.update_task_status(task.id, new_status)

        return handler

    def handle_delete():
        state.delete_task(task.id)

    return ps.div(
        ps.div(
            # Header
            ps.div(
                ps.div(
                    ps.h3(task.title, className="text-lg font-semibold text-gray-900"),
                    ps.p(task.description, className="text-gray-600 mt-1"),
                    className="flex-1",
                ),
                ps.div(
                    priority_badge(task.priority),
                    status_badge(task.status),
                    className="flex gap-2",
                ),
                className="flex justify-between items-start mb-4",
            ),
            # Meta info
            ps.div(
                ps.div(
                    ps.span("👤", className="mr-1"),
                    ps.span(
                        task.assigned_to or "Unassigned",
                        className="text-sm text-gray-600",
                    ),
                    className="flex items-center",
                ),
                ps.div(
                    ps.span("📅", className="mr-1"),
                    ps.span(
                        task.due_date.strftime("%Y-%m-%d")
                        if task.due_date
                        else "No due date",
                        className="text-sm text-gray-600",
                    ),
                    className="flex items-center",
                ),
                className="flex gap-4 mb-4",
            ),
            # Actions
            ps.div(
                ps.select(
                    ps.option("To Do", value="todo"),
                    ps.option("In Progress", value="in_progress"),
                    ps.option("Completed", value="completed"),
                    value=task.status.value,
                    onChange=lambda e: handle_status_change(e.target.value)(),
                    className="px-3 py-1 border border-gray-300 rounded-md text-sm",
                ),
                ps.button(
                    "🗑️ Delete",
                    onClick=handle_delete,
                    className="px-3 py-1 bg-red-500 text-white rounded-md text-sm hover:bg-red-600",
                ),
                className="flex justify-between items-center",
            ),
            className="p-4",
        ),
        className="bg-white rounded-lg shadow-md border border-gray-200 hover:shadow-lg transition-shadow",
    )


def task_form(form_state: FormState, app_state: AppState):
    """Render task creation form"""

    def handle_submit():
        if form_state.validate():
            app_state.add_task(
                form_state.title,
                form_state.description,
                form_state.priority,
                form_state.due_date,
            )
            form_state.reset_form()
            form_state.show_form = False

    def input_field(label: str, value: str, field: str, input_type: str = "text"):
        error = form_state.errors.get(field)

        return ps.div(
            ps.label(label, className="block text-sm font-medium text-gray-700 mb-1"),
            ps.input(
                type=input_type,
                value=value,
                onChange=lambda e: setattr(form_state, field, e.target.value),
                className=f"w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 {'border-red-500' if error else 'border-gray-300'}",
            ),
            *([ps.p(error, className="text-red-500 text-sm mt-1")] if error else []),
            className="mb-4",
        )

    if not form_state.show_form:
        return ps.div()  # Return empty div instead of None

    return ps.div(
        ps.div(
            ps.div(
                ps.h3("Create New Task", className="text-lg font-semibold mb-4"),
                ps.button(
                    "✕",
                    onClick=form_state.toggle_form,
                    className="text-gray-500 hover:text-gray-700",
                ),
                className="flex justify-between items-center",
            ),
            input_field("Title", form_state.title, "title"),
            ps.div(
                ps.label(
                    "Description",
                    className="block text-sm font-medium text-gray-700 mb-1",
                ),
                ps.textarea(
                    form_state.description,
                    onChange=lambda e: setattr(
                        form_state, "description", e.target.value
                    ),
                    rows=3,
                    className=f"w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 {'border-red-500' if form_state.errors.get('description') else 'border-gray-300'}",
                ),
                *(
                    [
                        ps.p(
                            str(form_state.errors.get("description")),
                            className="text-red-500 text-sm mt-1",
                        )
                    ]
                    if form_state.errors.get("description")
                    else []
                ),
                className="mb-4",
            ),
            ps.div(
                ps.label(
                    "Priority", className="block text-sm font-medium text-gray-700 mb-1"
                ),
                ps.select(
                    ps.option("Low", value="low"),
                    ps.option("Medium", value="medium"),
                    ps.option("High", value="high"),
                    value=form_state.priority,
                    onChange=lambda e: setattr(form_state, "priority", e.target.value),
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
                ),
                className="mb-4",
            ),
            input_field("Due Date", form_state.due_date, "due_date", "date"),
            ps.div(
                ps.button(
                    "Cancel",
                    onClick=form_state.toggle_form,
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 mr-2",
                ),
                ps.button(
                    "Create Task",
                    onClick=handle_submit,
                    className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600",
                ),
                className="flex justify-end",
            ),
            className="bg-white p-6 rounded-lg shadow-lg max-w-md w-full",
        ),
        className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
    )


@ps.route("/demo")
def task_dashboard():
    """Main task dashboard"""
    state, form_state = ps.init(lambda: (AppState(), FormState()))

    # Initialize sample data on first load
    if not state.tasks:
        init_sample_data(state)

    filtered_tasks = state.get_filtered_tasks()
    stats = state.get_task_stats()

    return ps.div(
        # Header
        ps.nav(
            ps.div(
                ps.h1("📋 TaskFlow Demo", className="text-xl font-bold text-white"),
                ps.button(
                    "➕ New Task",
                    onClick=form_state.toggle_form,
                    className="px-4 py-2 bg-white bg-opacity-20 text-white rounded-md hover:bg-opacity-30 transition-colors",
                ),
                className="flex items-center justify-between",
            ),
            className="bg-blue-600 p-4 shadow-lg",
        ),
        # Main content
        ps.div(
            # Stats cards
            ps.div(
                ps.div(
                    ps.div("📋", className="text-3xl mb-2"),
                    ps.div(
                        str(stats["total"]), className="text-2xl font-bold text-white"
                    ),
                    ps.div("Total Tasks", className="text-sm text-white opacity-80"),
                    className="text-center p-6 bg-gradient-to-br from-blue-400 to-blue-600 rounded-lg shadow-md",
                ),
                ps.div(
                    ps.div("✅", className="text-3xl mb-2"),
                    ps.div(
                        str(stats["completed"]),
                        className="text-2xl font-bold text-white",
                    ),
                    ps.div("Completed", className="text-sm text-white opacity-80"),
                    className="text-center p-6 bg-gradient-to-br from-green-400 to-green-600 rounded-lg shadow-md",
                ),
                ps.div(
                    ps.div("🔄", className="text-3xl mb-2"),
                    ps.div(
                        str(stats["in_progress"]),
                        className="text-2xl font-bold text-white",
                    ),
                    ps.div("In Progress", className="text-sm text-white opacity-80"),
                    className="text-center p-6 bg-gradient-to-br from-yellow-400 to-yellow-600 rounded-lg shadow-md",
                ),
                ps.div(
                    ps.div("📝", className="text-3xl mb-2"),
                    ps.div(
                        str(stats["todo"]), className="text-2xl font-bold text-white"
                    ),
                    ps.div("To Do", className="text-sm text-white opacity-80"),
                    className="text-center p-6 bg-gradient-to-br from-gray-400 to-gray-600 rounded-lg shadow-md",
                ),
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8",
            ),
            # Completion progress bar
            ps.div(
                ps.h3("Completion Progress", className="text-xl font-semibold mb-4"),
                ps.div(
                    ps.div(
                        style={
                            "width": f"{stats['completion_rate']}%",
                            "height": "20px",
                            "backgroundColor": "#10b981",
                            "borderRadius": "10px",
                            "transition": "width 0.3s ease",
                        }
                    ),
                    className="w-full bg-gray-200 rounded-full h-5",
                ),
                ps.p(
                    f"{stats['completion_rate']}% of tasks completed",
                    className="text-sm text-gray-600 mt-2",
                ),
                className="bg-white p-6 rounded-lg shadow-md mb-8",
            ),
            # Filters
            ps.div(
                ps.input(
                    type="text",
                    placeholder="Search tasks...",
                    value=state.search_query,
                    onChange=lambda e: setattr(state, "search_query", e.target.value),
                    className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
                ),
                ps.select(
                    ps.option("All Statuses", value="all"),
                    ps.option("To Do", value="todo"),
                    ps.option("In Progress", value="in_progress"),
                    ps.option("Completed", value="completed"),
                    value=state.filter_status,
                    onChange=lambda e: setattr(state, "filter_status", e.target.value),
                    className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
                ),
                ps.select(
                    ps.option("All Priorities", value="all"),
                    ps.option("Low", value="low"),
                    ps.option("Medium", value="medium"),
                    ps.option("High", value="high"),
                    value=state.filter_priority,
                    onChange=lambda e: setattr(
                        state, "filter_priority", e.target.value
                    ),
                    className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
                ),
                className="flex gap-4 items-center mb-6 bg-white p-4 rounded-lg shadow-md",
            ),
            # Task header
            ps.div(
                ps.div(
                    ps.h2(
                        "Task Management",
                        className="text-2xl font-semibold text-gray-900",
                    ),
                    ps.p(
                        f"Showing {len(filtered_tasks)} of {len(state.tasks)} tasks",
                        className="text-gray-600",
                    ),
                ),
                ps.button(
                    "🔄 Refresh",
                    onClick=lambda: print("🔄 Refreshing tasks..."),
                    className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200",
                ),
                className="flex justify-between items-center mb-6",
            ),
            # Tasks grid
            ps.div(
                *[task_card(task, state) for task in filtered_tasks]
                if filtered_tasks
                else [
                    ps.div(
                        ps.div("📭", className="text-6xl mb-4"),
                        ps.h3(
                            "No tasks found",
                            className="text-xl font-semibold text-gray-600 mb-2",
                        ),
                        ps.p(
                            "Create your first task or adjust your filters",
                            className="text-gray-500",
                        ),
                        ps.button(
                            "Create First Task",
                            onClick=form_state.toggle_form,
                            className="mt-4 px-6 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600",
                        ),
                        className="text-center py-12",
                    )
                ],
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
            ),
            className="container mx-auto px-4 py-8",
        ),
        # Task creation form modal
        task_form(form_state, state),
        className="min-h-screen bg-gray-50",
    )


# Create the demo app
app = ps.App(routes=[*ps.decorated_routes()])
