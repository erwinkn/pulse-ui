import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import Any, Callable, cast, override

import pulse as ps
import pytest
from pulse import Component, HookContext
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteContext, RouteInfo, RouteTree
from pulse.transpiler import TranspileError


class TrackedState(ps.State):
	_dispose_calls: int

	def __init__(self) -> None:
		self._dispose_calls = 0

	@override
	def on_dispose(self) -> None:
		self._dispose_calls += 1

	@property
	def dispose_calls(self) -> int:
		return self._dispose_calls


def make_render_context(
	query_params: dict[str, str] | None = None,
) -> tuple[ps.App, RenderSession, RouteContext]:
	def render():
		return ps.div()

	route = Route("/", ps.component(render))
	routes = RouteTree([route])
	session = RenderSession("test", routes)
	app = ps.App(routes=[route])
	info: RouteInfo = {
		"pathname": "/",
		"hash": "",
		"query": "",
		"queryParams": query_params or {},
		"pathParams": {},
		"catchall": [],
	}
	return app, session, RouteContext(info, route, session)


def test_init_block_runs_once_and_restores_locals():
	@ps.component
	def Counter():
		with ps.init():
			state = {"count": 0}

		state["count"] += 1
		return state["count"]

	with HookContext():
		assert Counter.fn() == 1
		assert Counter.fn() == 2


def test_init_preserves_object_identity_and_runs_once():
	@ps.component
	def Example() -> tuple[int, list[int]]:
		with ps.init():
			obj: list[int] = []
		obj.append(len(obj))
		return id(obj), list(obj)

	example = Example
	with HookContext():
		result1 = cast(tuple[int, list[int]], cast(object, example.fn()))
		result2 = cast(tuple[int, list[int]], cast(object, example.fn()))
		first_id, first_list = result1
		second_id, second_list = result2

	# object identity preserved across renders (init ran once)
	assert first_id == second_id
	# data accumulates across renders
	assert first_list == [0]
	assert second_list == [0, 1]


def test_init_rewrites_component_renamed_before_decoration():
	def make_component(label: str):
		def Example() -> tuple[str, int, int]:
			with ps.init():
				state = {"count": 0}
			state["count"] += 1
			return label, id(state), state["count"]

		Example.__name__ = "RenamedExample"
		return ps.component(Example)

	first = make_component("first")
	second = make_component("second")
	with HookContext():
		first_label, first_id, first_count = cast(
			tuple[str, int, int], cast(object, first.fn())
		)
		_, second_id, second_count = cast(
			tuple[str, int, int], cast(object, first.fn())
		)
	with HookContext():
		second_label, _, _ = cast(tuple[str, int, int], cast(object, second.fn()))

	assert first_label == "first"
	assert second_label == "second"
	assert first_id == second_id
	assert first_count == 1
	assert second_count == 2


def test_init_reruns_when_key_changes():
	calls: list[str] = []

	@ps.component
	def Example(key: str) -> tuple[int, str]:
		with ps.init(key=key):
			calls.append(key)
			value = {"key": key}
		return id(value), value["key"]

	example = Example
	with HookContext():
		first_id, first_key = cast(tuple[int, str], cast(object, example.fn("a")))
		second_id, second_key = cast(tuple[int, str], cast(object, example.fn("a")))
		third_id, third_key = cast(tuple[int, str], cast(object, example.fn("b")))
		fourth_id, fourth_key = cast(tuple[int, str], cast(object, example.fn("b")))

	assert calls == ["a", "b"]
	assert first_id == second_id
	assert third_id == fourth_id
	assert first_id != third_id
	assert first_key == "a"
	assert second_key == "a"
	assert third_key == "b"
	assert fourth_key == "b"


def test_init_restores_functions_and_classes():
	@ps.component
	def Example() -> tuple[Callable[[int], int], type[Any]]:
		with ps.init():

			def helper(x: int) -> int:
				return x * 2

			class Box:
				def __init__(self, v: int) -> None:
					self.v: int = v

		return helper, Box

	example = Example
	with HookContext():
		result1 = cast(
			tuple[Callable[[int], int], type[Any]], cast(object, example.fn())
		)
		result2 = cast(
			tuple[Callable[[int], int], type[Any]], cast(object, example.fn())
		)
		h1, C1 = result1
		h2, C2 = result2

	# identity preserved (init once)
	assert h1 is h2
	assert C1 is C2
	# behavior intact
	assert h1(3) == 6
	assert C1(5).v == 5


