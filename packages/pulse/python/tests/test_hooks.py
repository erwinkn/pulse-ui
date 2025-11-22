from typing import override

import pytest
from pulse.hooks.core import HookContext
from pulse.hooks.effects import effects
from pulse.hooks.setup import setup, setup_key
from pulse.hooks.stable import stable
from pulse.hooks.states import states
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


def test_states_reuses_instances_without_key():
	ctx = HookContext()

	with ctx:
		first = states(DummyState)

	with ctx:
		second = states(DummyState)

	assert first is second


def test_states_persists_when_key_changes():
	ctx = HookContext()

	with ctx:
		first = states(DummyState, key="a")

	with ctx:
		second = states(DummyState, key="b")

	assert first is not second
	assert first.dispose_calls == 0  # States not disposed on key change


def test_states_disposes_direct_instances():
	ctx = HookContext()

	with ctx:
		direct = DummyState()
		retained = states(direct)
		assert retained is direct

	with ctx:
		transient = DummyState()
		# When reusing states, State instances passed as args are disposed if not being used
		result = states(transient)
		assert result is direct  # Should return the existing state
		# transient should be disposed since it's not being used
		assert transient.dispose_calls == 1


def test_states_allows_multiple_calls_with_different_keys():
	ctx = HookContext()

	with ctx:
		state_a = states(DummyState, key="a")
		state_b = states(DummyState, key="b")
		state_c = states(DummyState, key="c")

	assert state_a is not state_b
	assert state_b is not state_c
	assert state_a.dispose_calls == 0
	assert state_b.dispose_calls == 0
	assert state_c.dispose_calls == 0


def test_states_enforces_single_call_per_key():
	ctx = HookContext()

	with ctx:
		states(DummyState, key="a")
		with pytest.raises(
			RuntimeError,
			match="can only be called once per component render with key='a'",
		):
			states(DummyState, key="a")


def test_states_enforces_single_call_without_key():
	ctx = HookContext()

	with ctx:
		states(DummyState)
		with pytest.raises(
			RuntimeError,
			match="can only be called once per component render without a key",
		):
			states(DummyState)


def test_states_allows_same_key_across_renders():
	ctx = HookContext()

	with ctx:
		first = states(DummyState, key="a")

	with ctx:
		second = states(DummyState, key="a")

	assert first is second


def test_states_enforces_same_argument_count_without_key():
	ctx = HookContext()

	with ctx:
		states(DummyState)

	with ctx:
		with pytest.raises(
			RuntimeError,
			match=r"called with 2 argument\(s\) but was previously called with 1 argument\(s\) without a key",
		):
			states(DummyState, DummyState)


def test_states_enforces_same_argument_count_with_key():
	ctx = HookContext()

	with ctx:
		states(DummyState, key="a")

	with ctx:
		with pytest.raises(
			RuntimeError,
			match=r"called with 2 argument\(s\) but was previously called with 1 argument\(s\) with key='a'",
		):
			states(DummyState, DummyState, key="a")


def test_states_allows_same_argument_count_across_renders():
	ctx = HookContext()

	with ctx:
		first_a, first_b = states(DummyState, DummyState, key="multi")

	with ctx:
		second_a, second_b = states(DummyState, DummyState, key="multi")

	assert first_a is second_a
	assert first_b is second_b


def test_states_disposes_all_on_unmount():
	ctx = HookContext()

	with ctx:
		state_a = states(DummyState, key="a")
		state_b = states(DummyState, key="b")
		state_c = states(DummyState)  # no key

	# Unmount disposes all hooks
	ctx.unmount()

	assert state_a.dispose_calls == 1
	assert state_b.dispose_calls == 1
	assert state_c.dispose_calls == 1


def test_effects_allows_single_call_and_key_changes():
	ctx = HookContext()

	with ctx:
		effects(lambda: None)
		with pytest.raises(RuntimeError):
			effects(lambda: None)

	with ctx:
		effects(lambda: None, key="alpha")

	with ctx:
		effects(lambda: None, key="beta")


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
