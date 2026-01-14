"""
Tests for React module bindings (pulse.js.react) in transpiler.

Tests verify that React hooks and utilities transpile correctly to JavaScript code.
"""

from __future__ import annotations

from typing import Any

import pulse.js.console as console
import pytest
from pulse.js import obj
from pulse.transpiler import (
	Import,
	clear_function_cache,
	clear_import_registry,
	emit,
	get_registered_imports,
	javascript,
)


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()
	clear_import_registry()
	yield
	clear_function_cache()
	clear_import_registry()


# =============================================================================
# Test Utilities
# =============================================================================


def transpile_with_imports(fn: Any) -> str:
	"""Transpile a function and return the full code with imports.

	Returns a string containing:
	1. Import statements (sorted by source)
	2. Function definition(s)

	This utility makes it easy to verify the complete transpiled output
	including all dependencies.
	"""
	# Transpile the function
	transpiled = fn.transpile()
	fn_code = emit(transpiled)

	# Collect imports
	imports = get_registered_imports()

	# Group imports by source
	by_source: dict[str, list[Any]] = {}
	for imp in imports:
		if imp.src not in by_source:
			by_source[imp.src] = []
		by_source[imp.src].append(imp)

	# Generate import statements
	import_lines: list[str] = []
	for src in sorted(by_source.keys()):
		src_imports = by_source[src]
		named = sorted(
			[imp for imp in src_imports if imp.kind == "named"], key=lambda i: i.name
		)
		if named:
			members = [f"{imp.name} as {imp.js_name}" for imp in named]
			import_lines.append(f'import {{ {", ".join(members)} }} from "{src}";')

	# Combine imports and function
	if import_lines:
		return "\n".join(import_lines) + "\n\n" + fn_code
	return fn_code


# =============================================================================
# useState Hook
# =============================================================================


class TestUseState:
	def test_use_state_basic(self):
		useState = Import("useState", "react")

		@javascript
		def counter():
			count, set_count = useState(0)
			return count

		code = transpile_with_imports(counter)
		assert code == (
			'import { useState as useState_1 } from "react";\n\n'
			"function counter_2() {\n"
			"const $tmp0 = useState_1(0);\n"
			"let count = $tmp0[0];\n"
			"let set_count = $tmp0[1];\n"
			"return count;\n"
			"}"
		)

	def test_use_state_with_setter(self):
		useState = Import("useState", "react")

		@javascript
		def toggle():
			visible, set_visible = useState(True)
			set_visible(not visible)
			return visible

		code = transpile_with_imports(toggle)
		assert code == (
			'import { useState as useState_1 } from "react";\n\n'
			"function toggle_2() {\n"
			"const $tmp0 = useState_1(true);\n"
			"let visible = $tmp0[0];\n"
			"let set_visible = $tmp0[1];\n"
			"set_visible(!visible);\n"
			"return visible;\n"
			"}"
		)

	def test_use_state_with_object(self):
		"""Test useState with object using obj() for plain JS objects."""
		useState = Import("useState", "react")

		@javascript
		def form_state():
			state, set_state = useState(obj(name="", email=""))
			return state

		code = transpile_with_imports(form_state)
		assert code == (
			'import { useState as useState_1 } from "react";\n\n'
			"function form_state_2() {\n"
			'const $tmp0 = useState_1({"name": "", "email": ""});\n'
			"let state = $tmp0[0];\n"
			"let set_state = $tmp0[1];\n"
			"return state;\n"
			"}"
		)


# =============================================================================
# Object Spread Syntax
# =============================================================================


