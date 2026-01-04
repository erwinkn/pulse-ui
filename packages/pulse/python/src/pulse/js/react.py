"""
JavaScript React module.

Usage:
    from pulse.js.react import useState, useEffect, useRef
    state, setState = useState(0)         # -> const [state, setState] = useState(0)
    useEffect(lambda: print("hi"), [])    # -> useEffect(() => console.log("hi"), [])
    ref = useRef(None)                    # -> const ref = useRef(null)

    # Also available as namespace:
    import pulse.js.react as React
    React.useState(0)                     # -> React.useState(0)
"""

from collections.abc import Callable as _Callable
from typing import Any as _Any
from typing import Protocol as _Protocol
from typing import TypeVar as _TypeVar

from pulse.component import component as _component
from pulse.transpiler import Import as _Import
from pulse.transpiler.function import Constant as _Constant
from pulse.transpiler.js_module import JsModule
from pulse.transpiler.nodes import Call as _Call
from pulse.transpiler.nodes import Jsx as _Jsx
from pulse.transpiler.nodes import Node as _PulseNode

# Type variables for hooks
T = _TypeVar("T")
T_co = _TypeVar("T_co", covariant=True)
T_contra = _TypeVar("T_contra", contravariant=True)
S = _TypeVar("S")
A = _TypeVar("A")


# =============================================================================
# React Types
# =============================================================================


class RefObject(_Protocol[T_co]):
	"""Type for useRef return value."""

	@property
	def current(self) -> T_co: ...


class MutableRefObject(_Protocol[T]):
	"""Type for useRef return value with mutable current."""

	@property
	def current(self) -> T: ...

	@current.setter
	def current(self, value: T) -> None: ...


class Dispatch(_Protocol[T_contra]):
	"""Type for setState/dispatch functions."""

	def __call__(self, action: T_contra, /) -> None: ...


class TransitionStartFunction(_Protocol):
	"""Type for startTransition callback."""

	def __call__(self, callback: _Callable[[], None], /) -> None: ...


class Context(_Protocol[T_co]):
	"""Type for React Context."""

	@property
	def Provider(self) -> _Any: ...

	@property
	def Consumer(self) -> _Any: ...


class ReactNode(_Protocol):
	"""Type for React children."""

	...


class ReactElement(_Protocol):
	"""Type for React element."""

	@property
	def type(self) -> _Any: ...

	@property
	def props(self) -> _Any: ...

	@property
	def key(self) -> str | None: ...


# =============================================================================
# State Hooks
# =============================================================================


def useState(
	initial_state: S | _Callable[[], S],
) -> tuple[S, Dispatch[S | _Callable[[S], S]]]:
	"""Returns a stateful value and a function to update it.

	Example:
		count, set_count = useState(0)
		set_count(count + 1)
		set_count(lambda prev: prev + 1)
	"""
	...


def useReducer(
	reducer: _Callable[[S, A], S],
	initial_arg: S,
	init: _Callable[[S], S] | None = None,
) -> tuple[S, Dispatch[A]]:
	"""An alternative to useState for complex state logic.

	Example:
		def reducer(state, action):
			if action['type'] == 'increment':
				return {'count': state['count'] + 1}
			return state

		state, dispatch = useReducer(reducer, {'count': 0})
		dispatch({'type': 'increment'})
	"""
	...


# =============================================================================
# Effect Hooks
# =============================================================================


def useEffect(
	effect: _Callable[[], None | _Callable[[], None]],
	deps: list[_Any] | None = None,
) -> None:
	"""Accepts a function that contains imperative, possibly effectful code.

	Example:
		useEffect(lambda: print("mounted"), [])
		useEffect(lambda: (print("update"), lambda: print("cleanup"))[-1], [dep])
	"""
	...


def useLayoutEffect(
	effect: _Callable[[], None | _Callable[[], None]],
	deps: list[_Any] | None = None,
) -> None:
	"""Like useEffect, but fires synchronously after all DOM mutations.

	Example:
		useLayoutEffect(lambda: measure_element(), [])
	"""
	...


def useInsertionEffect(
	effect: _Callable[[], None | _Callable[[], None]],
	deps: list[_Any] | None = None,
) -> None:
	"""Like useLayoutEffect, but fires before any DOM mutations.
	Use for CSS-in-JS libraries.
	"""
	...


# =============================================================================
# Ref Hooks
# =============================================================================


def useRef(initial_value: T) -> MutableRefObject[T]:
	"""Returns a mutable ref object.

	Example:
		input_ref = useRef(None)
		# In JSX: <input ref={input_ref} />
		input_ref.current.focus()
	"""
	...


