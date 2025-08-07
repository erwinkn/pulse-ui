"""
Tests for the State class and computed properties.
"""

from typing import cast
import pulse as ps
from pulse.reactive import flush_effects


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

    def test_unannotated_property_becomes_signal(self):
        class MyState(ps.State):
            count = 1  # no annotation

            @ps.computed
            def double(self):
                return self.count * 2

        s = MyState()
        assert s.count == 1
        assert s.double == 2
        s.count = 3
        assert s.count == 3
        assert s.double == 6

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

    def test_state_effect_runs_and_reruns(self):
        effect_runs = 0

        class MyState(ps.State):
            count: int = 0

            @ps.effect
            def my_effect(self):
                nonlocal effect_runs
                _ = self.count
                effect_runs += 1

        state = MyState()
        # Not run yet by default
        assert effect_runs == 0
        state.my_effect.schedule()
        flush_effects()
        assert effect_runs == 1

        state.count = 5
        flush_effects()
        assert effect_runs == 2

        state.count = 10
        flush_effects()
        assert effect_runs == 3

    def test_state_effect_without_super_init(self):
        runs = 0

        class Base(ps.State):
            count: int = 0

            @ps.effect
            def bump(self):
                nonlocal runs
                _ = self.count
                runs += 1

        class Child(Base):
            def __init__(self):
                # Intentionally do NOT call super().__init__
                self.custom = True

        s = Child()
        assert runs == 0
        s.bump.schedule()
        flush_effects()
        assert runs == 1
        s.count = 1
        flush_effects()
        assert runs == 2

    def test_computed_and_effect_interaction_inheritance(self):
        runs = 0

        class Base(ps.State):
            a: int = 1
            b: int = 2

            @ps.computed
            def sum(self):
                return self.a + self.b

            @ps.effect
            def track(self):
                nonlocal runs
                _ = self.sum
                runs += 1

        class Child(Base):
            b: int = 3

        s = Child()
        assert runs == 0
        s.track.schedule()
        flush_effects()
        assert runs == 1
        assert s.sum == 4
        s.a = 2
        flush_effects()
        assert runs == 2

    def test_subclass_overrides_property_default(self):
        class Base(ps.State):
            count: int = 0

            @ps.computed
            def doubled(self):
                return self.count * 2

        class Child(Base):
            count: int = 5

        s = Child()
        assert s.count == 5
        assert s.doubled == 10
        s.count = 6
        assert s.doubled == 12

        s = Base()
        assert s.count == 0
        assert s.doubled == 0

    def test_subclass_overrides_unannotated_property_default(self):
        class Base(ps.State):
            count = 1

        class Child(Base):
            count = 7

        s = Child()
        assert s.count == 7
        s.count = 8
        assert s.count == 8

    def test_subclass_overrides_computed(self):
        class Base(ps.State):
            x: int = 1

            @ps.computed
            def value(self):
                return self.x + 1

        class Child(Base):
            @ps.computed
            def value(self):
                return self.x + 2

        s = Child()
        assert s.value == 3
        s.x = 2
        assert s.value == 4

    def test_shadow_effect_overrides_base_effect(self):
        base_runs = 0
        child_runs = 0

        class Base(ps.State):
            a: int = 0

            @ps.effect
            def e(self):
                nonlocal base_runs
                _ = self.a
                base_runs += 1

        class Child(Base):
            @ps.effect
            def e(self):  # shadow base effect
                nonlocal child_runs
                _ = self.a
                child_runs += 1

        s = Child()
        # Only child's effect should be present
        assert base_runs == 0
        assert child_runs == 0
        s.e.schedule()
        flush_effects()
        assert base_runs == 0
        assert child_runs == 1
        s.a = 1
        flush_effects()
        assert base_runs == 0
        assert child_runs == 2

    def test_do_not_wrap_callables_or_descriptors(self):
        class MyState(ps.State):
            count = 1

            def regular(self, x: int) -> int:
                return x + 1

            @staticmethod
            def sm(x: int) -> int:
                return x * 2

            @classmethod
            def cm(cls, x: int) -> int:
                return x * 3

            @property
            def prop(self) -> int:
                return self.count + 10

            @ps.computed
            def doubled(self) -> int:
                return self.count * 2

        s = MyState()
        # methods stay methods
        assert s.regular(2) == 3
        # staticmethod/classmethod stay intact
        assert MyState.sm(2) == 4
        assert s.sm(2) == 4
        assert MyState.cm(2) == 6
        assert s.cm(2) == 6
        # property stays property
        assert s.prop == 11

        # Verify that only the data fields are signals, not the callables/descriptors
        prop_names = {cast(str, sig.name).split(".", 1)[1] for sig in s.properties()}
        assert "count" in prop_names
        assert "doubled" not in prop_names  # it's computed
        assert "regular" not in prop_names
        assert "sm" not in prop_names
        assert "cm" not in prop_names
        assert "prop" not in prop_names

        # Updating a signal updates dependent computed and property reads reflect current state
        s.count = 5
        assert s.doubled == 10
        assert s.prop == 15
