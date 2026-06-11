import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import Any, Callable, cast

import pulse as ps
import pytest
from pulse import Component, HookContext
from pulse.transpiler import TranspileError


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


def test_init_disposes_states_and_effects_on_unmount() -> None:
	from pulse.reactive import flush_effects
	from pulse.renderer import RenderTree

	events: list[str] = []

	class S(ps.State):
		count: int = 0

		@ps.effect
		def watch(self):
			events.append(f"state:{self.count}")

	captured: dict[str, Any] = {}

	@ps.component
	def Comp():
		with ps.init():
			st = S()

			@ps.effect
			def mount_only():  # pyright: ignore[reportUnusedFunction]
				events.append("mount")
				return lambda: events.append("unmount")

		captured["st"] = st
		return ps.div(f"{st.count}")

	tree = RenderTree(Comp())
	tree.render()
	flush_effects()
	assert events == ["state:0", "mount"]

	# Re-render: the init block is skipped, its effects must survive.
	st = captured["st"]
	st.count = 1
	flush_effects()
	assert "unmount" not in events

	tree.unmount()
	assert st.__disposed__
	assert events.count("unmount") == 1

	# The state's effect is dead: further writes don't run it.
	before = list(events)
	st.count = 2
	flush_effects()
	assert events == before


def test_init_effects_are_not_inline_cached() -> None:
	"""Effects created in a ps.init block bypass the inline-effects hook, so
	the inline GC for unseen callsites can't dispose them on re-renders."""
	from pulse.hooks.effects import effect_state
	from pulse.renderer import RenderTree

	inline_counts: list[int] = []

	@ps.component
	def Comp():
		with ps.init():

			@ps.effect
			def mount_only():  # pyright: ignore[reportUnusedFunction]
				pass

		inline_counts.append(len(effect_state().effects))
		return ps.div()

	tree = RenderTree(Comp())
	tree.render()
	assert inline_counts == [0]
	tree.unmount()


def test_init_key_change_disposes_previous_states() -> None:
	from pulse.reactive import Signal, flush_effects
	from pulse.renderer import RenderTree

	class S(ps.State):
		label: str = ""

		def __init__(self, label: str):
			self.label = label

	key_sig = Signal("a")
	instances: list[Any] = []

	@ps.component
	def Comp():
		current = key_sig()
		with ps.init(key=current):
			st = S(current)
		if st not in instances:
			instances.append(st)
		return ps.div(st.label)

	tree = RenderTree(Comp())
	tree.render()
	flush_effects()
	assert len(instances) == 1

	key_sig.write("b")
	flush_effects()
	assert len(instances) == 2
	assert instances[0].__disposed__
	assert not instances[1].__disposed__

	tree.unmount()
	assert instances[1].__disposed__


def test_init_does_not_own_shared_states() -> None:
	"""States obtained through ps.state or ps.global_state inside a ps.init
	block belong to their own stores, not to the init entry, so unmounting
	one component must not dispose them."""
	from pulse.reactive import flush_effects
	from pulse.renderer import RenderTree

	class Shared(ps.State):
		value: int = 0

	shared = ps.global_state(Shared, key="test-init-shared")
	seen: list[Any] = []

	@ps.component
	def Comp():
		with ps.init():
			inst = shared(id="x")
		seen.append(inst)
		return ps.div(f"{inst.value}")

	tree = RenderTree(Comp())
	tree.render()
	flush_effects()
	tree.unmount()

	assert not seen[0].__disposed__
	# Cleanup the process-wide registry for test isolation.
	from pulse.hooks.runtime import GLOBAL_STATES

	GLOBAL_STATES.pop("test-init-shared|x", None)
	seen[0].dispose()


def test_init_parent_child_state_composition_disposes_cleanly() -> None:
	"""A parent state disposing a child it holds as an attribute must not be
	flagged: both are captured by the init scope, and whichever the entry
	disposes first cascades into the other."""
	from pulse.renderer import RenderTree

	class Child(ps.State):
		value: int = 0

	class Parent(ps.State):
		def __init__(self, child: Child):
			self._child: Child = child

	created: list[Any] = []

	@ps.component
	def Comp():
		with ps.init():
			child = Child()
			parent = Parent(child)
		created.append((child, parent))
		return ps.div()

	tree = RenderTree(Comp())
	tree.render()
	tree.unmount()
	child, parent = created[0]
	assert child.__disposed__ and parent.__disposed__


def test_init_owned_state_disposed_elsewhere_is_surfaced(
	caplog: pytest.LogCaptureFixture,
) -> None:
	import logging

	from pulse.renderer import RenderTree

	class S(ps.State):
		value: int = 0

	created: list[Any] = []

	@ps.component
	def Comp():
		with ps.init():
			st = S()
		created.append(st)
		return ps.div()

	tree = RenderTree(Comp())
	tree.render()

	# Forbidden: the init block owns this state.
	created[0].dispose()

	with caplog.at_level(logging.ERROR, logger="pulse.hooks.core"):
		tree.unmount()

	assert any(
		"Error disposing hook 'init_storage'" in record.getMessage()
		for record in caplog.records
	)
