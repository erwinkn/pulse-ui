from typing import override

import pulse as ps
import pytest
from pulse.hooks.core import HookContext
from pulse.hooks.setup import setup, setup_key
from pulse.hooks.stable import stable
from pulse.hooks.state import state
from pulse.reactive import Signal
from pulse.state import State


class DummyState(State):
	_dispose_calls: int

	def __init__(self):
		self._dispose_calls = 0
		super().__init__()

	@override
	def dispose(self):
		self._dispose_calls += 1
		super().dispose()

	@property
	def dispose_calls(self) -> int:
		return self._dispose_calls


def test_setup_returns_same_value_within_context():
	ctx = HookContext()
	calls = 0

	def factory():
		nonlocal calls
		calls += 1
		return {"calls": calls}

	with ctx:
		first = setup(factory)

	with ctx:
		second = setup(factory)

	assert calls == 1
	assert first is second


def test_setup_reinitializes_when_key_changes():
	ctx = HookContext()

	def factory(label: str):
		return {"label": label}

	with ctx:
		setup_key("alpha")
		first = setup(lambda: factory("alpha"))

	with ctx:
		setup_key("beta")
		second = setup(lambda: factory("beta"))

	assert first is not second
	assert first["label"] == "alpha"
	assert second["label"] == "beta"


def test_setup_enforces_single_call_per_render():
	ctx = HookContext()

	with ctx:
		setup(lambda: object())
		with pytest.raises(RuntimeError):
			setup(lambda: object())


def test_setup_key_must_precede_setup():
	ctx = HookContext()

	with ctx:
		setup(lambda: object())
		with pytest.raises(RuntimeError):
			setup_key("late")


def test_state_reuses_instances_with_same_key():
	ctx = HookContext()

	with ctx:
		first = state(DummyState, key="test")

	with ctx:
		second = state(DummyState, key="test")

	assert first is second


def test_state_auto_key_reuses_instances():
	ctx = HookContext()

	@ps.component
	def Comp():
		return state(DummyState)

	comp = Comp

	with ctx:
		first = comp.fn()

	with ctx:
		second = comp.fn()

	assert first is second


def test_state_auto_key_requires_unique_callsite():
	ctx = HookContext()

	@ps.component
	def BadComp():
		for _ in range(2):
			state(DummyState)
		return None

	with pytest.raises(
		RuntimeError,
		match="called once per component render at the same location",
	):
		with ctx:
			BadComp.fn()


def test_state_creates_different_instances_for_different_keys():
	ctx = HookContext()

	with ctx:
		first = state(DummyState, key="a")

	with ctx:
		second = state(DummyState, key="b")

	assert first is not second
	assert first.dispose_calls == 0  # States not disposed on key change


def test_state_disposes_direct_instances():
	ctx = HookContext()

	with ctx:
		direct = DummyState()
		retained = state(direct, key="test")
		assert retained is direct

	with ctx:
		transient = DummyState()
		# When reusing states, State instances passed as args are disposed if not being used
		result = state(transient, key="test")
		assert result is direct  # Should return the existing state
		# transient should be disposed since it's not being used
		assert transient.dispose_calls == 1


def test_state_allows_multiple_calls_with_different_keys():
	ctx = HookContext()

	with ctx:
		state_a = state(DummyState, key="a")
		state_b = state(DummyState, key="b")
		state_c = state(DummyState, key="c")

	assert state_a is not state_b
	assert state_b is not state_c
	assert state_a.dispose_calls == 0
	assert state_b.dispose_calls == 0
	assert state_c.dispose_calls == 0


def test_state_enforces_single_call_per_key():
	ctx = HookContext()

	with ctx:
		state(DummyState, key="a")
		with pytest.raises(
			RuntimeError,
			match="can only be called once per component render with key='a'",
		):
			state(DummyState, key="a")


def test_state_allows_same_key_across_renders():
	ctx = HookContext()

	with ctx:
		first = state(DummyState, key="a")

	with ctx:
		second = state(DummyState, key="a")

	assert first is second


def test_state_requires_non_empty_key():
	ctx = HookContext()

	with ctx:
		with pytest.raises(ValueError, match="requires a non-empty string key"):
			state(DummyState, key="")


def test_state_disposes_all_on_unmount():
	ctx = HookContext()

	with ctx:
		state_a = state(DummyState, key="a")
		state_b = state(DummyState, key="b")
		state_c = state(DummyState, key="c")

	# Unmount disposes all hooks
	ctx.unmount()

	assert state_a.dispose_calls == 1
	assert state_b.dispose_calls == 1
	assert state_c.dispose_calls == 1


def test_state_kept_when_not_called_in_render():
	ctx = HookContext()
	flag = Signal(True)
	states: list[DummyState] = []

	@ps.component
	def Comp():
		if flag():
			states.append(state(DummyState))
		return None

	with ctx:
		Comp.fn()  # type: ignore[attr-defined]

	flag.write(False)
	with ctx:
		Comp.fn()  # type: ignore[attr-defined]

	flag.write(True)
	with ctx:
		Comp.fn()  # type: ignore[attr-defined]

	assert len(states) == 2
	assert states[0] is states[1]
	assert states[0].dispose_calls == 0


def test_state_branch_disambiguation_with_key():
	ctx = HookContext()
	flag = Signal(True)

	left: DummyState | None = None
	right: DummyState | None = None

	with ctx:
		if flag():
			left = state(DummyState, key="left")
		else:
			right = state(DummyState, key="right")

	flag.write(False)
	with ctx:
		if flag():
			state(DummyState, key="left")
		else:
			right = state(DummyState, key="right")

	assert left is not None
	assert right is not None
	assert left is not right
	assert left.dispose_calls == 0
	assert right.dispose_calls == 0


def test_stable_returns_consistent_wrappers():
	ctx = HookContext()

	with ctx:
		wrapper = stable("value", 1)
		assert wrapper() == 1

	with ctx:
		wrapper_again = stable("value")
		assert wrapper_again() == 1

	with ctx:
		updated = stable("value", 2)
		assert updated() == 2

	with ctx:
		assert stable("value")() == 2

	with ctx:
		with pytest.raises(KeyError):
			stable("missing")
