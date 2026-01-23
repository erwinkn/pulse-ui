# The Pulse tutorial

Welcome to the Pulse tutorial! In this guide, we'll work through examples that cover all the key concepts of the Pulse framework.

## Setup

- [Install `uv`](https://docs.astral.sh/uv/getting-started/installation/)
- [Install Bun](https://bun.com/docs/installation)
- Run `uv sync` to install Python dependencies
- Run `cd web && bun i` to install JavaScript dependencies
- Activate the Python virtual environment:
  - Linux/macOS: `source .venv/bin/activate`
  - Windows: `.venv\Scripts\Activate`

You're good to go! Now execute `pulse run tutorial.py`. Your terminal should display two pane, with the Python server on the left and the React app on the right. Use `q` to stop the app.

Go to the address given by the React app on the right, most likely http://localhost:5173, to see the final app.

The Pulse server and React app automatically reload the app if you make changes during development.

If you need to install the latest package versions after an update to this tutorial, run `uv sync` in the root folder and `bun i` in the `web` folder.

> [!TIP]
> This tutorial will use [Tailwind CSS](https://tailwindcss.com/) for styling. If you are not familiar with it, you can just ignore the CSS classes passed as `className`.

## 1. Defining the App

A Pulse application is defined by creating an `App` object, which defines the routes and other code generation options.

```python
"Full example: steps/01-basic-app.py"

from pathlib import Path
import pulse as ps


@ps.component
def welcome():
    return ps.div(
        className="min-h-screen flex items-center justify-center flex-col bg-gray-100"
    )[
        ps.h1("Welcome to Pulse!", className="text-4xl font-bold text-blue-600 mb-4"),
        ps.p(
            "You've created your first Pulse application!",
            className="text-lg text-gray-700",
        ),
    ]


app = ps.App(
    routes=[ps.Route("/", welcome)],
    codegen=ps.CodegenConfig(web_dir=Path(__file__).parent.parent / "web"),
)
```

Each route defines its path and its component, which is a function that takes no argument and returns Pulse elements (HTML tags in this case). It is wrapped by `@ps.component`, we will see what this decorator does later in the tutorial.

Like all steps of this tutorial, you will find it in the `steps/` folder in this repository. Run it using:

```
pulse run steps/01-basic-app.py
```

## 2. HTML and Pulse syntax

The main objective of Pulse is to display something on a web page. As such, the most basic building blocks are HTML elements. They are built into Pulse, so you can simply use `ps.div()` or `ps.a`.

The code seen earlier:

```python
ps.div(
    className="min-h-screen flex items-center justify-center flex-col bg-gray-100"
)[
    ps.h1("Welcome to Pulse!", className="text-4xl font-bold text-blue-600 mb-4"),
    ps.p(
        "You've created your first Pulse application!",
        className="text-lg text-gray-700",
    ),
]
```

Translates to this HTML:

```html
<div class="min-h-screen flex items-center justify-center flex-col bg-gray-100">
  <h1 class="text-4xl font-bold text-blue-600 mb-4">Welcome to Pulse!</h1>
  <p class="text-lg text-gray-700">
    You've created your first Pulse application!
  </p>
</div>
```

All Pulse elements, including HTML ones, can receive _props_ (in React terms), or _attributes_ (in HTML terms), and child elements, if they accept them. Props are passed as keyword arguments like `className` in the example above, children are passed as positional arguments.

> [!NOTE]
> Pulse adopts React conventions, which means that the HTML attribute `class` is renamed to `className`, to avoid conflicts with the `class` keyword in JavaScript or Python.

You may have noticed that our earlier example showcases two ways of passing children to a Pulse element:

1. As positional arguments when calling the function, like `ps.div("content")`
2. By using indexing syntax after defining the props, like `ps.div(className="...")["content]"`

Option 1. is convenient when the element doesn't have many children. Option 2. resembles HTML more and keeps the attributes close to the element's definition.

```python
ps.div(
    # Having the className stay close to the `ps.div` and passing in the children afterwards is more readable for this div.
    className="min-h-screen flex items-center justify-center flex-col bg-gray-100"
)[
    # Passing in the content as first argument is easier for this h1.
    ps.h1("Welcome to Pulse!", className="text-4xl font-bold text-blue-600 mb-4"),
    ps.p(
        "You've created your first Pulse application!",
        className="text-lg text-gray-700",
    ),
]
```

## 3. State

The most important concept in order to build an interactive application is how to define its state and how it can be modified by users.

The easiest way to demonstrate how it works in Pulse is with a counter:

```python
"Full example: steps/02-counter.py"
import pulse as ps

class CounterState(ps.State):
    count: int = 0

    def increment(self):
        self.count += 1


@ps.component
def counter():
    with ps.init():
        state = CounterState()
    print(f"Rendering counter, count is {state.count}")

    def decrement():
        state.count -= 1

    return ps.div(
        # Display current count
        ps.p(f"Current count: {state.count}", className="text-lg"),
        # Control buttons
        ps.div(className="flex items-center space-x-2")[
            ps.button(
                "Decrement (-1)",
                onClick=decrement,
                className="bg-red-500 text-white px-4 py-2 rounded mr-4 hover:bg-red-600",
            ),
            ps.button(
                "Increment (+1)",
                onClick=state.increment,
                className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600",
            ),
        ],
    )
```

You can run the full example using `pulse run steps/02-counter.py`.

Here we see:

- A state is defined as a class that inherits from `pulse.State`.
- State properties are defined as `count: int = 0` with a type annotation and eventual default value.
- Users modify state through events, like `onClick`.
- Event handlers can be a state method or any other function.
- When state is modified, the application reruns (we call this _"rerendering"_) and the user interface is updated.
- You should see the `print` statement in your terminal after every click on increment or decrement.

So the core loop of Pulse is:

1. Define the state.
2. Render the application based on the state.
3. User interacts with the application, modifies the state.
4. Application rerenders, returning the updated user interface.
5. Pulse performs a _diff_ between the current and updated UIs and only sends update operations to the user's browser.

## 4. Hooks

### 4.1. Introduction: `ps.init()`

You may have noticed that our earlier state example uses a context manager called `ps.init()`. This is a **Pulse hook**, providing a special mechanism outside the usual render -> update -> render cycle.

Its purpose is to preserve the same state instance across component rerenders. Any variables assigned inside the `with ps.init():` block are captured on the first render and restored on subsequent renders. To see why this matters, try making this change in `02-counter.py`:

```diff
@ps.component
def counter():
-    with ps.init():
-        state = CounterState()
+    state = CounterState()
```

You should notice that clicking the buttons doesn't do anything anymore. Here is what happens:

- 1st render: `CounterState` is created.
- Click increment: `count` in `CounterState` is incremented.
- 2nd render: a new `CounterState` is created. The count is at its default value of 0. The rest of the component uses this state and displays that count is 0.

With `ps.init()`, this becomes:

- 1st render: `CounterState` is created and captured by `ps.init()`.
- Click increment: `count` in `CounterState` is incremented.
- 2nd render: `ps.init()` restores the same state from the 1st render. The count has been incremented and is now 1. The rest of the component uses this state and thus displays that count is 1.

### 4.2. Rules of hooks

The two main Pulse hooks are:

- `ps.setup`: runs an arbitrary function on first render and returns its result on every render afterwards.
- `ps.init()`: preserves variables (including states) across rerenders.

They have one single rule: **you can only call them once per component.**

Components are functions decorated with `@ps.component`. We will discuss them in the [Components](#7-components) section.

This rule illustrates that the purpose of hooks is to **give you a way to do something exactly once, when a component first renders**.

In practice, you could do everything with `ps.setup`: create your states, set up your effects, initialize something, etc... `ps.init()` is a convenience hook for common requirements.

### 4.3. Usage

Let's understand how to use hooks by looking at an example.

The code is available in [`examples/03-hooks.py`](./examples/03-hooks.py)

```python
"examples/03-hooks.py"

from pathlib import Path
import pulse as ps


class CounterState(ps.State):
    count: int = 0

    def increment(self):
        self.count += 1

    def decrement(self):
        self.count -= 1


class DebugState(ps.State):
    enabled: bool = True

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def toggle(self):
        self.enabled = not self.enabled


def setup_demo(arg, *, kwarg):
    print(f"Received argument: {arg} and kwarg: {kwarg}")
    # do anything else here
    return DebugState(True)


def render_counter(label: str, state: CounterState):
    return ps.div(className="flex items-center gap-2")[
        ps.button(
            "-",
            onClick=state.decrement,
            className="px-2 py-1 bg-red-500 text-white rounded",
        ),
        ps.span(f"{label}: {state.count}"),
        ps.button(
            "+",
            onClick=state.increment,
            className="px-2 py-1 bg-green-500 text-white rounded",
        ),
    ]


def debug_toggle(label: str, state: DebugState):
    return ps.label(className="flex items-center gap-2")[
        ps.input(type="checkbox", checked=state.enabled, onChange=state.toggle),
        f"{label}: {state.enabled}",
    ]


@ps.component
def HooksDemo():
    # Use `ps.init()` to create state that persists across renders.
    # Any variables assigned inside the block are captured on the first render
    # and restored on subsequent renders.
    with ps.init():
        counter1 = CounterState()
        counter2 = CounterState()
        debug1 = DebugState(False)

    # `ps.setup` can also be used to create states and perform anything else you
    # need to set up on the first render. Note that the setup function has to be
    # synchronous, it is not recommended to perform async operations, like
    # network requests, there.
    debug2 = ps.setup(setup_demo, "arg", kwarg="kwarg")

    return ps.div(
        className="w-xl mx-auto h-screen flex flex-col justify-center items-start"
    )[
        ps.h3("Setup + States demo", className="text-2xl font-bold mb-4"),
        ps.div(className="space-y-4")[
            render_counter("Counter 1", counter1),
            render_counter("Counter 2", counter2),
            ps.div(className="flex flex-col gap-2")[
                debug_toggle("Debug 1", debug1), debug_toggle("Debug 2", debug2)
            ],
        ],
    ]


app = ps.App(
    routes=[ps.Route("/", HooksDemo)],
    codegen=ps.CodegenConfig(web_dir=Path(__file__).parent.parent / "web"),
)
```

In this example, we can see:

- Using `ps.init()` to create multiple states. All variables assigned inside the block are captured on first render and restored on subsequent renders.
  - Example: `counter1 = CounterState()`, `debug1 = DebugState(False)`
  - States are constructed only on the first render and reused on all subsequent renders.
- Using `ps.setup` with a function that takes in arguments. The function will be called once, its result stored and returned on every render. Arguments to the function can be passed to `ps.setup()` after the function.
  - Here, we use it to create a `DebugState`, essentially doing the same thing as `ps.init()`
  - This is useful if you have more complex initialization needs. See the [Cookbook](#15-cookbook) for usage examples.

### 4.4 Hook keys

The `ps.setup` hook accepts an optional `key` argument.

If the key changes, the setup function reruns. States and effects created in the previous execution of the setup function are cleaned up.

Keys are compared using the `!=` operator and thus have to support it. It is recommended to only use primitive values (strings, numbers, booleans) or tuples of primitive values as keys.

For keyed state management, use `ps.state(StateClass, key=...)` when you need different state instances based on runtime keys.

### 4.5 `stable` hook

In addition to the main hooks, Pulse has another hook: `stable`. The stable hook works a bit differently: it gives you a way to always access the latest value of a given variable.

```python
@ps.component
def Example():
    # `stable` is always used with a key
    # 1. key + value -> stores the value, returns a constant reference
    ref = ps.stable("key", value)
    # `ref` is always the same function on every render
    ref() # <- returns the latest `value` for `key`

    # 2. Just the key -> returns the value (or errors if there's none)
    ps.stable("key") # same thing as calling `ref()` above

    # If you pass a function or callable object, `ref` is a constant function
    # that takes the same arguments and directly returns the result
    def my_function(a: int, b: int):
        return a + b

    fn_ref = ps.stable("my_function", my_function)
    # You can use `fn_ref` directly like `my_function`
    fn_ref(2, 3) # returns 5
    # This pattern is just designed to be more convenient than `fn_ref()(2,3)`
```

Why do you need this? Here's a motivating example.

Let's say we have a component that allows the user to edit a string and, once the edits are finalized, save them. In practice, this component would implement some editing or validation logic and only allow finalizing the edits if they match certain criteria.

The basic implementation would look like this:

```python

class EditorState(ps.State):
    value: str

    def __init__(self, initial: str, on_finalized: Callable[[str], None]):
        self.value = initial
        self._on_finalized = on_finalized

    # editing and validation methods...

    def finalize(self):
        self._on_finalized(self.value)

@ps.component
def Editor(value: str, on_finalized: Callable[[str], None]):
    with ps.init():
        st = EditorState(value, on_finalized)
    # do stuff, render the component
```

But if you're building `Editor` to be a reusable component, what happens if `on_finalized` changes? For example, `Editor` could be used like this:

```python
@ps.component
def EditorUser():
    def on_finalized():
        # save the value, do something
        ...

    return Editor(value="", on_finalized=on_finalized)
```

In this case, a new `on_finalized` function is created every time `EditorUser` renders. So how do you make sure that `EditorState` calls the latest version of `on_finalized` that has been given to the component?

Using `stable`, it's pretty easy:

```python
class EditorState(ps.State):
    value: str

    def __init__(self, initial: str, on_finalized: Callable[[str], None]):
        self.value = initial
        self._on_finalized = on_finalized

    # editing and validation methods...

    def finalize(self):
        self._on_finalized(self.value)

@ps.component
def Editor(value: str, on_finalized: Callable[[str], None]):
    on_finalized = ps.stable("on_finalized", on_finalized)
    with ps.init():
        st = EditorState(value, on_finalized)
    # do stuff, render the component
```

As mentioned above, `stable` works especially well with functions, as it's the most common use case. This change didn't even require updating `EditorState`, as the return value of `ps.stable` is a function that takes the same arguments but whose reference doesn't change.

### 4.6. Custom hooks

TODO. Pulse has a core hook system that is used to define all the hooks described above. It can also be leveraged by the user to implement their own hooks. The hook system and implementations can be found in [`packages/pulse/python/src/pulse/hooks`](https://github.com/erwinkn/pulse-ui/tree/main/packages/pulse/python/src/pulse/hooks).

## 5. State (part II)

Now that we understand how hooks work, everything in the first state demo ([`examples/02-counter.py`](./examples/02-counter.py)) should be clear. States are one of Pulse's central features and they have more features we haven't discussed yet, so let's explore them.

We're going to use a todo list example to guide us through this section and the next: [`examples/04-todos.py`](./examples/04-todos.py)

Let's break it down piece by piece.

### 5.1. Deep reactivity

In our example, you can see that `TodosState` stores a list of Todo objects. In order to update it, we could rebuild it and update the property. For example:

```python
class TodosState(ps.State):
    def add_todo(self, text: str):
        next_id = max((n.id for n in self.todos), default=0) + 1
        self.todos.append(Todo(next_id, text, False))
```

This works the same way as the counter updates we saw earlier.

However, Pulse supports **deep reactivity**:

- _Reactivity_ means that when a state change happens, Pulse can propagate updates where they are needed.
- _Deep_ means that Pulse is able to detect changes that are deeper than the property defined on the state

This means `TodosState` can just use `self.todos.append()` when adding a todo. Updating `todo.done` directly also works.

```python
class TodosState(ps.State):
    def toggle(self, todo_id: int):
        for n in self.todos:
            if n.id == todo_id:
                n.done = not n.done
```

Pulse has special versions of lists, sets, dictionaries, and dataclasses, that are applied automatically to any value stored in a state.

You can verify it by adding this line to the TodosState constructor:

```diff
class TodosState(ps.State):
    todos: list[Todo]
    filt: Filter = "all"
    _owner: str  # non-reactive property

    def __init__(self, owner: str):
        self._owner = owner
        self.todos = [
            Todo(1, "Learn Pulse", False),
            Todo(2, "Ship demo", True),
        ]
+       print("Todos is a reactive list:", isinstance(self.todos, ps.ReactiveList))
```

The same thing applies for dictionaries and sets. The transformation is also applied recursively, so all nested lists, sets, and dictionaries get converted as well.

Pulse is also able to convert dataclasses and thus makes the `Todo` class reactive as well. In general, it is recommended to use dataclasses to define your data structures when working with Pulse.

Overall, this system exists to make Pulse state usable like regular Python, except all changes are detected and update the application.

### 5.2. Computeds

Another new feature introduced here is the usage of **computeds**. Computeds are **cached computations that update only when necessary**.

```python
class TodosState(ps.State):
    @ps.computed
    def filtered(self) -> list[Todo]:
        if self.filt == "open":
            return [n for n in self.todos if not n.done]
        if self.filt == "done":
            return [n for n in self.todos if n.done]
        return self.todos
```

How it works:

- The `filtered` function doesn't run when the state is created
- The first time `state.filtered` is accessed, it executes the function
- During this function execution, Pulse detects all accessed state properties. They become the dependencies of this computed.
- Whenever a dependency changes,
- Optimizations:
  - If you have a complex graph of state properties and computeds and perform multiple updates at once, Pulse only reruns each computed once.
  - After a state update, computeds are only recaculated once they are accessed. This allows Pulse to not rerun currently unused computeds.

If you need a computed that accesses multiple states, you can also define one manually using `ps.Computed`. Generally, you should do this in `ps.setup`. Note that a computed outside a state has to be used like a function, but the same caching behavior will apply.

```python
# This is an illustrative example, not part of 04-todos.py
def setup_counters():
    counter1 = CounterState()
    counter2 = CounterState()

    @ps.computed
    def counter_sum():
        return counter1.count + counter2.count

    return counter1, counter2, counter_sum

@ps.component
def CountersWithSum():
    counter1, counter2, counter_sum = ps.setup(setup_counters)

    return ps.div(
        # Display the counters and buttons here
        ps.p(f"The sum of the counters is: {counter_sum()}")
    )
```

### 5.3. Non-reactive properties

Sometimes, you need to store something that is not reactive on a state. For instance, this could be a name for debugging purposes or a reference to another state. You could declare this like your regular reactive properties, using `name: str` or `todo_state: TodoState`, but it's good to be explicit about your intent.

In that case, the convention is to have the property's name start with an underscore, like `_name`. Otherwise, Pulse will assume the property is meant to be reactive and will complain if there is no annotation, like `name: str`, on the class.

In our todos example, this is used to communicate between `AddTodoState` and `TodosState`:

```python
class AddTodoState(ps.State):
    new_title: str = ""

    def __init__(self, todo_state: TodosState):
        self._todo_state = todo_state # OK
        # Would raise an error, as Pulse would expect something like `todo_state: TodoState`
        # self.todo_state = todo_state

    def on_add(self):
        if not self.disabled:
            self._todo_state.add_todo(self.new_title)
```

### 5.4. Global states

It's pretty common to require some kind of global state, that persists as users navigate across different pages. For example, let's say we wanted to add a details page for each TODO, where the user would be able to add a description and comments. We would need the state of all todos to persist between our todos list page and the todo details page.

However, `TodosState` is tied to the page and we currently have no way of sharing it across pages.

Besides storing our todos in a database, which will have to wait until we discuss [async](#9-async), an easy way to solve this would be to have a global `TodosState` instance.

The natural way to write it would be:

```python
todo_state = TodosState()

def TodosPage():
    # use todo_state here
    ...
```

Unfortunately, this would create a single state object that would be used across all user sessions, which is not what we want. In order to isolate the global state to a given session, we should wrap `TodosState` with `ps.global_state`.

```python
# If the state's constructor require arguments, they can be passed to ps.global_state
global_todo_state = ps.global_state(TodosState)

def TodosPage():
    todo_state = global_todo_state()
    # use todo_state in the rest of the page
    ...
```

`ps.global_state(TodosState)` creates a function which returns the global state instance for the current user session, providing automatic isolation.

> [!NOTE]
> Pulse currently does not support sharing a state instance between user sessions. This is a planned feature to enable real-time collaboration, but it has not been developed and tested yet. Do not try to create a single state instance to use across sessions, you will encounter errors.

## 6. Events and callbacks

We've seen a few examples of event handlers being used to respond to user interactions. It's time we cover them properly.

Event handlers are part of Pulse's **callback** system. A **callback** is a Python function that can be called from the React app. When you pass a function as a prop to an HTML element or React component, Pulse automatically creates a corresponding JavaScript function that can be used in the client application to call into your Python function.

Callbacks can be any function, including state methods or functions recreated at every render, like a lambda. By convention, callbacks that respond to user interaction are called **event handlers** and are named starting with `on`, like `onClick` or `onChange`.

Going back to our counter example, it looks like this:

```python
class CounterState(ps.State):
    count: int = 0

    def increment(self):
        self.count += 1

    def reset(self):
        self.count = 0


@ps.component
def Counter():
    with ps.init():
        state = CounterState()

    def decrement():
        state.count -= 1

    return ps.div(
        # `decrement` is recreated at every render, not a problem
        ps.button("Decrement", onClick=decrement),
        ps.p(f"The count is {state.count}"),
        # `increment` is a state method, works fine as well
        ps.button("Increment", onClick=state.increment)
    )
```

The event handlers above take no arguments, but most event handlers on HTML elements or React components pass in some payload. We see this in the TODOs example:

```python
ps.input(
    type="text",
    placeholder="Add a todo...",
    value=add_todo.new_title,
    onChange=lambda evt: add_todo.on_change(evt["target"]["value"]),
    className="border p-2 mr-2",
)
```

The `evt` argument contains an event payload with details about the event and target HTML element. The type of the `evt` argument is a bit complicated: `ps.ChangeEvent[ps.HTMLInputElement]`. Most of the time, if you only need a specific value from the event payload, I would suggest using a lambda to call your proper state method or handler function with the value you care about, like in the example above. That way, you get proper type checking for `evt` without having to remember the exact type to use.

Note that Pulse is able to wrap React components (see [Components](#7-components) for a quick introduction). The arguments received by event handlers on React components can be anything, from standard HTML events to simple data (a string, a date) to multiple arguments. You will have to rely on the component's documentation to learn about it.

Also, we have seen that callbacks in Pulse can decide to receive their arguments or not. The rule here is: **a Pulse callback can take no argument or all its arguments.**

> [!WARNING]
> If a React component expects a synchronous callback that returns a value, Pulse will not be able to handle this scenario. By definition, a Pulse callback has to reach out over the network and is thus asynchronous. There is currently no support for returning values from Python to JavaScript. You may need to write a custom React component to achieve what you need.

## 7. Components

Another Pulse feature we have seen multiple times already is Pulse's component system. So far, we have used `@ps.component` on the render function for our pages. We have also mentioned that Pulse hooks can be called _once_ per component.

**A Pulse component is a reusable piece of user interface with persistent state and effects.**

A component can be created from any function returning Pulse elements by decorating it with `@ps.component`. Using hooks, each instance of a component can have its own internal state. Here's a very simple example using toggles ([`examples/05-toggle-component.py`](./examples/05-toggle-component.py)).

```python
"examples/05-toggle-component.py"
from pathlib import Path

import pulse as ps


class ToggleState(ps.State):
    on: bool = False

    def toggle(self):
        self.on = not self.on


@ps.component
def Toggle(label: str):
    with ps.init():
        state = ToggleState()
    return ps.div(
        ps.button(
            f"{label}: {'ON' if state.on else 'OFF'}",
            onClick=state.toggle,
            className="px-3 py-1 rounded border",
        ),
        ps.small(
            "Enabled content…" if state.on else "", className="block text-gray-500 mt-1"
        ),
    )


@ps.component
def ToggleDemo():
    return ps.div(
        ps.h3("Reusable Toggle"),
        ps.div(Toggle(label="Wi‑Fi"), className="mb-2"),
        ps.div(Toggle(label="Bluetooth")),
    )
```

Currently, Pulse rerenders the full application on every state change. Soon, Pulse will be optimized to only rerender the components affected by the state change.

---

By default, a component's identity is tied to its position in the Pulse element tree. In the example above, the two toggles are identified by their position.

However, in cases where components may change position, for example when iterating over a list or when the user can reorder items, we want to preserve a component's state even if it moves around. For this, we can use **component keys**.

**Keys are used to define a component's identity and preserve its state.**

Keys can be added to a component by adding a keyword argument named `key`. It generally should default to None, as a component should be usable with or without a key.

Here is an example of a keyed vs. unkeyed scenario: [`examples/06-component-keys.py`](./examples/06-component-keys.py)

Run this example, write "test" in the first two items, click their checkbox, and click "Prepend item".

You will notice that in the keyed version, the existing items properly shift down when a new item is added at the beginning of the list, their input and checkbox state moving with them.

In the unkeyed version, the labels shift down properly, but the checkbox and the input don't. They stay in the same position in the list.

> [!INFO]
> Keys only work at a given level in the tree. They are mostly used for list scenarios. They cannot be used to move a component to a completely different place in the UI while preserving its state.

Components can also accept children. It is recommended to define them as a variadic positional argument `*children`, as this will allow using the `Component(**props)[*children]` syntax.

```python
@ps.component
def Component(*children, key=None, title: str):
    return ps.div(
        ps.h3(title),
        *children
    )

def Page():
    # This only works if `Component` accepts a `*children` argument
    return Component(title="Section 1")[
        ps.div(...),
        ps.div(...)
    ]
```

## 8. Iterables

Talking about component keys, I mentioned that they are mostly used for lists. There are a few things to be aware of when working with lists/iterables.

The first is that you can pass an iterable of Pulse elements as a child. Pulse will automatically flatten the iterable alongside the other children (if any). If the iterable contains components, Pulse will check whether they have keys. If not, you will see a warning, as it is unintentional most of the time. Worst case, you can always use the index as the key.

```python
@ps.component
def Section(key=None, title: str, content: str):
    return ps.div(
        ps.h3(title),
        ps.p(content)
    )

def Page():
    sections = ['A', 'B', 'C']
    return ps.div(className="...")[
        # Not using a key will raise a warning
        [Section(key=title, title=title, content="...") for title in sections]
    ]
```

The second thing is that it is recommended to use the `ps.For` construct to work with iterables.

```python
ps.For(items, lambda x: ps.div(x))
```

Python iterables can often create subtle bugs due to [late binding semantics](https://docs.python-guide.org/writing/gotchas/#late-binding-closures).

For a demonstration, run [examples/08-iterable-late-binding.py]. Try clicking "Remove A" on the left (bad version). You should see that it removes C instead.

If you refresh and click "Remove A" on the right (good version), it will correctly remove A.

The issue is that in the bad version, all the `onClick` callbacks get a reference to `item` _after_ the iteration has ended, at which point it points to the last item.

`ps.For` mitigates this issue and will, down the line, introduce additional optimizations around rendering lists of items.

## 9. Effects

> [!WARNING]
> This section covers the essentials, but is still pretty light. Effects are powerful and essential, but also frequent sources of subtle bugs. Generally, you should try to avoid them in favor of other Pulse features, like computeds or async support.

Effects are the last piece of Pulse's reactive system. They are meant to do _something_ in response to a state change. This _something_ can be anything and happens outside rendering.

Effects are defined by decorating a function with `@ps.effect`. When an effect is created, Pulse runs it once and tracks its dependencies. When one of the dependencies changes, the effect reruns.

Effects can optionally return a _cleanup_ function that is called before each new effect run and when the effect is disposed. This is useful to clean up anything you may have set up during the last effect execution.

The simplest example is logging on state changes: [`examples/09-effects.py`](./examples/09-effects.py).

```python
class ToggleState(ps.State):
    enabled: bool = True

    def __init__(self, label: str):
        self._label = label

    def toggle(self):
        print(f"[toggle] {self._label}")
        self.enabled = not self.enabled

    @ps.effect
    def log_toggle_change(self):
        # Reading self.enabled registers it as a dependency
        print(f"[effect] {self._label}, enabled = {self.enabled}")

        # This will be executed before each subsequent effect execution and upon
        # effect disposal (when the state is not used anymore).
        def cleanup():
            print(f"[cleanup] {self._label}")

        return cleanup
```

In this example, the sequence of events is:

- Initial render, effect is created
- Effect runs for the 1st time, prints "[effect] ..." and registers its cleanup function.
- Click on toggle
- Application rerenders
- Effect triggers again: the cleanup from the 1st time runs, the effect runs a 2nd time, prints "[effect] ...", and returns a cleanup again.

The full demo also showcases that the effects on separate states behave independently.

Generally, it is recommended to define effects either on a state or in `ps.setup`. Otherwise, you risk creating a new effect on every render and they will all accumulate on top of one another.

Following this guideline, effects are automatically disposed when the state is disposed, or when the component that created them in `ps.setup` is removed from the UI.

Effects always run after rendering. They are something that happens _on the side_, once rendering is done.

> [!TIP]
> With Pulse computeds and async support, effects should be rarely needed, besides logging for debugging purposes.
> [!TIP]
> If you come from the React world and are accustomed to `useEffect`, you should still try to use effects as little as possible. Most use cases for effects are covered by Pulse's built-in support for asynchronous work.

## 10. Async

Nearly all real-world applications contain async workloads: network requests, database queries, etc.

Pulse comes with built-in support for common asynchronous patterns.

- Async event handlers
- Queries
- Async effects

### 10.1. Async callbacks

Pulse callbacks can be asynchronous out-of-the-box. Everything works as you expect, nothing special is needed.

The nice thing is that all synchronous state updates are automatically batched.

Example: [`examples/10-batch-updates.py`](./examples/10-batch-updates.py)

```python
class CounterState(ps.State):
    count: int = 0

    async def increment_twice(self):
        await asyncio.sleep(1)
        # Two separate state updates.
        # They are automatically batched, the app only rerenders once.
        self.count += 1
        self.count += 1
        await asyncio.sleep(1)
        # The app rerenders again after these two updates
        self.count += 1
        self.count += 1
```

### 10.2. Queries

Pulse has a built-in primitive for data queries. Currently it supports the following features:

- Built-in loading and error states
- Automatically detect dependencies (unkeyed mode)
- Use an explicit query key to trigger reruns (keyed mode)
- Set the initial data
- Manually refetch the query

Eventually this feature set will be expanded to look like a full query library, like TanStack Query or SWR in the JavaScript ecosystem.

You can see most of these features in our query example: [`examples/11-queries.py`](./examples/11-queries.py).

Here's a simplified version. The example demonstrates an unkeyed and a keyed query.

```python
class QueryDemoState(ps.State):
    user_id: int = 1

    # Default mode: unkeyed, auto-tracks dependencies
    @ps.query
    async def user(self) -> dict:
        # Simulate async work
        await asyncio.sleep(1)
        return {"id": self.user_id, "name": f"User {self.user_id}"}

@ps.component
def QueryDemo():
    with ps.init():
        state = QueryDemoState()

    def prev():
        state.user_id = max(1, state.user_id - 1)

    def next_():
        state.user_id = state.user_id + 1

    return ps.div(
        ps.h2("Query Demo", className="text-2xl font-bold mb-4"),
        ps.p(f"User ID: {state.user_id}"),
        ps.div(
            ps.h3("Query", className="text-xl font-semibold mt-4"),
            ps.p(
                "Loading..."
                if state.user.is_loading
                else f"Data: {state.user.data}",
                className="mb-2",
            ),
            ps.div(
                ps.button("Prev", onClick=prev, className="btn-secondary mr-2"),
                ps.button("Next", onClick=next_, className="btn-secondary mr-2"),
                ps.button(
                    "Refetch keyed",
                    onClick=state.user.refetch,
                    className="btn-primary",
                ),
                className="mb-4",
            ),
            className="mb-6 p-3 rounded bg-white shadow",
        ),
    )
```

Here are the properties and methods available on a query:

- `data`: the data returned by the query function, or `None` if not loaded yet
- `is_loading`: whether the query is currently loading
- `is_error`: whether the query failed with an error
- `has_loaded`: whether the query has finished loading at least once
- `refetch()`: manually trigger the query to run again
- `set_data(...)`: directly set the query data, bypassing the query function
- `set_initial_data(...)`: set initial data that will be returned before first load completes

The keyed mode is useful to more finely control when a query reruns. It will also be used to allow targeting a query by its key in future utilities.

Queries currently have to be bound to a state.

### 10.3. Async effects

Effects can also be async. They're useful for background tasks, periodic updates, or any operation that needs to await something.

See the example in [`example/12-async-effects.py`](./examples/12-async-effects.py).

```python
import pulse as ps
import asyncio

class AsyncEffectState(ps.State):
    running: bool = False
    step: int = 0

    @ps.effect(lazy=True)
    async def ticker(self):
        # Simulate writes across awaits
        await asyncio.sleep(0.5)
        with ps.Untrack():
            self.step += 1
            self.step += 1
        await asyncio.sleep(0.5)
        # Keep going by rescheduling itself through a signal
        self.step += 1

    def start(self):
        # Manually schedule an effect
        self.ticker.schedule()
        self.running = True

    def stop(self):
        self.ticker.cancel()
        self.running = False


@ps.component
def AsyncEffectDemo():
    with ps.init():
        state = AsyncEffectState()

    return ps.div(
        ps.div(
            ps.button(
                "Start async effect", onClick=state.start, className="btn-secondary"
            ),
            ps.button("Stop", onClick=state.stop, className="btn-secondary ml-2"),
            className="mb-2",
        ),
        ps.p(f"Running: {state.running}", className="text-sm"),
        ps.p(f"Step: {state.step}", className="text-sm"),
    )
```

## 11. Routing

- Pages take a component without arguments
- `ps.navigate`
- `ps.Outlet`
- `ps.Link`
- `ps.route_info`: returns information about the current route (URL). Often used to get query or path parameters for dynamic routes
- `ps.navigate`:

# 12. Sessions

- `ps.session`: returns a shared session context

## 12. Utilities

- `ps.call_api`
- `ps.Untrack` / `ps.Batch`
- ... all other hooks

## 13. Common gotchas

- Component rendering order
- Rerendering philosophy
- Creating states with arguments
- Stale arguments to states (ex: callback)
- For loop

## 14. Advanced

TODO:

- Computeds in ps.setup()
- Wrapping React
- Serialization
- User sessions
- Middleware
- `ps.call_api`

## 15. Cookbook

- Using `ps.setup` for stable callbcaks

```

```
