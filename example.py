"""
Example demonstrating the refined server-side Python to TypeScript integration.

This file shows how to:
1. Define React components with the new direct UI tree generation
2. Create routes with inline component registries
3. Generate TypeScript files with simplified structure
4. Test stateful React components with server-rendered children
"""

from pulse.html import (
    define_react_component, 
    define_route, 
    div, h1, h2, h3, p, button, span, br, ul, li, a, strong, em, code
)
from pulse.codegen import write_generated_files

# ============================================================================
# Step 1: Define React Components
# ============================================================================

# Import components from the existing demo-components file
Counter = define_react_component(
    component_key="counter",
    import_path="../ui-tree/demo-components",
    export_name="Counter",
    is_default_export=False
)

UserCard = define_react_component(
    component_key="user-card", 
    import_path="../ui-tree/demo-components",
    export_name="UserCard",
    is_default_export=False
)

Button = define_react_component(
    component_key="button",
    import_path="../ui-tree/demo-components", 
    export_name="Button",
    is_default_export=False
)

Card = define_react_component(
    component_key="card",
    import_path="../ui-tree/demo-components",
    export_name="Card", 
    is_default_export=False
)

# New stateful component with server-rendered children
ColorBox = define_react_component(
    component_key="color-box",
    import_path="../ui-tree/demo-components",
    export_name="ColorBox",
    is_default_export=False
)

ProgressBar = define_react_component(
    component_key="progress-bar",
    import_path="../ui-tree/demo-components",
    export_name="ProgressBar",
    is_default_export=False
)


# ============================================================================
# Step 2: Define Routes
# ============================================================================

@define_route("/", components=[])
def home_route():
    """Home page with navigation to all demo routes."""
    
    def handle_click():
        print("🎉 Button clicked from server-side!")
        print("This Python function was executed on the server!")
    
    return div()[
        div(className="max-w-4xl mx-auto py-8 px-4")[
            h1(className="text-4xl font-bold text-gray-900 mb-2")["🚀 Pulse UI Demo"],
            p(className="text-xl text-gray-600 mb-8")["Server-rendered React components with Python integration"],
            
            div(className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg")[
                p(className="text-sm text-blue-800 mb-2")["🔗 Test Server-Client Interaction:"],
                button(
                    className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition-colors",
                    onClick=handle_click
                )["Click me! (Server callback)"]
            ],
            
            div(className="grid grid-cols-1 md:grid-cols-2 gap-6")[
                # Server Demo Card
                div(className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow")[
                    h3(className="text-xl font-semibold text-gray-900 mb-3")["🔧 Server-Generated Demo"],
                    p(className="text-gray-600 mb-4")["Complex route with nested React components, server-rendered children, and stateful interactions."],
                    ul(className="text-sm text-gray-500 mb-4 space-y-1")[
                        li()["✓ Nested React components"],
                        li()["✓ Server-side props"],
                        li()["✓ Stateful ColorBox component"],
                        li()["✓ Mixed content types"]
                    ],
                    a(href="/server-demo", className="inline-block bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition-colors")["View Demo →"]
                ],
                
                # API Example Card
                div(className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow")[
                    h3(className="text-xl font-semibold text-gray-900 mb-3")["📊 API Data Example"],
                    p(className="text-gray-600 mb-4")["Demonstrates rendering dynamic data from API calls with React components."],
                    ul(className="text-sm text-gray-500 mb-4 space-y-1")[
                        li()["✓ Dynamic data rendering"],
                        li()["✓ User card components"],
                        li()["✓ List iteration in Python"],
                        li()["✓ Avatar integration"]
                    ],
                    a(href="/api-example", className="inline-block bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 transition-colors")["View Demo →"]
                ],
                
                # Simple Route Card
                div(className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow")[
                    h3(className="text-xl font-semibold text-gray-900 mb-3")["🎯 Simple Static Route"],
                    p(className="text-gray-600 mb-4")["Pure HTML elements without React components, showing the flexibility of the system."],
                    ul(className="text-sm text-gray-500 mb-4 space-y-1")[
                        li()["✓ HTML-only content"],
                        li()["✓ No React dependencies"],
                        li()["✓ Fast server rendering"],
                        li()["✓ Static optimization"]
                    ],
                    a(href="/simple", className="inline-block bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700 transition-colors")["View Demo →"]
                ],
                
                # Stateful Demo Card
                div(className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow")[
                    h3(className="text-xl font-semibold text-gray-900 mb-3")["🎨 Stateful Components"],
                    p(className="text-gray-600 mb-4")["React components with internal state that render server-provided children."],
                    ul(className="text-sm text-gray-500 mb-4 space-y-1")[
                        li()["✓ Client-side state management"],
                        li()["✓ Server-rendered children"],
                        li()["✓ Interactive color switching"],
                        li()["✓ Hybrid rendering approach"]
                    ],
                    a(href="/stateful-demo", className="inline-block bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700 transition-colors")["View Demo →"]
                ]
            ],
            
            div(className="mt-12 p-6 bg-gray-50 rounded-lg")[
                h2(className="text-2xl font-semibold text-gray-900 mb-4")["🛠️ How It Works"],
                div(className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm")[
                    div()[
                        strong(className="text-gray-900")["1. Python Definition"],
                        p(className="text-gray-600 mt-1")["Define React components and routes using Python syntax with the ", code()["pulse.html"], " library."]
                    ],
                    div()[
                        strong(className="text-gray-900")["2. TypeScript Generation"],
                        p(className="text-gray-600 mt-1")["Generate TypeScript files with component registries and UI trees automatically."]
                    ],
                    div()[
                        strong(className="text-gray-900")["3. React Rendering"],
                        p(className="text-gray-600 mt-1")["Render with full React capabilities including state, effects, and server-rendered children."]
                    ]
                ]
            ]
        ]
    ]


