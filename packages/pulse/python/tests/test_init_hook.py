from typing import Any, Callable, cast

import pulse as ps
import pytest
from pulse import Component, HookContext


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
	@ps.component  # pyright: ignore[reportCallIssue, reportArgumentType, reportUntypedFunctionDecorator]
	def Example() -> tuple[int, list[int]]:
		with ps.init():
			obj: list[int] = []
		obj.append(len(obj))
		return id(obj), list(obj)

	example = cast(ps.Component[[]], Example)
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
	@ps.component  # pyright: ignore[reportCallIssue, reportArgumentType, reportUntypedFunctionDecorator]
	def Example() -> tuple[Callable[[int], int], type[Any]]:
		with ps.init():

			def helper(x: int) -> int:
				return x * 2

			class Box:
				def __init__(self, v: int) -> None:
					self.v: int = v

		return helper, Box

	example = cast(Component[[]], Example)
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

	@ps.component  # pyright: ignore[reportCallIssue, reportArgumentType, reportUntypedFunctionDecorator]
	def Example() -> tuple[Callable[[float], float], dict[str, int]]:
		with ps.init():

			def helper(x: float) -> float:
				return x + 1

			obj: dict[str, int] = {"x": 1}

		obj["x"] += 1
		return helper, obj

	example = cast(Component[[]], Example)
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
