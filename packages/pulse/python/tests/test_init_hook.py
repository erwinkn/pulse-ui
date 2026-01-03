import inspect
import re
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