@define_route("/server-demo", components=["counter", "user-card", "button", "card", "color-box"])
def server_demo_route():
    """A route demonstrating server-rendered React components."""
    return div()[
        div(className="max-w-4xl mx-auto py-8 px-4")[
            h1()["🔧 Server-Generated Demo Route"],
            p()["This entire page was generated from Python code and rendered with React components."],
            
            Card(title="Welcome", variant="primary")[
                p()["This card component is a React component imported from the demo-components file."],
                p()["It can contain arbitrary children from the UI tree."]
            ],
            
            h2()["Interactive Components"],
            p()["These components will be hydrated with React and become interactive:"],
            
            Counter(count=10, label="Server Counter")[
                "This counter was initialized with count=10 from the server."
            ],
            
            div()[
                UserCard(
                    name="Alice Johnson",
                    email="alice@example.com",
                    avatar="https://i.pravatar.cc/150?img=1"
                ),
                br(),
                UserCard(
                    name="Bob Smith", 
                    email="bob@example.com",
                    avatar="https://i.pravatar.cc/150?img=2"
                )
            ],
            
            h2()["Stateful Component with Server-Rendered Children"],
            p()["This ColorBox component has internal React state but renders server-provided children:"],
            
            ColorBox(title="Interactive Color Demo", initialColor="green")[
                p()["This content was generated on the server in Python."],
                ul()[
                    li()["✓ Server-side rendering"],
                    li()["✓ Client-side interactivity"],
                    li()["✓ Seamless integration"]
                ],
                strong()["Click the color buttons above to change the background!"]
            ],
            
            h2()["Nested Components"],
            Card(title="Nested Example")[
                p()["This card contains other React components:"],
                Button(variant="primary", size="large")[
                    "Click me!"
                ],
                br(),
                br(),
                Counter(count=5, label="Nested Counter")[
                    "This counter is nested inside a card."
                ]
            ]
        ]
    ]


@define_route("/api-example", components=["user-card"])
def api_example_route():
    """A route that might display data from an API."""
    # In a real application, this could fetch data from an API
    users = [
        {"name": "John Doe", "email": "john@example.com"},
        {"name": "Jane Smith", "email": "jane@example.com"},
        {"name": "Mike Johnson", "email": "mike@example.com"}
    ]
    
    return div()[
        div(className="max-w-4xl mx-auto py-8 px-4")[
            h1()["📊 API Data Example"],
            p()["This route demonstrates how you might render data from an API:"],
            
            div(className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4")[
                *[UserCard(
                    name=user["name"],
                    email=user["email"], 
                    avatar=f"https://i.pravatar.cc/150?u={user['email']}"
                ) for user in users]
            ]
        ]
    ]