class TestObjSpread:
	"""Test obj() with **spread syntax."""

	def test_obj_single_spread(self):
		"""Test obj(**base) with Map-to-object conversion."""

		@javascript
		def merge(base: dict):
			return obj(**base)

		fn = merge.transpile()
		code = emit(fn)
		assert (
			code
			== "function merge_1(base) {\nreturn {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(base)};\n}"
		)

	def test_obj_spread_with_override(self):
		"""Test obj(**base, a=2) with Map-to-object conversion."""

		@javascript
		def merge(base: dict):
			return obj(**base, a=2)

		fn = merge.transpile()
		code = emit(fn)
		assert (
			code
			== 'function merge_1(base) {\nreturn {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(base), "a": 2};\n}'
		)

	def test_obj_override_before_spread(self):
		"""Test obj(a=1, **base) with Map-to-object conversion."""

		@javascript
		def merge(base: dict):
			return obj(a=1, **base)

		fn = merge.transpile()
		code = emit(fn)
		assert (
			code
			== 'function merge_1(base) {\nreturn {"a": 1, ...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(base)};\n}'
		)

	def test_obj_multiple_spreads(self):
		"""Test obj(**a, x=1, **b, y=2) with Map-to-object conversion."""

		@javascript
		def merge(a: dict, b: dict):
			return obj(**a, x=1, **b, y=2)

		fn = merge.transpile()
		code = emit(fn)
		assert (
			code
			== 'function merge_1(a, b) {\nreturn {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(a), "x": 1, ...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(b), "y": 2};\n}'
		)

	def test_obj_spread_expression(self):
		"""Test obj(**items[0], a=1) with Map-to-object conversion."""

		@javascript
		def merge(items: list):
			return obj(**items[0], a=1)

		fn = merge.transpile()
		code = emit(fn)
		assert (
			code
			== 'function merge_1(items) {\nreturn {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(items[0]), "a": 1};\n}'
		)

	def test_obj_empty(self):
		"""Test obj() with no args produces {}."""

		@javascript
		def make_obj():
			return obj()

		fn = make_obj.transpile()
		code = emit(fn)
		assert code == "function make_obj_1() {\nreturn {};\n}"

	def test_obj_simple_kwargs(self):
		"""Test obj(a=1, b=2) produces {"a": 1, "b": 2}."""

		@javascript
		def make_obj():
			return obj(a=1, b=2)

		fn = make_obj.transpile()
		code = emit(fn)
		assert code == 'function make_obj_1() {\nreturn {"a": 1, "b": 2};\n}'


# =============================================================================
# JSX Spread Props
# =============================================================================


class TestJsxSpread:
	"""Test JSX components with **spread props syntax."""

	def test_jsx_single_spread(self):
		"""Test Component(**props) produces <Component {...(Map check)} />."""
		from pulse.transpiler.nodes import Jsx

		Button = Jsx(Import("Button", "@mantine/core"))

		@javascript
		def render(props: dict):
			return Button(**props)

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_3(props) {\n"
			"return <Button_1 {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(props)} />;\n"
			"}"
		)

	def test_jsx_spread_with_override(self):
		"""Test Component(**base, disabled=True) includes Map check and override."""
		from pulse.transpiler.nodes import Jsx

		Button = Jsx(Import("Button", "@mantine/core"))

		@javascript
		def render(base: dict):
			return Button(**base, disabled=True)

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_3(base) {\n"
			"return <Button_1 {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(base)} disabled={true} />;\n"
			"}"
		)

	def test_jsx_override_before_spread(self):
		"""Test Component(size="lg", **props) includes size and Map check."""
		from pulse.transpiler.nodes import Jsx

		Button = Jsx(Import("Button", "@mantine/core"))

		@javascript
		def render(props: dict):
			return Button(size="lg", **props)

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_3(props) {\n"
			'return <Button_1 size="lg" {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(props)} />;\n'
			"}"
		)

	def test_jsx_multiple_spreads(self):
		"""Test Component(**a, x=1, **b) includes Map checks for both spreads."""
		from pulse.transpiler.nodes import Jsx

		Box = Jsx(Import("Box", "@mantine/core"))

		@javascript
		def render(a: dict, b: dict):
			return Box(**a, padding=10, **b)

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_3(a, b) {\n"
			"return <Box_1 {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(a)} padding={10} {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(b)} />;\n"
			"}"
		)

	def test_jsx_spread_with_children(self):
		"""Test Component(**props)["child"] includes Map check and children."""
		from pulse.transpiler.nodes import Jsx

		Button = Jsx(Import("Button", "@mantine/core"))

		@javascript
		def render(props: dict):
			return Button(**props)["Click me"]

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_3(props) {\n"
			'return <Button_1 {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(props)}>{"Click me"}</Button_1>;\n'
			"}"
		)

	def test_jsx_spread_dict_literal(self):
		"""Test Component(**{"disabled": True}) converts Map to object at runtime.

		Dict literals transpile to new Map([...]) which has no enumerable own props.
		The Map check ensures {disabled: True} spreads correctly into JSX props.
		"""
		from pulse.transpiler.nodes import Jsx

		Button = Jsx(Import("Button", "@mantine/core"))

		@javascript
		def render():
			return Button(**{"disabled": True, "size": "lg"})

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_3() {\n"
			'return <Button_1 {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(new Map([["disabled", true], ["size", "lg"]]))} />;\n'
			"}"
		)


