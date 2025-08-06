"""
Tests for the State class and computed properties.
"""

import pulse as ps


class TestState:
    def test_simple_state(self):
        class MyState(ps.State):
            count: int = 0

        state = MyState()
        assert state.count == 0
        state.count = 5
        assert state.count == 5

    def test_computed_property(self):
        class MyState(ps.State):
            count: int = 0

            @ps.computed
            def double_count(self):
                return self.count * 2

        state = MyState()
        assert state.double_count == 0

        state.count = 5
        assert state.double_count == 10

    def test_computed_property_chaining(self):
        class MyState(ps.State):
            count: int = 0

            @ps.computed
            def double_count(self):
                return self.count * 2

            @ps.computed
            def quadruple_count(self):
                return self.double_count * 2

        state = MyState()
        assert state.quadruple_count == 0

        state.count = 5
        assert state.double_count == 10
        assert state.quadruple_count == 20

    def test_repr(self):
        class MyState(ps.State):
            count: int = 0
            name: str = "Test"

            @ps.computed
            def double_count(self):
                return self.count * 2

        state = MyState()
        state.count = 5
        repr_str = repr(state)
        assert "count=5" in repr_str
        assert "name='Test'" in repr_str
        assert "double_count=10 (computed)" in repr_str

    def test_state_instances_are_independent(self):
        class MyState(ps.State):
            count: int = 0

        state_a = MyState()
        state_b = MyState()

        state_a.count = 10
        assert state_a.count == 10
        assert state_b.count == 0, "state_b.count should not have changed"

    def test_state_effect(self):
        effect_runs = 0

        class MyState(ps.State):
            count: int = 0

            @ps.effect
            def my_effect(self):
                nonlocal effect_runs
                _ = self.count
                effect_runs += 1

        state = MyState()
        assert effect_runs == 1, "Effect should run once on initialization"

        state.count = 5
        assert effect_runs == 2, "Effect should re-run when dependency changes"

        state.count = 10
        assert effect_runs == 3, "Effect should re-run on subsequent changes"