@define_route("/simple", components=[])
def simple_route():
    """A simple route with no React components."""
    return div()[
        div(className="max-w-4xl mx-auto py-8 px-4")[
            h1()["🎯 Simple Static Route"],
            p()["This route uses only HTML elements, no React components."],
            p()["It demonstrates that you can mix static and dynamic content."],
            
            h2()["Pure HTML Elements"],
            ul()[
                li()["This is a regular HTML list item"],
                li()["No React components involved"],
                li()["Fast server-side rendering"],
                li()["Perfect for static content"]
            ],
            
            button()["This is just an HTML button"],
            
            div(className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded")[
                p()[
                    strong()["Note: "],
                    "This demonstrates the flexibility of the Pulse UI system. ",
                    "You can choose to use React components where you need interactivity, ",
                    "and plain HTML where you don't."
                ]
            ]
        ]
    ]


@define_route("/stateful-demo", components=["color-box", "counter", "progress-bar"])
def stateful_demo_route():
    """A route focused on demonstrating stateful React components with server children."""
    return div()[
        div(className="max-w-4xl mx-auto py-8 px-4")[
            h1()["🎨 Stateful Components Demo"],
            p()["This page demonstrates React components with internal state that render server-provided children."],
            
            div(className="space-y-6")[
                ColorBox(title="Color Switcher #1", initialColor="blue")[
                    h3()["Server-Rendered Content Inside Stateful Component"],
                    p()["This content was generated on the Python server, but it's rendered inside a React component that has its own state (the background color)."],
                    Counter(count=42, label="Nested Counter")[
                        "This counter is nested inside the stateful ColorBox!"
                    ]
                ],
                
                ColorBox(title="Color Switcher #2", initialColor="red")[
                    h3()["Another Example"],
                    p()["Each ColorBox component maintains its own independent state."],
                    ul()[
                        li()["✓ Independent state management"],
                        li()["✓ Server-rendered children"],
                        li()["✓ Seamless hydration"]
                    ]
                ],
                
                ColorBox(title="Progress Tracker", initialColor="purple")[
                    p()["This ColorBox contains a progress bar component:"],
                    ProgressBar(value=75, max=100, label="Task Progress", color="green"),
                    p()["The progress bar is also a React component, demonstrating nested component composition."]
                ]
            ],
            
            div(className="mt-8 p-6 bg-blue-50 border border-blue-200 rounded-lg")[
                h2()["💡 Key Insights"],
                ul(className="mt-4 space-y-2")[
                    li()["🔄 ", strong()["Hybrid Rendering"], ": Server generates initial structure, React handles interactivity"],
                    li()["🧩 ", strong()["Component Composition"], ": Server-rendered children work seamlessly with stateful components"],
                    li()["⚡ ", strong()["Performance"], ": Fast initial render from server, enhanced with client-side capabilities"],
                    li()["🎯 ", strong()["Flexibility"], ": Choose the right tool for each part of your UI"]
                ]
            ]
        ]
    ]


# ============================================================================
# Step 3: Generate TypeScript Files
# ============================================================================

def generate_files():
    """Generate all TypeScript files for the defined routes."""
    routes = [home_route, server_demo_route, api_example_route, simple_route, stateful_demo_route]
    write_generated_files(routes)
    print("✅ Generated TypeScript files successfully!")
    print("📁 Check pulse-web/app/routes/ for the generated files")
    print("📁 Check pulse-web/app/routes.ts for the updated route configuration")


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == "__main__":
    print("🎯 Pulse UI Server Integration Example")
    print("\nThis file defines example routes for Pulse UI.")
    print("The routes are automatically registered when imported.")
    print("\nTo use the new CLI:")
    print("  uv run pulse generate  - Generate TypeScript files")
    print("  uv run pulse run       - Start server with auto-generation")
    print("  uv run pulse run --port 8001  - Start server on custom port")
    print("\nTo get started:")
    print("1. Import this file to register routes: python -c 'import example'")
    print("2. Run 'uv run pulse run' to start the server")
    print("3. Start your React development server: bun dev")
    print("4. Visit http://localhost:5173/ to see the application")