def useImperativeHandle(
	ref: RefObject[T] | _Callable[[T | None], None] | None,
	create_handle: _Callable[[], T],
	deps: list[_Any] | None = None,
) -> None:
	"""Customizes the instance value exposed to parent components when using ref."""
	...


# =============================================================================
# Performance Hooks
# =============================================================================


def useMemo(factory: _Callable[[], T], deps: list[_Any]) -> T:
	"""Returns a memoized value.

	Example:
		expensive = useMemo(lambda: compute_expensive(a, b), [a, b])
	"""
	...


def useCallback(callback: T, deps: list[_Any]) -> T:
	"""Returns a memoized callback.

	Example:
		handle_click = useCallback(lambda e: print(e), [])
	"""
	...


def useDeferredValue(value: T) -> T:
	"""Defers updating a part of the UI. Returns a deferred version of the value."""
	...


def useTransition() -> tuple[bool, TransitionStartFunction]:
	"""Returns a stateful value for pending state and a function to start transition.

	Example:
		is_pending, start_transition = useTransition()
		start_transition(lambda: set_state(new_value))
	"""
	...


# =============================================================================
# Context Hooks
# =============================================================================


def useContext(context: Context[T]) -> T:
	"""Returns the current context value for the given context.

	Example:
		theme = useContext(ThemeContext)
	"""
	...


# =============================================================================
# Other Hooks
# =============================================================================


def useId() -> str:
	"""Generates a unique ID that is stable across server and client.

	Example:
		id = useId()
		# <label htmlFor={id}>Name</label>
		# <input id={id} />
	"""
	...


def useDebugValue(value: T, format_fn: _Callable[[T], _Any] | None = None) -> None:
	"""Displays a label in React DevTools for custom hooks."""
	...


def useSyncExternalStore(
	subscribe: _Callable[[_Callable[[], None]], _Callable[[], None]],
	get_snapshot: _Callable[[], T],
	get_server_snapshot: _Callable[[], T] | None = None,
) -> T:
	"""Subscribe to an external store.

	Example:
		width = useSyncExternalStore(
			subscribe_to_resize,
			lambda: window.innerWidth
		)
	"""
	...


# =============================================================================
# React Components and Elements
# =============================================================================


def createElement(
	type: _Any,
	props: dict[str, _Any] | None = None,
	*children: _Any,
) -> ReactElement:
	"""Creates a React element."""
	...


def cloneElement(
	element: ReactElement,
	props: dict[str, _Any] | None = None,
	*children: _Any,
) -> ReactElement:
	"""Clones and returns a new React element."""
	...


def isValidElement(obj: _Any) -> bool:
	"""Checks if the object is a React element."""
	...


def memo(component: T, are_equal: _Callable[[_Any, _Any], bool] | None = None) -> T:
	"""Memoizes a component to skip re-rendering when props are unchanged."""
	...


def forwardRef(
	render: _Callable[[_Any, _Any], ReactElement | None],
) -> _Callable[..., ReactElement | None]:
	"""Lets your component expose a DOM node to a parent component with a ref."""
	...


def lazy(factory: _Import) -> _Jsx:
	"""Create a lazy-loaded component from a factory import.

	Usage:
		LazyChart = lazy(Import("Chart", "./Chart", lazy=True))
		# Generates: const LazyChart_1 = lazy(Chart_2);

	Args:
		factory: An Import with lazy=True that generates a dynamic import factory

	Returns:
		A Jsx-wrapped lazy component that can be used as LazyChart(props)[children]
	"""
	react_lazy = _Import("lazy", "react")
	# Create: lazy(factory) call expression
	lazy_call = _Call(react_lazy, [factory])
	# Register as Constant so it appears in generated JS
	const = _Constant(lazy_call, lazy_call)
	# Wrap in Jsx so it's callable as a component
	return _Jsx(const)


def createContext(default_value: T) -> Context[T]:
	"""Creates a Context object."""
	...


# =============================================================================
# Components (stub declarations become Jsx-wrapped imports)
# =============================================================================


@_component
def Suspense(
	*, fallback: ReactNode | _PulseNode | None = None, name: str | None = None
) -> ReactElement:
	"""Lets you display a fallback while its children are loading."""
	...


# =============================================================================
# Registration
# =============================================================================

# React is a namespace module where each hook is a named import
JsModule.register(name="React", src="react", kind="namespace", values="named_import")