class TestHtmlTagSpread:
	"""Test HTML tags with **spread props syntax."""

	def test_div_spread(self):
		"""Test div(**props) includes Map-to-object conversion."""
		from pulse.dom import tags

		@javascript
		def render(props: dict):
			return tags.div(**props)

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_1(props) {\n"
			"return <div {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(props)} />;\n"
			"}"
		)

	def test_div_spread_with_children(self):
		"""Test div(**props)["content"] includes Map check and children."""
		from pulse.dom import tags

		@javascript
		def render(props: dict):
			return tags.div(**props)["Hello"]

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_1(props) {\n"
			'return <div {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(props)}>{"Hello"}</div>;\n'
			"}"
		)

	def test_input_spread_with_override(self):
		"""Test input(**base, type="text") includes Map check and override."""
		from pulse.dom import tags

		@javascript
		def render(base: dict):
			return tags.input(**base, type="text")

		fn = render.transpile()
		code = emit(fn)
		assert code == (
			"function render_1(base) {\n"
			'return <input {...($s => $s instanceof Map ? Object.fromEntries($s) : $s)(base)} type="text" />;\n'
			"}"
		)


# =============================================================================
# useEffect Hook
# =============================================================================


class TestUseEffect:
	def test_use_effect_empty_deps(self):
		useEffect = Import("useEffect", "react")

		@javascript
		def on_mount():
			useEffect(lambda: console.log("mounted"), [])

		code = transpile_with_imports(on_mount)
		assert code == (
			'import { useEffect as useEffect_1 } from "react";\n\n'
			"function on_mount_2() {\n"
			'return useEffect_1(() => console.log("mounted"), []);\n'
			"}"
		)

	def test_use_effect_with_deps(self):
		useEffect = Import("useEffect", "react")

		@javascript
		def watch_count(count: int):
			useEffect(lambda: console.log(count), [count])

		code = transpile_with_imports(watch_count)
		assert code == (
			'import { useEffect as useEffect_1 } from "react";\n\n'
			"function watch_count_2(count) {\n"
			"return useEffect_1(() => console.log(count), [count]);\n"
			"}"
		)

	def test_use_effect_no_deps(self):
		useEffect = Import("useEffect", "react")

		@javascript
		def on_every_render():
			useEffect(lambda: console.log("render"))

		code = transpile_with_imports(on_every_render)
		assert code == (
			'import { useEffect as useEffect_1 } from "react";\n\n'
			"function on_every_render_2() {\n"
			'return useEffect_1(() => console.log("render"));\n'
			"}"
		)


# =============================================================================
# useRef Hook
# =============================================================================


