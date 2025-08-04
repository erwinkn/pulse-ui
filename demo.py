"""
Pulse UI Feature Showcase Demo

This demo showcases ALL of Pulse's features with beautiful Tailwind styling:
- ✅ Rendering (HTML elements & components)
- ✅ Reactive state (State classes)
- ✅ Computed variables (@computed decorator)
- ✅ Effects (ps.Effect for side effects)
- ✅ Nested routes (parent/child routing)
- ✅ Layouts (persistent layouts)
- ✅ Callbacks (event handlers)
- ✅ Wrapped React components (ReactComponent integration)
"""

import pulse as ps
from typing import List, Optional
from datetime import datetime
import random


# ============================================================================
# Reactive Components Examples
# ============================================================================

# Define wrapped React components
CustomDatePicker = ps.ReactComponent(
    "DatePicker",
    "~/components/date-picker",
    is_default=True,
)


class CounterState(ps.State):
    """Demonstrates reactive state with computed properties and effects"""

    count: int = 0
    multiplier: int = 2
    history: List[int] = []
    last_updated: Optional[datetime] = None

    @ps.computed
    def doubled_count(self) -> int:
        """Computed property that automatically updates when count changes"""
        return self.count * self.multiplier

    @ps.computed
    def is_even(self) -> bool:
        """Another computed property"""
        return self.count % 2 == 0

    @ps.computed
    def progress_percentage(self) -> float:
        """Progress as percentage (0-100)"""
        return min((abs(self.count) / 50) * 100, 100)

    def increment(self):
        """Increment counter and track history"""
        self.count += 1
        self.history = [*self.history, self.count]
        self.last_updated = datetime.now()
        print(f"🔢 Counter incremented to {self.count}")

    def decrement(self):
        """Decrement counter and track history"""
        self.count -= 1
        self.history = [*self.history, self.count]
        self.last_updated = datetime.now()
        print(f"🔢 Counter decremented to {self.count}")

    def reset(self):
        """Reset counter"""
        self.count = 0
        self.history.append(self.count)
        self.last_updated = datetime.now()
        print("🔄 Counter reset!")

    def set_multiplier(self, value: int):
        """Change the multiplier for computed property"""
        self.multiplier = value
        print(f"✖️ Multiplier set to {value}")


