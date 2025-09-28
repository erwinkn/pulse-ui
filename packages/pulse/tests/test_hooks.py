import pytest

from pulse.hooks import HookContext, setup, setup_key, states, effects, stable
from pulse.state import State


class DummyState(State):
    def __init__(self):
        self._dispose_calls = 0
        super().__init__()

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


def test_states_recreates_when_key_changes():
    ctx = HookContext()

    with ctx:
        first = states(DummyState, key="a")

    with ctx:
        second = states(DummyState, key="b")

    assert first is not second
    assert first.dispose_calls == 1


def test_states_disposes_direct_instances():
    ctx = HookContext()

    with ctx:
        direct = DummyState()
        retained = states(direct)
        assert retained is direct

    with ctx:
        transient = DummyState()
        states(transient)

    assert transient.dispose_calls == 1


def test_states_disallows_multiple_calls():
    ctx = HookContext()

    with ctx:
        states(DummyState)
        with pytest.raises(RuntimeError):
            states(DummyState)


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