class TestUseRef:
	def test_use_ref_null(self):
		useRef = Import("useRef", "react")

		@javascript
		def input_ref():
			ref = useRef(None)
			return ref

		code = transpile_with_imports(input_ref)
		assert code == (
			'import { useRef as useRef_1 } from "react";\n\n'
			"function input_ref_2() {\n"
			"let ref = useRef_1(null);\n"
			"return ref;\n"
			"}"
		)

	def test_use_ref_with_value(self):
		useRef = Import("useRef", "react")

		@javascript
		def counter_ref():
			ref = useRef(0)
			return ref.current

		code = transpile_with_imports(counter_ref)
		assert code == (
			'import { useRef as useRef_1 } from "react";\n\n'
			"function counter_ref_2() {\n"
			"let ref = useRef_1(0);\n"
			"return ref.current;\n"
			"}"
		)

	def test_use_ref_multiple(self):
		"""Test using multiple refs."""
		useRef = Import("useRef", "react")

		@javascript
		def multiple_refs():
			input_ref = useRef(None)
			count_ref = useRef(0)
			return [input_ref.current, count_ref.current]

		code = transpile_with_imports(multiple_refs)
		assert code == (
			'import { useRef as useRef_1 } from "react";\n\n'
			"function multiple_refs_2() {\n"
			"let input_ref = useRef_1(null);\n"
			"let count_ref = useRef_1(0);\n"
			"return [input_ref.current, count_ref.current];\n"
			"}"
		)


# =============================================================================
# useCallback Hook
# =============================================================================


class TestUseCallback:
	def test_use_callback_basic(self):
		useCallback = Import("useCallback", "react")

		@javascript
		def click_handler():
			handle_click = useCallback(lambda: console.log("clicked"), [])
			return handle_click

		code = transpile_with_imports(click_handler)
		assert code == (
			'import { useCallback as useCallback_1 } from "react";\n\n'
			"function click_handler_2() {\n"
			'let handle_click = useCallback_1(() => console.log("clicked"), []);\n'
			"return handle_click;\n"
			"}"
		)

	def test_use_callback_with_deps(self):
		useCallback = Import("useCallback", "react")

		@javascript
		def handler_with_deps(id: int):
			handle = useCallback(lambda: console.log(id), [id])
			return handle

		code = transpile_with_imports(handler_with_deps)
		assert code == (
			'import { useCallback as useCallback_1 } from "react";\n\n'
			"function handler_with_deps_2(id) {\n"
			"let handle = useCallback_1(() => console.log(id), [id]);\n"
			"return handle;\n"
			"}"
		)


# =============================================================================
# useMemo Hook
# =============================================================================


class TestUseMemo:
	def test_use_memo_basic(self):
		useMemo = Import("useMemo", "react")

		@javascript
		def expensive_value(a: int, b: int):
			result = useMemo(lambda: a * b, [a, b])
			return result

		code = transpile_with_imports(expensive_value)
		assert code == (
			'import { useMemo as useMemo_1 } from "react";\n\n'
			"function expensive_value_2(a, b) {\n"
			"let result = useMemo_1(() => a * b, [a, b]);\n"
			"return result;\n"
			"}"
		)

	def test_use_memo_complex(self):
		useMemo = Import("useMemo", "react")

		@javascript
		def filtered_list(items: list[int], threshold: int):
			filtered = useMemo(
				lambda: [x for x in items if x > threshold], [items, threshold]
			)
			return filtered

		code = transpile_with_imports(filtered_list)
		assert code == (
			'import { useMemo as useMemo_1 } from "react";\n\n'
			"function filtered_list_2(items, threshold) {\n"
			"let filtered = useMemo_1(() => items.filter(x => x > threshold).map(x => x), [items, threshold]);\n"
			"return filtered;\n"
			"}"
		)


# =============================================================================
# useReducer Hook
# =============================================================================