def test_component_without_init_is_unchanged():
	calls: list[int] = []

	@ps.component
	def Hello() -> str:
		calls.append(1)
		return "hi"

	hello = Component[[]](Hello.fn, Hello.name)  # type: ignore[arg-type]
	with HookContext():
		assert cast(str, cast(object, hello.fn())) == "hi"
		assert cast(str, cast(object, hello.fn())) == "hi"
	# Without init, the function should run each time we call fn()
	assert len(calls) == 2


def test_init_rewrite_resolves_later_module_globals(tmp_path: Path):
	module_path = tmp_path / "late_global_component.py"
	module_path.write_text(
		"""
import pulse as ps


@ps.component
def Example():
	with ps.init():
		value = 1
	return helper(value)


def helper(value):
	return value + 1
""",
		encoding="utf-8",
	)
	spec = importlib.util.spec_from_file_location("late_global_component", module_path)
	assert spec is not None
	assert spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)

	with HookContext():
		assert module.Example.fn() == 2


def test_fallback_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
	# Force fallback path
	from pulse.hooks import init as init_mod

	monkeypatch.setattr(init_mod, "_CAN_USE_CPYTHON", False)

	@ps.component
	def Greeter() -> str:
		with ps.init():
			greeting = "hi"
		return greeting

	greeter = Component[[]](Greeter.fn, Greeter.name)  # type: ignore[arg-type]
	with HookContext():
		assert cast(str, cast(object, greeter.fn())) == "hi"
		# Ensure second call reuses saved value via fallback assignments
		assert cast(str, cast(object, greeter.fn())) == "hi"


