from typing import override

import pytest
from pulse.hooks.core import HookContext
from pulse.hooks.setup import setup, setup_key
from pulse.hooks.stable import stable
from pulse.hooks.state import state
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
		first = state("test", DummyState)

	with ctx:
		second = state("test", DummyState)

	assert first is second


def test_state_creates_different_instances_for_different_keys():
	ctx = HookContext()

	with ctx:
		first = state("a", DummyState)

	with ctx:
		second = state("b", DummyState)

	assert first is not second
	assert first.dispose_calls == 0  # States not disposed on key change


def test_state_disposes_direct_instances():
	ctx = HookContext()

	with ctx:
		direct = DummyState()
		retained = state("test", direct)
		assert retained is direct

	with ctx:
		transient = DummyState()
		# When reusing states, State instances passed as args are disposed if not being used
		result = state("test", transient)
		assert result is direct  # Should return the existing state
		# transient should be disposed since it's not being used
		assert transient.dispose_calls == 1


def test_state_allows_multiple_calls_with_different_keys():
	ctx = HookContext()

	with ctx:
		state_a = state("a", DummyState)
		state_b = state("b", DummyState)
		state_c = state("c", DummyState)

	assert state_a is not state_b
	assert state_b is not state_c
	assert state_a.dispose_calls == 0
	assert state_b.dispose_calls == 0
	assert state_c.dispose_calls == 0


def test_state_enforces_single_call_per_key():
	ctx = HookContext()

	with ctx:
		state("a", DummyState)
		with pytest.raises(
			RuntimeError,
			match="can only be called once per component render with key='a'",
		):
			state("a", DummyState)


def test_state_allows_same_key_across_renders():
	ctx = HookContext()

	with ctx:
		first = state("a", DummyState)

	with ctx:
		second = state("a", DummyState)

	assert first is second


def test_state_requires_non_empty_key():
	ctx = HookContext()

	with ctx:
		with pytest.raises(ValueError, match="requires a non-empty string key"):
			state("", DummyState)


def test_state_disposes_all_on_unmount():
	ctx = HookContext()

	with ctx:
		state_a = state("a", DummyState)
		state_b = state("b", DummyState)
		state_c = state("c", DummyState)

	# Unmount disposes all hooks
	ctx.unmount()

	assert state_a.dispose_calls == 1
	assert state_b.dispose_calls == 1
	assert state_c.dispose_calls == 1


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