class TestUseReducer:
	def test_use_reducer_basic(self):
		useReducer = Import("useReducer", "react")

		@javascript
		def counter_reducer():
			def reducer(state: int, action: str) -> int:
				if action == "inc":
					return state + 1
				return state

			state, dispatch = useReducer(reducer, 0)
			return state

		code = transpile_with_imports(counter_reducer)
		assert code == (
			'import { useReducer as useReducer_1 } from "react";\n\n'
			"function counter_reducer_2() {\n"
			"const reducer = function(state, action) {\n"
			'if (action === "inc") {\n'
			"return state + 1;\n"
			"}\n"
			"return state;\n"
			"};\n"
			"const $tmp0 = useReducer_1(reducer, 0);\n"
			"let state = $tmp0[0];\n"
			"let dispatch = $tmp0[1];\n"
			"return state;\n"
			"}"
		)


# =============================================================================
# useContext Hook
# =============================================================================


class TestUseContext:
	def test_use_context_basic(self):
		useContext = Import("useContext", "react")
		# Use package-style import (not relative) to avoid path resolution
		ThemeContext = Import("ThemeContext", "@app/theme")

		@javascript
		def themed_component():
			theme = useContext(ThemeContext)
			return theme

		code = transpile_with_imports(themed_component)
		assert code == (
			'import { ThemeContext as ThemeContext_2 } from "@app/theme";\n'
			'import { useContext as useContext_1 } from "react";\n\n'
			"function themed_component_3() {\n"
			"let theme = useContext_1(ThemeContext_2);\n"
			"return theme;\n"
			"}"
		)


# =============================================================================
# useLayoutEffect Hook
# =============================================================================


class TestUseLayoutEffect:
	def test_use_layout_effect_basic(self):
		useLayoutEffect = Import("useLayoutEffect", "react")

		@javascript
		def measure_element():
			useLayoutEffect(lambda: console.log("measured"), [])

		code = transpile_with_imports(measure_element)
		assert code == (
			'import { useLayoutEffect as useLayoutEffect_1 } from "react";\n\n'
			"function measure_element_2() {\n"
			'return useLayoutEffect_1(() => console.log("measured"), []);\n'
			"}"
		)


# =============================================================================
# useId Hook
# =============================================================================


class TestUseId:
	def test_use_id_basic(self):
		useId = Import("useId", "react")

		@javascript
		def labeled_input():
			input_id = useId()
			return input_id

		code = transpile_with_imports(labeled_input)
		assert code == (
			'import { useId as useId_1 } from "react";\n\n'
			"function labeled_input_2() {\n"
			"let input_id = useId_1();\n"
			"return input_id;\n"
			"}"
		)


# =============================================================================
# useTransition Hook
# =============================================================================


class TestUseTransition:
	def test_use_transition_basic(self):
		useTransition = Import("useTransition", "react")

		@javascript
		def transition_example():
			is_pending, start_transition = useTransition()
			return is_pending

		code = transpile_with_imports(transition_example)
		assert code == (
			'import { useTransition as useTransition_1 } from "react";\n\n'
			"function transition_example_2() {\n"
			"const $tmp0 = useTransition_1();\n"
			"let is_pending = $tmp0[0];\n"
			"let start_transition = $tmp0[1];\n"
			"return is_pending;\n"
			"}"
		)


# =============================================================================
# useDeferredValue Hook
# =============================================================================


class TestUseDeferredValue:
	def test_use_deferred_value_basic(self):
		useDeferredValue = Import("useDeferredValue", "react")

		@javascript
		def deferred_search(query: str):
			deferred_query = useDeferredValue(query)
			return deferred_query

		code = transpile_with_imports(deferred_search)
		assert code == (
			'import { useDeferredValue as useDeferredValue_1 } from "react";\n\n'
			"function deferred_search_2(query) {\n"
			"let deferred_query = useDeferredValue_1(query);\n"
			"return deferred_query;\n"
			"}"
		)