def test_fallback_preserves_identity_and_runs_once(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from pulse.hooks import init as init_mod

	monkeypatch.setattr(init_mod, "_CAN_USE_CPYTHON", False)

	@ps.component
	def Example() -> tuple[Callable[[float], float], dict[str, int]]:
		with ps.init():

			def helper(x: float) -> float:
				return x + 1

			obj: dict[str, int] = {"x": 1}

		obj["x"] += 1
		return helper, obj

	example = Example
	with HookContext():
		result1 = cast(
			tuple[Callable[[float], float], dict[str, int]], cast(object, example.fn())
		)
		result2 = cast(
			tuple[Callable[[float], float], dict[str, int]], cast(object, example.fn())
		)
		h1, o1 = result1
		h2, o2 = result2

	assert h1 is h2
	assert o1 is o2
	assert o2["x"] == 3


def test_fallback_init_reruns_when_key_changes(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from pulse.hooks import init as init_mod

	monkeypatch.setattr(init_mod, "_CAN_USE_CPYTHON", False)
	calls: list[str] = []

	@ps.component
	def Example(key: str) -> tuple[int, str]:
		with ps.init(key=key):
			calls.append(key)
			value = {"key": key}
		return id(value), value["key"]

	example = Example
	with HookContext():
		first_id, first_key = cast(tuple[int, str], cast(object, example.fn("a")))
		second_id, second_key = cast(tuple[int, str], cast(object, example.fn("a")))
		third_id, third_key = cast(tuple[int, str], cast(object, example.fn("b")))
		fourth_id, fourth_key = cast(tuple[int, str], cast(object, example.fn("b")))

	assert calls == ["a", "b"]
	assert first_id == second_id
	assert third_id == fourth_id
	assert first_id != third_id
	assert first_key == "a"
	assert second_key == "a"
	assert third_key == "b"
	assert fourth_key == "b"


def test_init_allows_control_flow_outside_block() -> None:
	@ps.component
	def Example(flag: bool) -> int:
		with ps.init():
			value = 1
		if flag:
			value += 1
		return value

	example = Example
	with HookContext():
		assert cast(int, cast(object, example.fn(True))) == 2
		assert cast(int, cast(object, example.fn(False))) == 1


def test_init_control_flow_error_has_location() -> None:
	with pytest.raises(TranspileError) as excinfo:

		@ps.component
		def Example() -> int:  # pyright: ignore[reportUnusedFunction]
			with ps.init():
				if True:
					value = 1
			return value

	message = str(excinfo.value)
	assert "ps.init blocks cannot contain control flow" in message
	assert "if True:" in message
	assert "test_init_hook.py" in message
	assert "^" in message
	lines, start_line = inspect.getsourcelines(
		test_init_control_flow_error_has_location
	)
	if_index = next(i for i, line in enumerate(lines) if "if True:" in line)
	expected_line = start_line + if_index
	line_match = re.search(r"test_init_hook\.py:(\d+):", message)
	assert line_match is not None
	assert int(line_match.group(1)) == expected_line
	lines = message.splitlines()
	source_index = next(i for i, line in enumerate(lines) if "if True:" in line)
	caret_line = lines[source_index + 1]
	source_line = lines[source_index]
	assert caret_line.index("^") == source_line.index("if True:")


def test_init_only_once_per_component_render() -> None:
	with pytest.raises(TranspileError) as excinfo:

		@ps.component
		def Example() -> int:  # pyright: ignore[reportUnusedFunction]
			with ps.init():
				value = 1
			with ps.init():
				other = 2
			return value + other

	message = str(excinfo.value)
	assert "ps.init may only be used once per component render" in message
	lines, start_line = inspect.getsourcelines(test_init_only_once_per_component_render)
	with_indices = [i for i, line in enumerate(lines) if "with ps.init()" in line]
	expected_line = start_line + with_indices[1]
	line_match = re.search(r"test_init_hook\.py:(\d+):", message)
	assert line_match is not None
	assert int(line_match.group(1)) == expected_line


def test_init_disallows_as_binding() -> None:
	with pytest.raises(TranspileError) as excinfo:

		@ps.component
		def Example() -> int:  # pyright: ignore[reportUnusedFunction]
			with ps.init() as _ctx:
				value = 1
			return value

	message = str(excinfo.value)
	assert "ps.init does not support 'as' bindings" in message
	lines, start_line = inspect.getsourcelines(test_init_disallows_as_binding)
	with_index = next(
		i for i, line in enumerate(lines) if "with ps.init() as _ctx" in line
	)
	expected_line = start_line + with_index
	line_match = re.search(r"test_init_hook\.py:(\d+):", message)
	assert line_match is not None
	assert int(line_match.group(1)) == expected_line


def test_init_key_must_be_string() -> None:
	@ps.component
	def Example() -> int:
		with ps.init(key=cast(Any, 1)):
			value = 1
		return value

	example = Example
	with HookContext():
		with pytest.raises(TypeError, match="init\\(\\) key must be a string"):
			example.fn()


def test_init_key_must_not_be_empty() -> None:
	@ps.component
	def Example() -> int:
		with ps.init(key=""):
			value = 1
		return value

	example = Example
	with HookContext():
		with pytest.raises(
			ValueError, match="init\\(\\) requires a non-empty string key"
		):
			example.fn()


def test_init_exception_does_not_save_partial_locals() -> None:
	calls = {"count": 0}

	def maybe_raise(counter: dict[str, int], value: dict[str, int]) -> None:
		if counter["count"] == 1:
			value["x"] = 5
			raise RuntimeError("boom")

	@ps.component
	def Example() -> int:
		with ps.init():
			calls["count"] += 1
			value = {"x": 0}
			maybe_raise(calls, value)
		value["x"] += 1
		return value["x"]

	example = Example
	with HookContext():
		with pytest.raises(RuntimeError, match="boom"):
			example.fn()
		assert calls["count"] == 1
		assert cast(int, cast(object, example.fn())) == 1
		assert calls["count"] == 2


def test_init_disposes_created_state_and_effect_on_unmount() -> None:
	from pulse.reactive import Effect

	states: list[TrackedState] = []
	effects: list[Effect] = []
	events: list[str] = []

	def capture(state: TrackedState, effect: Effect) -> None:
		states.append(state)
		effects.append(effect)

	@ps.component
	def Example():
		with ps.init():
			state = TrackedState()

			@ps.effect(immediate=True)
			def mount_effect():
				events.append("run")
				return lambda: events.append("cleanup")

			capture(state, mount_effect)
		return state

	ctx = HookContext()
	with ctx:
		assert Example.fn() is states[0]

	assert events == ["run"]
	assert states[0].dispose_calls == 0
	assert not effects[0].__disposed__

	ctx.unmount()

	assert states[0].dispose_calls == 1
	assert effects[0].__disposed__
	assert events == ["run", "cleanup"]


def test_init_key_change_disposes_query_param_state_before_replacement() -> None:
	from pulse.reactive import Effect

	class Filters(TrackedState):
		q: ps.QueryParam[str] = ""

	effects: list[Effect] = []
	events: list[str] = []

	def capture(effect: Effect) -> None:
		effects.append(effect)

	@ps.component
	def Example(key: str):
		with ps.init(key=key):
			state = Filters()

			@ps.effect(immediate=True)
			def mount_effect():
				events.append(f"run:{key}")
				return lambda: events.append(f"cleanup:{key}")

			capture(mount_effect)
		return state

	app, session, route_ctx = make_render_context({"q": "hello"})
	ctx = HookContext()

	with ps.PulseContext(app=app, render=session, route=route_ctx):
		with ctx:
			first = cast(Filters, cast(object, Example.fn("first")))
		with ctx:
			second = cast(Filters, cast(object, Example.fn("second")))

	assert first is not second
	assert first.dispose_calls == 1
	assert effects[0].__disposed__
	assert second.dispose_calls == 0
	assert not effects[1].__disposed__
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		assert second.q == "hello"
	assert events == ["run:first", "cleanup:first", "run:second"]

	ctx.unmount()
	session.close()
	assert first.dispose_calls == 1
	assert second.dispose_calls == 1
	assert events == [
		"run:first",
		"cleanup:first",
		"run:second",
		"cleanup:second",
	]


def test_init_rolls_back_created_state_and_effect_when_block_raises() -> None:
	from pulse.reactive import Effect

	states: list[TrackedState] = []
	effects: list[Effect] = []
	events: list[str] = []
	should_raise = True

	def capture_and_maybe_raise(state: TrackedState, effect: Effect) -> None:
		nonlocal should_raise
		states.append(state)
		effects.append(effect)
		if should_raise:
			should_raise = False
			raise RuntimeError("boom")

	@ps.component
	def Example():
		with ps.init():
			state = TrackedState()

			@ps.effect(immediate=True)
			def mount_effect():
				events.append("run")
				return lambda: events.append("cleanup")

			capture_and_maybe_raise(state, mount_effect)
		return state

	ctx = HookContext()
	with pytest.raises(RuntimeError, match="boom"):
		with ctx:
			Example.fn()

	assert states[0].dispose_calls == 1
	assert effects[0].__disposed__
	assert events == ["run", "cleanup"]

	with ctx:
		recovered = cast(TrackedState, cast(object, Example.fn()))

	assert recovered is states[1]
	assert recovered.dispose_calls == 0
	ctx.unmount()
	assert states[0].dispose_calls == 1
	assert recovered.dispose_calls == 1
	assert events == ["run", "cleanup", "run", "cleanup"]


def test_init_does_not_take_ownership_from_state_or_global_state() -> None:
	global_accessor = ps.global_state(TrackedState, key="test-init-ownership")

	@ps.component
	def Example(key: str):
		with ps.init(key=key):
			factory_state = ps.state(TrackedState, key="factory")
			direct_state = ps.state(TrackedState(), key="direct")
			global_value = global_accessor()
		return factory_state, direct_state, global_value

	app, session, route_ctx = make_render_context()
	ctx = HookContext()

	with ps.PulseContext(app=app, render=session, route=route_ctx):
		with ctx:
			first_factory, first_direct, first_global = cast(
				tuple[TrackedState, TrackedState, TrackedState],
				cast(object, Example.fn("first")),
			)
		with ctx:
			second_factory, second_direct, second_global = cast(
				tuple[TrackedState, TrackedState, TrackedState],
				cast(object, Example.fn("second")),
			)

	assert second_factory is first_factory
	assert second_direct is first_direct
	assert second_global is first_global
	assert first_factory.dispose_calls == 0
	assert first_direct.dispose_calls == 0
	assert first_global.dispose_calls == 0

	ctx.unmount()
	assert first_factory.dispose_calls == 1
	assert first_direct.dispose_calls == 1
	assert first_global.dispose_calls == 0

	session.close()
	assert first_global.dispose_calls == 1


def test_init_parent_child_states_are_each_disposed_once() -> None:
	class Parent(TrackedState):
		def __init__(self, child: TrackedState) -> None:
			super().__init__()
			self._child: TrackedState = child

	created: list[tuple[TrackedState, Parent]] = []

	def capture(child: TrackedState, parent: Parent) -> None:
		created.append((child, parent))

	@ps.component
	def Example():
		with ps.init():
			child = TrackedState()
			parent = Parent(child)
			capture(child, parent)
		return parent

	ctx = HookContext()
	with ctx:
		Example.fn()
	ctx.unmount()

	child, parent = created[0]
	assert child.dispose_calls == 1
	assert parent.dispose_calls == 1


def test_init_disposes_all_entries_when_one_dispose_fails() -> None:
	class FailingState(TrackedState):
		@override
		def on_dispose(self) -> None:
			super().on_dispose()
			raise RuntimeError("boom")

	failing: list[FailingState] = []
	tracked: list[TrackedState] = []

	@ps.component
	def First():
		with ps.init():
			bad = FailingState()
			failing.append(bad)
		return bad

	@ps.component
	def Second():
		with ps.init():
			good = TrackedState()
			tracked.append(good)
		return good

	ctx = HookContext()
	with ctx:
		First.fn()
		Second.fn()

	ctx.unmount()

	assert failing[0].dispose_calls == 1
	assert tracked[0].dispose_calls == 1
