from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Generic, Literal, ParamSpec, TypeVar, TypeVarTuple

from typing import Literal
import pulse as ps

P = ParamSpec("P")
R = TypeVar("R")


class Component(ABC, Generic[P, R]):
    def __init__(self, *args: P.args, **kwargs: P.kwargs) -> None:
        super().__init__()

    @abstractmethod
    def render(self, *args: P.args, **kwargs: P.kwargs) -> R: ...

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.render(*args, **kwargs)


@dataclass
class Todo:
    title: str
    description: str
    done: bool


class TodoComponent(Component):
    def __init__(self, todo: Todo):
        ...

    def render(self, todo: Todo):
        return todo.title 

  
comp = TodoComponent()
comp()




@dataclass
class Todo:
    title: str
    description: str
    done: bool


class TodoState(ps.State):
    todos: list[Todo]


@ps.component
def todo_lists():
    state1, state2, helpers = ps.state(TodoState, TodoState)

    # Any logic here will get rerun across rerenders

    # Render UI
    return ps.div(
        ps.h1("TODO list 1"),
        [render_todo(todo) for todo in state1.todos],
        ps.h1("TODO list 2"),
        [render_todo(todo) for todo in state2.todos],
    )  

@ps.component
def todo_lists(user_type, initial_todos):  
    # Either props available through the closure (if we can make this happen),
    # or we'll add a `props` argument to `setup`.
    def setup():
        if user_type == "admin":
            return TodoState(initial_todos), AdminState
        else:
            return TodoState(initial_todos), None
        
    todos, admin = ps.setup(setup)
    ps.effects(
        ps.watch(lambda todo: print("Todo"), todos.todos[0])
    )