# =============================================================================
# memo and forwardRef
# =============================================================================


class TestMemoForwardRef:
	def test_memo_basic(self):
		memo = Import("memo", "react")

		@javascript
		def memoized_component():
			Component = memo(lambda props: props)
			return Component

		code = transpile_with_imports(memoized_component)
		assert code == (
			'import { memo as memo_1 } from "react";\n\n'
			"function memoized_component_2() {\n"
			"let Component = memo_1(props => props);\n"
			"return Component;\n"
			"}"
		)

	def test_forward_ref_basic(self):
		forwardRef = Import("forwardRef", "react")

		@javascript
		def ref_forwarding():
			return forwardRef(lambda props, ref: None)

		code = transpile_with_imports(ref_forwarding)
		assert code == (
			'import { forwardRef as forwardRef_1 } from "react";\n\n'
			"function ref_forwarding_2() {\n"
			"return forwardRef_1((props, ref) => null);\n"
			"}"
		)


# =============================================================================
# createContext
# =============================================================================


class TestCreateContext:
	def test_create_context_basic(self):
		createContext = Import("createContext", "react")

		@javascript
		def create_theme_context():
			return createContext("light")

		code = transpile_with_imports(create_theme_context)
		assert code == (
			'import { createContext as createContext_1 } from "react";\n\n'
			"function create_theme_context_2() {\n"
			'return createContext_1("light");\n'
			"}"
		)

	def test_create_context_with_object(self):
		"""Test createContext with object using obj() for plain JS objects."""
		createContext = Import("createContext", "react")

		@javascript
		def create_user_context():
			ctx = createContext(obj(name="", role="guest"))
			return ctx

		code = transpile_with_imports(create_user_context)
		assert code == (
			'import { createContext as createContext_1 } from "react";\n\n'
			"function create_user_context_2() {\n"
			'let ctx = createContext_1({"name": "", "role": "guest"});\n'
			"return ctx;\n"
			"}"
		)


# =============================================================================
# Multiple Hooks Combined
# =============================================================================


class TestMultipleHooks:
	def test_counter_component(self):
		"""Test a realistic component using multiple hooks."""
		useState = Import("useState", "react")
		useMemo = Import("useMemo", "react")
		useEffect = Import("useEffect", "react")
		useCallback = Import("useCallback", "react")

		@javascript
		def counter_component():
			count, set_count = useState(0)
			doubled = useMemo(lambda: count * 2, [count])

			useEffect(lambda: console.log(f"Count: {count}"), [count])

			increment = useCallback(lambda: set_count(count + 1), [count])

			return obj(count=count, doubled=doubled, increment=increment)

		code = transpile_with_imports(counter_component)
		assert code == (
			"import { useCallback as useCallback_4, useEffect as useEffect_3, "
			'useMemo as useMemo_2, useState as useState_1 } from "react";\n\n'
			"function counter_component_5() {\n"
			"const $tmp0 = useState_1(0);\n"
			"let count = $tmp0[0];\n"
			"let set_count = $tmp0[1];\n"
			"let doubled = useMemo_2(() => count * 2, [count]);\n"
			"useEffect_3(() => console.log(`Count: ${count}`), [count]);\n"
			"let increment = useCallback_4(() => set_count(count + 1), [count]);\n"
			'return {"count": count, "doubled": doubled, "increment": increment};\n'
			"}"
		)

	def test_form_component(self):
		"""Test a form component using useState and useCallback."""
		useState = Import("useState", "react")
		useCallback = Import("useCallback", "react")

		@javascript
		def form_component():
			name, set_name = useState("")
			email, set_email = useState("")

			handle_submit = useCallback(
				lambda: console.log(f"Name: {name}, Email: {email}"), [name, email]
			)

			return obj(name=name, email=email, onSubmit=handle_submit)

		code = transpile_with_imports(form_component)
		assert code == (
			'import { useCallback as useCallback_2, useState as useState_1 } from "react";\n\n'
			"function form_component_3() {\n"
			'const $tmp0 = useState_1("");\n'
			"let name = $tmp0[0];\n"
			"let set_name = $tmp0[1];\n"
			'const $tmp1 = useState_1("");\n'
			"let email = $tmp1[0];\n"
			"let set_email = $tmp1[1];\n"
			"let handle_submit = useCallback_2(() => console.log(`Name: ${name}, Email: ${email}`), [name, email]);\n"
			'return {"name": name, "email": email, "onSubmit": handle_submit};\n'
			"}"
		)