class EffectsState(ps.State):
    """Demonstrates effects and side effects"""

    timer_count: int = 0
    is_timer_running: bool = False
    notifications: List[str] = []
    auto_save_enabled: bool = True
    form_data: str = ""
    _initialized: bool = False

    def __init__(self):
        super().__init__()
        self._initialized = True

    @ps.effect
    def _timer_effect(self):
        """Effect that logs timer ticks."""
        if self.is_timer_running and self.timer_count < 10:
            print(f"⏱️ Timer tick: {self.timer_count}")

    @ps.effect
    def _auto_save_effect(self):
        """Effect that auto-saves form data."""
        # This will run on init, and when self.form_data or self.auto_save_enabled changes
        print("Running _auto_save_effect")
        if self._initialized and self.auto_save_enabled and self.form_data:
            self.add_notification(f"Auto-saved: '{self.form_data[:20]}...'")

    def start_timer(self):
        """Start a timer effect"""
        if not self.is_timer_running:
            self.is_timer_running = True
            print("⏰ Timer started!")

    def stop_timer(self):
        """Stop the timer"""
        self.is_timer_running = False
        print("⏹️ Timer stopped!")

    def tick_timer(self):
        """Manual timer tick for demo purposes"""
        if self.is_timer_running and self.timer_count < 10:
            self.timer_count += 1
            self.add_notification(f"Timer: {self.timer_count}")

    def toggle_auto_save(self):
        self.auto_save_enabled = not self.auto_save_enabled

    def reset_timer(self):
        """Reset the timer"""
        self.timer_count = 0
        self.is_timer_running = False
        print("🔄 Timer reset!")

    def add_notification(self, message: str):
        """Add a notification"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        with ps.untrack():
            new_notifications = self.notifications + [f"[{timestamp}] {message}"]
            # Keep only last 5 notifications
            self.notifications = new_notifications[-5:]

    def clear_notifications(self):
        """Clear all notifications"""
        self.notifications = []
        print("🧹 Notifications cleared!")

    def update_form_data(self, data: str):
        """Update form data and trigger auto-save effect"""
        self.form_data = data


class ThemeState(ps.State):
    """Global theme state for layout"""

    theme: str = "light"
    sidebar_open: bool = True

    @ps.computed
    def theme_classes(self) -> str:
        """Computed theme classes"""
        if self.theme == "dark":
            return "bg-gray-900 text-white"
        return "bg-white text-gray-900"

    @ps.computed
    def header_classes(self) -> str:
        """Computed header classes"""
        if self.theme == "dark":
            return "bg-gray-800 border-gray-700"
        return "bg-blue-600 border-blue-700"

    def toggle_theme(self):
        """Toggle between light and dark theme"""
        self.theme = "dark" if self.theme == "light" else "light"
        print(f"🎨 Theme switched to {self.theme}")

    def toggle_sidebar(self):
        """Toggle sidebar visibility"""
        self.sidebar_open = not self.sidebar_open
        print(f"📱 Sidebar {'opened' if self.sidebar_open else 'closed'}")


# ============================================================================
# Component Showcase Functions
# ============================================================================


def counter_showcase(state: CounterState):
    """Showcase reactive state and computed properties"""

    return ps.div(
        # Header
        ps.div(
            ps.h2(
                "🔢 Reactive State & Computed Properties",
                className="text-2xl font-bold text-gray-800 mb-2",
            ),
            ps.p(
                "State automatically triggers re-renders. Computed properties update automatically.",
                className="text-gray-600 mb-6",
            ),
            className="mb-8",
        ),
        # Main counter display
        ps.div(
            ps.div(
                ps.div(
                    ps.div(
                        ps.span(
                            str(state.count),
                            className="text-6xl font-bold text-blue-600",
                        ),
                        ps.div("Current Count", className="text-sm text-gray-500 mt-2"),
                        className="text-center",
                    ),
                    ps.div(
                        ps.span(
                            str(state.doubled_count),
                            className="text-4xl font-bold text-green-600",
                        ),
                        ps.div(
                            f"× {state.multiplier} (computed)",
                            className="text-sm text-gray-500 mt-2",
                        ),
                        className="text-center",
                    ),
                    ps.div(
                        ps.span("✅" if state.is_even else "❌", className="text-4xl"),
                        ps.div(
                            "Is Even (computed)", className="text-sm text-gray-500 mt-2"
                        ),
                        className="text-center",
                    ),
                    className="grid grid-cols-3 gap-8 mb-8",
                ),
                # Progress bar (computed)
                ps.div(
                    ps.div(
                        "Progress to 50",
                        className="text-sm font-medium text-gray-700 mb-2",
                    ),
                    ps.div(
                        ps.div(
                            style={
                                "width": f"{state.progress_percentage}%",
                                "transition": "width 0.3s ease",
                            },
                            className="h-4 bg-blue-600 rounded-full",
                        ),
                        className="w-full bg-gray-200 rounded-full",
                    ),
                    ps.div(
                        f"{state.progress_percentage:.1f}%",
                        className="text-sm text-gray-600 mt-1",
                    ),
                    className="mb-8",
                ),
                # Controls
                ps.div(
                    ps.button(
                        "➖ Decrement",
                        onClick=state.decrement,
                        className="px-6 py-3 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors",
                    ),
                    ps.button(
                        "🔄 Reset",
                        onClick=state.reset,
                        className="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors",
                    ),
                    ps.button(
                        "➕ Increment",
                        onClick=state.increment,
                        className="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors",
                    ),
                    className="flex gap-4 justify-center mb-8",
                ),
                # Multiplier controls
                ps.div(
                    ps.div(
                        "Multiplier for computed property:",
                        className="text-sm font-medium text-gray-700 mb-2",
                    ),
                    ps.div(
                        *[
                            ps.button(
                                str(mult),
                                onClick=lambda m=mult: state.set_multiplier(m),
                                className=f"px-4 py-2 rounded-lg transition-colors {'bg-blue-600 text-white' if state.multiplier == mult else 'bg-gray-200 text-gray-700 hover:bg-gray-300'}",
                            )
                            for mult in [1, 2, 3, 5, 10]
                        ],
                        className="flex gap-2 justify-center",
                    ),
                    className="text-center mb-8",
                ),
                # History and info
                ps.div(
                    ps.div(
                        ps.h4(
                            "📊 State Info",
                            className="font-semibold text-gray-800 mb-2",
                        ),
                        ps.div(
                            f"Last updated: {state.last_updated.strftime('%H:%M:%S') if state.last_updated else 'Never'}",
                            className="text-sm text-gray-600",
                        ),
                        ps.div(
                            f"History length: {len(state.history)}",
                            className="text-sm text-gray-600",
                        ),
                        ps.div(
                            f"Recent values: {', '.join(map(str, state.history[-5:]))}",
                            className="text-sm text-gray-600",
                        ),
                        className="bg-gray-50 p-4 rounded-lg",
                    ),
                    className="max-w-md mx-auto",
                ),
                className="bg-white p-8 rounded-xl shadow-lg",
            ),
            className="mb-12",
        ),
    )


def effects_showcase(state: EffectsState):
    """Showcase effects and side effects"""

    return ps.div(
        # Header
        ps.div(
            ps.h2(
                "⚡ Effects & Side Effects",
                className="text-2xl font-bold text-gray-800 mb-2",
            ),
            ps.p(
                "Effects run when dependencies change and can have cleanup functions.",
                className="text-gray-600 mb-6",
            ),
            className="mb-8",
        ),
        ps.div(
            # Timer demo
            ps.div(
                ps.h3(
                    "⏰ Timer Effect Demo",
                    className="text-xl font-semibold text-gray-800 mb-4",
                ),
                ps.div(
                    ps.div(
                        ps.span(
                            str(state.timer_count),
                            className="text-4xl font-bold text-purple-600",
                        ),
                        ps.div("Timer Count", className="text-sm text-gray-500 mt-1"),
                        className="text-center",
                    ),
                    ps.div(
                        ps.span(
                            "🟢" if state.is_timer_running else "🔴",
                            className="text-2xl",
                        ),
                        ps.div("Timer Status", className="text-sm text-gray-500 mt-1"),
                        className="text-center",
                    ),
                    className="grid grid-cols-2 gap-4 mb-6",
                ),
                ps.div(
                    ps.button(
                        "▶️ Start",
                        onClick=state.start_timer,
                        className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors disabled:opacity-50",
                        disabled=state.is_timer_running,
                    ),
                    ps.button(
                        "⏯️ Tick",
                        onClick=state.tick_timer,
                        className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50",
                        disabled=not state.is_timer_running,
                    ),
                    ps.button(
                        "⏹️ Stop",
                        onClick=state.stop_timer,
                        className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50",
                        disabled=not state.is_timer_running,
                    ),
                    ps.button(
                        "🔄 Reset",
                        onClick=state.reset_timer,
                        className="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors",
                    ),
                    className="flex gap-2 justify-center",
                ),
                className="bg-purple-50 p-6 rounded-lg mb-6",
            ),
            # Auto-save effect demo
            ps.div(
                ps.h3(
                    "💾 Auto-Save Effect Demo",
                    className="text-xl font-semibold text-gray-800 mb-4",
                ),
                ps.div(
                    ps.label(
                        "Type something (auto-saves with effects):",
                        className="block text-sm font-medium text-gray-700 mb-2",
                    ),
                    ps.textarea(
                        value=state.form_data,
                        onChange=lambda e: state.update_form_data(e["target"]["value"]),
                        placeholder="Start typing to see auto-save effects...",
                        rows=4,
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                    ),
                    ps.div(
                        ps.input(
                            type="checkbox",
                            checked=state.auto_save_enabled,
                            onChange=state.toggle_auto_save,
                            className="mr-2",
                        ),
                        ps.span("Enable auto-save", className="text-sm text-gray-700"),
                        className="mt-2",
                    ),
                    className="mb-6",
                ),
                className="bg-blue-50 p-6 rounded-lg mb-6",
            ),
            # Notifications panel
            ps.div(
                ps.div(
                    ps.h3(
                        "🔔 Effect Notifications",
                        className="text-lg font-semibold text-gray-800 mb-2",
                    ),
                    ps.button(
                        "🧹 Clear",
                        onClick=state.clear_notifications,
                        className="px-3 py-1 bg-gray-500 text-white text-sm rounded hover:bg-gray-600 transition-colors",
                    ),
                    className="flex justify-between items-center mb-4",
                ),
                ps.div(
                    *[
                        ps.div(
                            notification,
                            className="text-sm text-gray-700 py-1 border-b border-gray-200 last:border-b-0",
                        )
                        for notification in state.notifications[-5:]
                    ]
                    if state.notifications
                    else [
                        ps.div(
                            "No notifications yet...",
                            className="text-sm text-gray-500 italic",
                        )
                    ],
                    className="bg-gray-50 p-4 rounded-lg max-h-40 overflow-y-auto",
                ),
                className="bg-gray-100 p-4 rounded-lg",
            ),
            className="bg-white p-8 rounded-xl shadow-lg",
        ),
        className="mb-12",
    )


def react_components_showcase():
    """Showcase wrapped React components"""

    def handle_date_change(date_string):
        print(f"📅 Custom DatePicker selected: {date_string}")

    def handle_native_date_change(event):
        print(f"📅 Native date input selected: {event['target']['value']}")

    def handle_file_change(event):
        files = event["target"]["files"]
        if files and len(files) > 0:
            print(f"📁 File selected: {files[0]['name']}")

    return ps.div(
        # Header
        ps.div(
            ps.h2(
                "⚛️ Wrapped React Components",
                className="text-2xl font-bold text-gray-800 mb-2",
            ),
            ps.p(
                "Integration with existing React components and HTML5 elements.",
                className="text-gray-600 mb-6",
            ),
            className="mb-8",
        ),
        ps.div(
            # Custom React Components Demo
            ps.div(
                ps.h3(
                    "⚛️ Custom React Components",
                    className="text-xl font-semibold text-gray-800 mb-6",
                ),
                ps.div(
                    # Custom DatePicker
                    ps.div(
                        ps.label(
                            "📅 Custom React DatePicker:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        CustomDatePicker(
                            placeholder="Select a date and time",
                            onChange=handle_date_change,
                            showTimeSelect=True,
                            className="mb-2",
                        ),
                        ps.p(
                            "This is a wrapped React component using react-datepicker library",
                            className="text-sm text-gray-500",
                        ),
                        className="mb-4",
                    ),
                    # Another DatePicker without time
                    ps.div(
                        ps.label(
                            "📅 Date Only Picker:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        # CustomDatePicker(
                        #     placeholder="Select a date",
                        #     onChange=handle_date_change,
                        #     showTimeSelect=False,
                        #     className="mb-2",
                        # ),
                        ps.p(
                            "Same component, different configuration",
                            className="text-sm text-gray-500",
                        ),
                        className="mb-4",
                    ),
                    className="grid grid-cols-1 md:grid-cols-2 gap-6",
                ),
                className="bg-gradient-to-br from-purple-50 to-indigo-50 p-6 rounded-lg mb-6",
            ),
            # HTML5 Input Types Demo
            ps.div(
                ps.h3(
                    "🎛️ HTML5 Input Components",
                    className="text-xl font-semibold text-gray-800 mb-6",
                ),
                ps.div(
                    # Native date input
                    ps.div(
                        ps.label(
                            "📅 Native Date Input:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        ps.input(
                            type="date",
                            onChange=handle_native_date_change,
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                        ),
                        className="mb-4",
                    ),
                    # Time input
                    ps.div(
                        ps.label(
                            "🕐 Time Picker:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        ps.input(
                            type="time",
                            onChange=lambda e: print(
                                f"🕐 Time selected: {e['target']['value']}"
                            ),
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                        ),
                        className="mb-4",
                    ),
                    # Color input
                    ps.div(
                        ps.label(
                            "🎨 Color Picker:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        ps.input(
                            type="color",
                            onChange=lambda e: print(
                                f"🎨 Color selected: {e['target']['value']}"
                            ),
                            className="w-full h-12 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                        ),
                        className="mb-4",
                    ),
                    # Range input
                    ps.div(
                        ps.label(
                            "🎚️ Range Slider:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        ps.input(
                            type="range",
                            min="0",
                            max="100",
                            onChange=lambda e: print(
                                f"🎚️ Range value: {e['target']['value']}"
                            ),
                            className="w-full",
                        ),
                        className="mb-4",
                    ),
                    # File input
                    ps.div(
                        ps.label(
                            "📁 File Upload:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        ps.input(
                            type="file",
                            onChange=handle_file_change,
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                        ),
                        className="mb-4",
                    ),
                    className="grid grid-cols-1 md:grid-cols-2 gap-6",
                ),
                className="bg-gradient-to-br from-blue-50 to-cyan-50 p-6 rounded-lg mb-6",
            ),
            # Advanced HTML5 elements
            ps.div(
                ps.h3(
                    "📊 Advanced HTML5 Elements",
                    className="text-xl font-semibold text-gray-800 mb-6",
                ),
                ps.div(
                    # Progress bar
                    ps.div(
                        ps.label(
                            "📊 Progress Bar:",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        ps.progress(
                            value="70",
                            max="100",
                            className="w-full h-4 [&::-webkit-progress-bar]:bg-gray-200 [&::-webkit-progress-bar]:rounded-lg [&::-webkit-progress-value]:bg-green-500 [&::-webkit-progress-value]:rounded-lg",
                        ),
                        ps.div("70% Complete", className="text-sm text-gray-600 mt-1"),
                        className="mb-4",
                    ),
                    # Meter
                    ps.div(
                        ps.label(
                            "📏 Meter (0.8/1.0):",
                            className="block text-sm font-medium text-gray-700 mb-2",
                        ),
                        ps.meter(value="0.8", min="0", max="1", className="w-full h-4"),
                        className="mb-4",
                    ),
                    # Details/Summary
                    ps.div(
                        ps.details(
                            ps.summary(
                                "🔍 Click to expand details",
                                className="cursor-pointer font-medium text-gray-700 mb-2",
                            ),
                            ps.div(
                                ps.p(
                                    "This is a collapsible details section!",
                                    className="text-gray-600 mb-2",
                                ),
                                ps.p(
                                    "You can put any content here, including other Pulse components.",
                                    className="text-gray-600",
                                ),
                                className="pl-4 border-l-2 border-blue-200",
                            ),
                            className="mb-4",
                        ),
                    ),
                    className="space-y-4",
                ),
                className="bg-gradient-to-br from-green-50 to-emerald-50 p-6 rounded-lg",
            ),
            className="bg-white p-8 rounded-xl shadow-lg",
        ),
        className="mb-12",
    )


class CallbacksState(ps.State):
    """State for callbacks demonstration"""

    click_count: int = 0
    last_event: str = "None"
    form_name: str = ""
    form_email: str = ""
    form_message: str = ""


def callbacks_showcase(state: CallbacksState):
    """Showcase different types of callbacks and event handling"""

    def handle_button_click(button_type: str):
        def handler():
            state.click_count += 1
            state.last_event = (
                f"{button_type} clicked at {datetime.now().strftime('%H:%M:%S')}"
            )
            print(f"🖱️ {button_type} button clicked! Total clicks: {state.click_count}")

        return handler

    def handle_form_change(field: str):
        def handler(event):
            setattr(state, f"form_{field}", event["target"]["value"])
            print(f"📝 Form field '{field}' changed to: {event['target']['value']}")

        return handler

    def handle_form_submit():
        print(
            f"📤 Form submitted with data: name={state.form_name}, email={state.form_email}, message={state.form_message}"
        )
        # Reset form
        state.form_name = ""
        state.form_email = ""
        state.form_message = ""

    def handle_key_press(event):
        print(f"⌨️ Key pressed: {event['key']}")

    def handle_mouse_move(event):
        # Only log occasionally to avoid spam
        if random.random() < 0.01:  # 1% chance
            print(f"🖱️ Mouse position: ({event['clientX']}, {event['clientY']})")

    return ps.div(
        # Header
        ps.div(
            ps.h2(
                "🖱️ Callbacks & Event Handling",
                className="text-2xl font-bold text-gray-800 mb-2",
            ),
            ps.p(
                "Comprehensive event handling with different callback patterns.",
                className="text-gray-600 mb-6",
            ),
            className="mb-8",
        ),
        ps.div(
            # Button callbacks
            ps.div(
                ps.h3(
                    "🔘 Button Events",
                    className="text-xl font-semibold text-gray-800 mb-4",
                ),
                ps.div(
                    ps.button(
                        "Primary Action",
                        onClick=handle_button_click("Primary"),
                        className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-lg hover:shadow-xl",
                    ),
                    ps.button(
                        "Secondary Action",
                        onClick=handle_button_click("Secondary"),
                        className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors shadow-lg hover:shadow-xl",
                    ),
                    ps.button(
                        "Danger Action",
                        onClick=handle_button_click("Danger"),
                        className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors shadow-lg hover:shadow-xl",
                    ),
                    className="flex gap-4 justify-center mb-4",
                ),
                ps.div(
                    ps.div(
                        f"Total clicks: {state.click_count}",
                        className="text-lg font-semibold text-gray-800",
                    ),
                    ps.div(
                        f"Last event: {state.last_event}",
                        className="text-sm text-gray-600",
                    ),
                    className="text-center bg-gray-50 p-4 rounded-lg",
                ),
                className="mb-8",
            ),
            # Form callbacks
            ps.div(
                ps.h3(
                    "📝 Form Events",
                    className="text-xl font-semibold text-gray-800 mb-4",
                ),
                ps.form(
                    ps.div(
                        ps.label(
                            "Name:",
                            className="block text-sm font-medium text-gray-700 mb-1",
                        ),
                        ps.input(
                            type="text",
                            value=state.form_name,
                            onChange=handle_form_change("name"),
                            onKeyPress=handle_key_press,
                            placeholder="Enter your name",
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                        ),
                        className="mb-4",
                    ),
                    ps.div(
                        ps.label(
                            "Email:",
                            className="block text-sm font-medium text-gray-700 mb-1",
                        ),
                        ps.input(
                            type="email",
                            value=state.form_email,
                            onChange=handle_form_change("email"),
                            placeholder="Enter your email",
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                        ),
                        className="mb-4",
                    ),
                    ps.div(
                        ps.label(
                            "Message:",
                            className="block text-sm font-medium text-gray-700 mb-1",
                        ),
                        ps.textarea(
                            state.form_message,
                            onChange=handle_form_change("message"),
                            placeholder="Enter your message",
                            rows=3,
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                        ),
                        className="mb-4",
                    ),
                    ps.button(
                        "Submit Form",
                        onClick=handle_form_submit,
                        type="button",
                        className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors",
                    ),
                    className="space-y-4",
                ),
                className="bg-green-50 p-6 rounded-lg mb-8",
            ),
            # Mouse events
            ps.div(
                ps.h3(
                    "🖱️ Mouse Events",
                    className="text-xl font-semibold text-gray-800 mb-4",
                ),
                ps.div(
                    "Move your mouse over this area and check the console!",
                    onMouseMove=handle_mouse_move,
                    className="w-full h-32 bg-gradient-to-br from-purple-200 to-pink-200 rounded-lg flex items-center justify-center text-gray-700 font-medium cursor-crosshair",
                ),
                className="bg-purple-50 p-6 rounded-lg",
            ),
            className="bg-white p-8 rounded-xl shadow-lg",
        ),
        className="mb-12",
    )


def rendering_showcase():
    """Showcase basic rendering capabilities"""

    return ps.div(
        # Header
        ps.div(
            ps.h2(
                "🎨 Rendering Showcase",
                className="text-2xl font-bold text-gray-800 mb-2",
            ),
            ps.p(
                "HTML elements, styling, and component composition.",
                className="text-gray-600 mb-6",
            ),
            className="mb-8",
        ),
        ps.div(
            # Typography
            ps.div(
                ps.h3(
                    "✍️ Typography", className="text-xl font-semibold text-gray-800 mb-4"
                ),
                ps.h1("Heading 1", className="text-4xl font-bold text-gray-900 mb-2"),
                ps.h2("Heading 2", className="text-3xl font-bold text-gray-800 mb-2"),
                ps.h3("Heading 3", className="text-2xl font-bold text-gray-700 mb-2"),
                ps.h4("Heading 4", className="text-xl font-bold text-gray-600 mb-2"),
                ps.p(
                    "Regular paragraph text with ",
                    ps.strong("bold"),
                    " and ",
                    ps.em("italic"),
                    " formatting.",
                ),
                ps.p(
                    "Another paragraph with ",
                    ps.code("inline code", className="bg-gray-100 px-1 rounded"),
                    " styling.",
                ),
                ps.blockquote(
                    "This is a blockquote example to showcase text styling capabilities.",
                    className="border-l-4 border-blue-500 pl-4 italic text-gray-700 my-4",
                ),
                className="mb-8",
            ),
            # Lists
            ps.div(
                ps.h3("📋 Lists", className="text-xl font-semibold text-gray-800 mb-4"),
                ps.div(
                    ps.div(
                        ps.h4(
                            "Unordered List:",
                            className="font-semibold text-gray-700 mb-2",
                        ),
                        ps.ul(
                            ps.li("First item", className="mb-1"),
                            ps.li("Second item", className="mb-1"),
                            ps.li("Third item", className="mb-1"),
                            className="list-disc list-inside text-gray-600",
                        ),
                    ),
                    ps.div(
                        ps.h4(
                            "Ordered List:",
                            className="font-semibold text-gray-700 mb-2",
                        ),
                        ps.ol(
                            ps.li("Step one", className="mb-1"),
                            ps.li("Step two", className="mb-1"),
                            ps.li("Step three", className="mb-1"),
                            className="list-decimal list-inside text-gray-600",
                        ),
                    ),
                    className="grid grid-cols-1 md:grid-cols-2 gap-6",
                ),
                className="mb-8",
            ),
            # Tables
            ps.div(
                ps.h3(
                    "📊 Tables", className="text-xl font-semibold text-gray-800 mb-4"
                ),
                ps.table(
                    ps.thead(
                        ps.tr(
                            ps.th(
                                "Feature",
                                className="px-4 py-2 bg-gray-50 font-semibold text-left",
                            ),
                            ps.th(
                                "Status",
                                className="px-4 py-2 bg-gray-50 font-semibold text-left",
                            ),
                            ps.th(
                                "Priority",
                                className="px-4 py-2 bg-gray-50 font-semibold text-left",
                            ),
                        )
                    ),
                    ps.tbody(
                        ps.tr(
                            ps.td("Reactive State", className="px-4 py-2 border-t"),
                            ps.td(
                                ps.span("✅ Complete", className="text-green-600"),
                                className="px-4 py-2 border-t",
                            ),
                            ps.td(
                                ps.span(
                                    "High",
                                    className="px-2 py-1 bg-red-100 text-red-800 rounded text-sm",
                                ),
                                className="px-4 py-2 border-t",
                            ),
                        ),
                        ps.tr(
                            ps.td(
                                "Computed Properties", className="px-4 py-2 border-t"
                            ),
                            ps.td(
                                ps.span("✅ Complete", className="text-green-600"),
                                className="px-4 py-2 border-t",
                            ),
                            ps.td(
                                ps.span(
                                    "High",
                                    className="px-2 py-1 bg-red-100 text-red-800 rounded text-sm",
                                ),
                                className="px-4 py-2 border-t",
                            ),
                        ),
                        ps.tr(
                            ps.td("Effects", className="px-4 py-2 border-t"),
                            ps.td(
                                ps.span("✅ Complete", className="text-green-600"),
                                className="px-4 py-2 border-t",
                            ),
                            ps.td(
                                ps.span(
                                    "Medium",
                                    className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-sm",
                                ),
                                className="px-4 py-2 border-t",
                            ),
                        ),
                    ),
                    className="w-full border border-gray-200 rounded-lg overflow-hidden",
                ),
                className="mb-8",
            ),
            # Cards and layouts
            ps.div(
                ps.h3(
                    "🃏 Cards & Layouts",
                    className="text-xl font-semibold text-gray-800 mb-4",
                ),
                ps.div(
                    ps.div(
                        ps.div("🎯", className="text-3xl mb-3"),
                        ps.h4(
                            "Feature Rich",
                            className="text-lg font-semibold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Comprehensive feature set with modern styling.",
                            className="text-gray-600",
                        ),
                        className="bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-lg text-center",
                    ),
                    ps.div(
                        ps.div("⚡", className="text-3xl mb-3"),
                        ps.h4(
                            "High Performance",
                            className="text-lg font-semibold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Reactive updates with minimal re-renders.",
                            className="text-gray-600",
                        ),
                        className="bg-gradient-to-br from-green-50 to-green-100 p-6 rounded-lg text-center",
                    ),
                    ps.div(
                        ps.div("🎨", className="text-3xl mb-3"),
                        ps.h4(
                            "Beautiful UI",
                            className="text-lg font-semibold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Tailwind CSS integration for stunning designs.",
                            className="text-gray-600",
                        ),
                        className="bg-gradient-to-br from-purple-50 to-purple-100 p-6 rounded-lg text-center",
                    ),
                    className="grid grid-cols-1 md:grid-cols-3 gap-6",
                ),
            ),
            className="bg-white p-8 rounded-xl shadow-lg",
        ),
        className="mb-12",
    )


# ============================================================================
# Route Components
# ============================================================================


@ps.component
def home():
    """Home page with overview of all features"""
    return ps.div(
        # Hero section
        ps.div(
            ps.div(
                ps.h1(
                    "🚀 Pulse UI Feature Showcase",
                    className="text-5xl font-bold text-white mb-4 text-center",
                ),
                ps.p(
                    "A comprehensive demonstration of all Pulse UI capabilities",
                    className="text-xl text-blue-100 text-center mb-8",
                ),
                ps.div(
                    ps.Link(
                        "🔍 Explore Features",
                        to="/features",
                        className="px-8 py-4 bg-white text-blue-600 rounded-lg hover:bg-blue-50 transition-colors font-semibold shadow-lg hover:shadow-xl",
                    ),
                    ps.Link(
                        "🧪 Interactive Demo",
                        to="/demo",
                        className="px-8 py-4 bg-blue-700 text-white rounded-lg hover:bg-blue-800 transition-colors font-semibold shadow-lg hover:shadow-xl",
                    ),
                    className="flex gap-4 justify-center",
                ),
                className="container mx-auto px-4 py-16",
            ),
            className="bg-gradient-to-br from-blue-600 to-purple-700",
        ),
        # Features overview
        ps.div(
            ps.div(
                ps.h2(
                    "✨ What's Included",
                    className="text-3xl font-bold text-center text-gray-800 mb-12",
                ),
                ps.div(
                    ps.div(
                        ps.div("🎨", className="text-4xl mb-4"),
                        ps.h3(
                            "Rendering",
                            className="text-xl font-bold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "HTML elements, components, and beautiful styling with Tailwind CSS.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    ps.div(
                        ps.div("🔄", className="text-4xl mb-4"),
                        ps.h3(
                            "Reactive State",
                            className="text-xl font-bold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Automatic re-rendering when state changes, with reactive properties.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    ps.div(
                        ps.div("🧮", className="text-4xl mb-4"),
                        ps.h3(
                            "Computed Variables",
                            className="text-xl font-bold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Derived state that updates automatically when dependencies change.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    ps.div(
                        ps.div("⚡", className="text-4xl mb-4"),
                        ps.h3(
                            "Effects", className="text-xl font-bold text-gray-800 mb-2"
                        ),
                        ps.p(
                            "Side effects that run when dependencies change, with cleanup support.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    ps.div(
                        ps.div("🗂️", className="text-4xl mb-4"),
                        ps.h3(
                            "Nested Routes",
                            className="text-xl font-bold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Hierarchical routing with layouts and nested components.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    ps.div(
                        ps.div("🎯", className="text-4xl mb-4"),
                        ps.h3(
                            "Layouts", className="text-xl font-bold text-gray-800 mb-2"
                        ),
                        ps.p(
                            "Persistent layouts that wrap multiple routes with shared state.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    ps.div(
                        ps.div("🖱️", className="text-4xl mb-4"),
                        ps.h3(
                            "Callbacks",
                            className="text-xl font-bold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Event handlers for user interactions with full event object access.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    ps.div(
                        ps.div("⚛️", className="text-4xl mb-4"),
                        ps.h3(
                            "React Components",
                            className="text-xl font-bold text-gray-800 mb-2",
                        ),
                        ps.p(
                            "Seamless integration with existing React components and libraries.",
                            className="text-gray-600",
                        ),
                        className="text-center p-6 bg-white rounded-xl shadow-lg hover:shadow-xl transition-shadow",
                    ),
                    className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8",
                ),
                className="container mx-auto px-4 py-16",
            ),
            className="bg-gray-50",
        ),
        # CTA section
        ps.div(
            ps.div(
                ps.h2(
                    "🎯 Ready to Explore?",
                    className="text-3xl font-bold text-center text-gray-800 mb-6",
                ),
                ps.p(
                    "Dive into each feature with interactive examples and see Pulse UI in action.",
                    className="text-xl text-gray-600 text-center mb-8",
                ),
                ps.div(
                    ps.Link(
                        "📚 Feature Documentation",
                        to="/features",
                        className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-semibold",
                    ),
                    ps.Link(
                        "🧪 Try the Demo",
                        to="/demo",
                        className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-semibold",
                    ),
                    className="flex gap-4 justify-center",
                ),
                className="container mx-auto px-4 py-16",
            ),
            className="bg-white",
        ),
    )


@ps.component
def features():
    """Features showcase page"""
    # Initialize all states needed for this route
    counter_state, effects_state, callbacks_state = ps.init(
        lambda: (CounterState(), EffectsState(), CallbacksState())
    )

    return ps.div(
        ps.div(
            ps.h1(
                "🔍 Feature Showcase",
                className="text-4xl font-bold text-center text-gray-800 mb-2",
            ),
            ps.p(
                "Interactive demonstrations of every Pulse UI capability",
                className="text-xl text-gray-600 text-center mb-8",
            ),
            className="container mx-auto px-4 py-8",
        ),
        # Feature showcases
        ps.div(
            rendering_showcase(),
            counter_showcase(counter_state),
            effects_showcase(effects_state),
            callbacks_showcase(callbacks_state),
            react_components_showcase(),
            className="container mx-auto px-4",
        ),
        className="min-h-screen bg-gray-50",
    )


@ps.component
def demo():
    """Interactive demo page"""
    return ps.div(
        ps.div(
            ps.h1(
                "🧪 Interactive Demo",
                className="text-4xl font-bold text-center text-gray-800 mb-2",
            ),
            ps.p(
                "Try out Pulse UI features in this interactive playground",
                className="text-xl text-gray-600 text-center mb-8",
            ),
            className="container mx-auto px-4 py-8",
        ),
        ps.div(
            ps.Outlet(),  # Child routes will render here
            className="container mx-auto px-4",
        ),
        className="min-h-screen bg-gray-50",
    )


@ps.component
def demo_counter():
    """Counter demo child route"""
    counter_state = ps.init(lambda: CounterState())
    return counter_showcase(counter_state)


@ps.component
def demo_effects():
    """Effects demo child route"""
    effects_state = ps.init(lambda: EffectsState())
    return effects_showcase(effects_state)


@ps.component
def demo_callbacks():
    """Callbacks demo child route"""
    callbacks_state = ps.init(lambda: CallbacksState())
    return callbacks_showcase(callbacks_state)


@ps.component
def about():
    """About page"""
    return ps.div(
        ps.div(
            ps.h1(
                "ℹ️ About Pulse UI",
                className="text-4xl font-bold text-center text-gray-800 mb-6",
            ),
            ps.div(
                ps.div(
                    ps.h2(
                        "🎯 What is Pulse UI?",
                        className="text-2xl font-bold text-gray-800 mb-4",
                    ),
                    ps.p(
                        "Pulse UI is a revolutionary Python framework that bridges the gap between Python backend logic and modern React frontend development. It allows you to write your entire web application in Python while automatically generating TypeScript and React code.",
                        className="text-lg text-gray-600 mb-6",
                    ),
                    ps.h2(
                        "🚀 Key Advantages",
                        className="text-2xl font-bold text-gray-800 mb-4",
                    ),
                    ps.ul(
                        ps.li(
                            "📝 Write your entire app in Python - no context switching",
                            className="mb-2",
                        ),
                        ps.li(
                            "⚡ Reactive state management with automatic re-renders",
                            className="mb-2",
                        ),
                        ps.li(
                            "🧮 Computed properties that update automatically",
                            className="mb-2",
                        ),
                        ps.li(
                            "🔄 Effects for side effects with cleanup", className="mb-2"
                        ),
                        ps.li("🗂️ Nested routing with layouts", className="mb-2"),
                        ps.li(
                            "⚛️ Seamless React component integration", className="mb-2"
                        ),
                        ps.li("🎨 Beautiful UIs with Tailwind CSS", className="mb-2"),
                        ps.li(
                            "🔧 TypeScript generation for type safety", className="mb-2"
                        ),
                        className="text-lg text-gray-600 list-disc list-inside mb-6",
                    ),
                    ps.h2(
                        "🛠️ How It Works",
                        className="text-2xl font-bold text-gray-800 mb-4",
                    ),
                    ps.div(
                        ps.div(
                            ps.div("1️⃣", className="text-3xl mb-2"),
                            ps.h3(
                                "Define Components",
                                className="text-lg font-bold text-gray-800 mb-2",
                            ),
                            ps.p(
                                "Write Python functions decorated with @ps.component",
                                className="text-gray-600",
                            ),
                            className="text-center p-4 bg-blue-50 rounded-lg",
                        ),
                        ps.div("➡️", className="text-2xl text-gray-400 self-center"),
                        ps.div(
                            ps.div("2️⃣", className="text-3xl mb-2"),
                            ps.h3(
                                "Manage State",
                                className="text-lg font-bold text-gray-800 mb-2",
                            ),
                            ps.p(
                                "Use ps.State classes with reactive properties",
                                className="text-gray-600",
                            ),
                            className="text-center p-4 bg-green-50 rounded-lg",
                        ),
                        ps.div("➡️", className="text-2xl text-gray-400 self-center"),
                        ps.div(
                            ps.div("3️⃣", className="text-3xl mb-2"),
                            ps.h3(
                                "Auto Generation",
                                className="text-lg font-bold text-gray-800 mb-2",
                            ),
                            ps.p(
                                "Pulse generates TypeScript and React code automatically",
                                className="text-gray-600",
                            ),
                            className="text-center p-4 bg-purple-50 rounded-lg",
                        ),
                        className="grid grid-cols-1 md:grid-cols-7 gap-4 items-center mb-8",
                    ),
                    ps.h2(
                        "📚 Learn More",
                        className="text-2xl font-bold text-gray-800 mb-4",
                    ),
                    ps.div(
                        ps.Link(
                            "🔍 Explore Features",
                            to="/features",
                            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-semibold",
                        ),
                        ps.Link(
                            "🧪 Try the Demo",
                            to="/demo",
                            className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-semibold",
                        ),
                        ps.a(
                            "📖 Documentation",
                            href="https://github.com/yourusername/pulse-ui",
                            className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold",
                        ),
                        className="flex gap-4 justify-center",
                    ),
                    className="max-w-4xl mx-auto",
                ),
                className="bg-white p-8 rounded-xl shadow-lg",
            ),
            className="container mx-auto px-4 py-8",
        ),
        className="min-h-screen bg-gray-50",
    )


@ps.component
def main_layout():
    """Main application layout with navigation and theme"""
    theme_state = ps.init(lambda: ThemeState())

    return ps.div(
        # Header
        ps.header(
            ps.div(
                # Logo and title
                ps.div(
                    ps.h1(
                        "🚀 Pulse UI Demo", className="text-2xl font-bold text-white"
                    ),
                    ps.p("Feature Showcase", className="text-blue-100 text-sm"),
                    className="flex-1",
                ),
                # Navigation
                ps.nav(
                    ps.Link(
                        "🏠 Home",
                        to="/",
                        className="px-4 py-2 text-white hover:bg-white hover:bg-opacity-20 rounded-lg transition-colors",
                    ),
                    ps.Link(
                        "🔍 Features",
                        to="/features",
                        className="px-4 py-2 text-white hover:bg-white hover:bg-opacity-20 rounded-lg transition-colors",
                    ),
                    ps.Link(
                        "🧪 Demo",
                        to="/demo",
                        className="px-4 py-2 text-white hover:bg-white hover:bg-opacity-20 rounded-lg transition-colors",
                    ),
                    ps.Link(
                        "ℹ️ About",
                        to="/about",
                        className="px-4 py-2 text-white hover:bg-white hover:bg-opacity-20 rounded-lg transition-colors",
                    ),
                    className="hidden md:flex items-center space-x-2",
                ),
                # Theme toggle
                ps.button(
                    "🌙" if theme_state.theme == "light" else "☀️",
                    onClick=theme_state.toggle_theme,
                    title=f"Switch to {'dark' if theme_state.theme == 'light' else 'light'} mode",
                    className="px-3 py-2 text-white hover:bg-white hover:bg-opacity-20 rounded-lg transition-colors",
                ),
                className="flex items-center justify-between",
            ),
            className=f"px-4 py-4 shadow-lg {theme_state.header_classes}",
        ),
        # Main content
        ps.main(ps.Outlet(), className=theme_state.theme_classes),
        # Footer
        ps.footer(
            ps.div(
                ps.p(
                    "Built with ❤️ using Pulse UI • Python + React + TypeScript",
                    className="text-center text-gray-600",
                ),
                ps.div(
                    ps.span(
                        f"Theme: {theme_state.theme.title()}",
                        className="text-sm text-gray-500 mr-4",
                    ),
                    ps.span(
                        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        className="text-sm text-gray-500",
                    ),
                    className="text-center mt-2",
                ),
                className="container mx-auto px-4 py-8",
            ),
            className="bg-gray-100 border-t border-gray-200",
        ),
        className=f"min-h-screen {theme_state.theme_classes}",
    )


# ============================================================================
# Application Setup
# ============================================================================

# Create the Pulse app with nested routes
app = ps.App(
    routes=[
        ps.Layout(
            main_layout,
            children=[
                ps.Route("/", home),
                ps.Route("/features", features),
                ps.Route("/about", about),
                ps.Route(
                    "/demo",
                    demo,
                    children=[
                        ps.Route("counter", demo_counter),
                        ps.Route("effects", demo_effects),
                        ps.Route("callbacks", demo_callbacks),
                    ],
                ),
            ],
        )
    ]
)

if __name__ == "__main__":
    print("🚀 Starting Pulse UI Feature Showcase Demo...")
    print("📋 Features included:")
    print("  ✅ Rendering (HTML elements & components)")
    print("  ✅ Reactive state (State classes)")
    print("  ✅ Computed variables (@computed decorator)")
    print("  ✅ Effects (ps.Effect for side effects)")
    print("  ✅ Nested routes (parent/child routing)")
    print("  ✅ Layouts (persistent layouts)")
    print("  ✅ Callbacks (event handlers)")
    print("  ✅ Wrapped React components (ReactComponent integration)")
    print("🌐 Visit the demo to see all features in action!")