# =============================================================================
# Namespace Import (via pulse.js.react module)
# =============================================================================


class TestPulseJsReactModule:
	def test_use_state_via_module(self):
		"""Test that pulse.js.react module exports work correctly."""
		import pulse.js.react as React

		# Access creates a fresh Import after registry was cleared
		useState = React.useState

		@javascript
		def use_namespace():
			count, set_count = useState(0)
			return count

		code = transpile_with_imports(use_namespace)
		assert code == (
			'import { useState as useState_1 } from "react";\n\n'
			"function use_namespace_2() {\n"
			"const $tmp0 = useState_1(0);\n"
			"let count = $tmp0[0];\n"
			"let set_count = $tmp0[1];\n"
			"return count;\n"
			"}"
		)

	def test_multiple_hooks_via_module(self):
		"""Test using multiple hooks from the pulse.js.react module."""
		import pulse.js.react as React

		useState = React.useState
		useEffect = React.useEffect

		@javascript
		def component_with_hooks():
			count, set_count = useState(0)
			useEffect(lambda: console.log(count), [count])
			return count

		code = transpile_with_imports(component_with_hooks)
		assert code == (
			'import { useEffect as useEffect_2, useState as useState_1 } from "react";\n\n'
			"function component_with_hooks_3() {\n"
			"const $tmp0 = useState_1(0);\n"
			"let count = $tmp0[0];\n"
			"let set_count = $tmp0[1];\n"
			"useEffect_2(() => console.log(count), [count]);\n"
			"return count;\n"
			"}"
		)


# =============================================================================
# from pulse.js import React
# =============================================================================


class TestPulseJsImportReact:
	"""Test `from pulse.js import React` generates proper imports."""

	def test_react_usestate_generates_import(self):
		"""Accessing React.useState should generate import { useState } from 'react'."""
		from pulse.js import React

		@javascript
		def use_react_namespace():
			count, set_count = React.useState(0)
			return count

		code = transpile_with_imports(use_react_namespace)
		assert code == (
			'import { useState as useState_2 } from "react";\n\n'
			"function use_react_namespace_1() {\n"
			"const $tmp0 = useState_2(0);\n"
			"let count = $tmp0[0];\n"
			"let set_count = $tmp0[1];\n"
			"return count;\n"
			"}"
		)


# =============================================================================
# lazy() Function
# =============================================================================


class TestLazy:
	"""Test React.lazy binding works both at definition time and in @javascript."""

	def test_lazy_definition_time(self):
		"""lazy(factory) at definition time creates a usable component."""
		from pulse.js.react import lazy

		# Create lazy component at definition time
		factory = Import("Chart", "./Chart", kind="default", lazy=True)
		LazyChart = lazy(factory)

		# Should be a Jsx wrapping a Constant
		from pulse.transpiler.nodes import Jsx

		assert isinstance(LazyChart, Jsx)

	def test_lazy_as_reference_in_javascript(self):
		"""lazy used as reference in @javascript produces correct import."""
		from pulse.js.react import lazy

		@javascript
		def pass_lazy_to_fn(some_fn):
			return some_fn(lazy)

		fn = pass_lazy_to_fn.transpile()
		code = emit(fn)
		# Note: lazy ID varies due to module-level caching across tests
		assert code.startswith("function pass_lazy_to_fn_1(some_fn) {\n")
		assert "return some_fn(lazy_" in code
		assert code.endswith(");\n}")

	def test_lazy_called_in_javascript(self):
		"""lazy(factory) called in @javascript creates Constant+Jsx."""
		from pulse.js.react import lazy
		from pulse.transpiler.function import CONSTANT_REGISTRY

		factory = Import("Chart", "./Chart", kind="default", lazy=True)

		@javascript
		def create_lazy():
			LazyComp = lazy(factory)
			return LazyComp

		fn = create_lazy.transpile()
		code = emit(fn)

		# The function body should reference a constant (created by lazy())
		assert "_const_" in code, f"Expected constant reference, got:\n{code}"

		# Verify a constant was created with the lazy call
		# Find constants that contain a lazy call
		lazy_constants = [
			c for c in CONSTANT_REGISTRY.values() if "lazy" in emit(c.expr).lower()
		]
		assert len(lazy_constants) > 0, "Expected constant with lazy call to be created"

		# The constant's expression should contain the lazy call with Chart
		const_expr = emit(lazy_constants[-1].expr)
		assert "lazy_" in const_expr, (
			f"Expected lazy_ in constant expr, got: {const_expr}"
		)
		assert "Chart_" in const_expr, (
			f"Expected Chart_ in constant expr, got: {const_expr}"
		)

	def test_lazy_via_react_namespace_reference(self):
		"""React.lazy used as reference in @javascript."""
		from pulse.js import React

		@javascript
		def pass_react_lazy(fn):
			return fn(React.lazy)

		fn = pass_react_lazy.transpile()
		code = emit(fn)
		assert code == ("function pass_react_lazy_1(fn) {\nreturn fn(lazy_2);\n}")

	def test_lazy_via_react_namespace_call(self):
		"""React.lazy(factory) called in @javascript."""
		from pulse.js import React

		factory = Import("Chart", "./Chart", kind="default", lazy=True)

		@javascript
		def create_lazy_via_react():
			LazyComp = React.lazy(factory)
			return LazyComp

		fn = create_lazy_via_react.transpile()
		code = emit(fn)
		assert code == (
			"function create_lazy_via_react_3() {\n"
			"let LazyComp = lazy_4(Chart_2);\n"
			"return LazyComp;\n"
			"}"
		)

	def test_lazy_component_in_rendered_tree(self):
		"""Lazy component used in a rendered JSX tree."""
		from pulse.dom.tags import div
		from pulse.js.react import Suspense, lazy

		# Create lazy component at definition time
		factory = Import("Chart", "./Chart", kind="default", lazy=True)
		LazyChart = lazy(factory)

		@javascript
		def App():
			return div()[Suspense(fallback=div()["Loading..."])[LazyChart()]]

		fn = App.transpile()
		code = emit(fn)

		# The lazy component should be referenced via its constant ID
		assert "_const_" in code, f"Expected constant reference, got:\n{code}"
		# Should have JSX structure with the lazy component
		assert "<_const_" in code, f"Expected JSX element with constant, got:\n{code}"
		# Suspense should be present
		assert "Suspense_" in code, f"Expected Suspense, got:\n{code}"

	def test_lazy_component_with_props(self):
		"""Lazy component with props in rendered tree."""
		from pulse.js.react import lazy

		factory = Import("Chart", "./Chart", kind="default", lazy=True)
		LazyChart = lazy(factory)

		@javascript
		def render_with_props():
			return LazyChart(data=[1, 2, 3], title="My Chart")

		fn = render_with_props.transpile()
		code = emit(fn)

		# Should have the lazy component as JSX
		assert "<_const_" in code, f"Expected JSX element, got:\n{code}"
		# Should have props
		assert "data=" in code, f"Expected data prop, got:\n{code}"
		assert "title=" in code, f"Expected title prop, got:\n{code}"
