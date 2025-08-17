"""
Tests for the State class and computed properties.
"""

from typing import cast
import pytest
import pulse as ps
from pulse.reactive import flush_effects
from pulse.reactive_extensions import ReactiveDict, ReactiveList, ReactiveSet


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

    def test_nested_structures_wrapped_and_reactive(self):
        class S(ps.State):
            data = {
                "user": {"name": "Ada", "friends": ["b"]},
                "ids": [1, 2],
                "set": {"x"},
            }

        s = S()
        # Ensure wrapping
        assert isinstance(s.data, ReactiveDict)
        assert isinstance(s.data["user"], ReactiveDict)
        assert isinstance(s.data["user"]["friends"], ReactiveList)
        assert isinstance(s.data["ids"], ReactiveList)
        assert isinstance(s.data["set"], ReactiveSet)

        name_reads = []
        ids_versions = []
        set_checks = []

        @ps.effect
        def track():
            name_reads.append(s.data["user"]["name"])  # reactive path user.name
            ids_versions.append(s.data["ids"].version)  # structural version
            set_checks.append("x" in s.data["set"])  # membership signal

        flush_effects()
        assert name_reads == ["Ada"] and ids_versions == [0] and set_checks == [True]

        # Non-related update shouldn't trigger name update
        s.data["other"] = 1
        flush_effects()
        assert name_reads == ["Ada"]

        # Update name
        s.data["user"]["name"] = "Grace"
        flush_effects()
        assert name_reads[-1] == "Grace"

        # Bump ids structure
        s.data["ids"].append(3)
        flush_effects()
        assert ids_versions[-1] == 1

        # Toggle set membership
        s.data["set"].discard("x")
        flush_effects()
        assert set_checks[-1] is False

    def test_non_reactive_property_detection(self):
        """Test that assignment to non-reactive properties after initialization is caught"""

        class MyState(ps.State):
            count: int = 0
            name: str = "test"

        state = MyState()

        # Setting reactive properties should work
        state.count = 10
        state.name = "updated"
        assert state.count == 10
        assert state.name == "updated"

        # Setting non-reactive property should fail
        with pytest.raises(
            AttributeError,
            match=r"Cannot assign to non-reactive property 'dynamic_prop'",
        ):
            state.dynamic_prop = "should fail"

    def test_private_attributes_allowed(self):
        """Test that private attributes can be set even after initialization"""

        class MyState(ps.State):
            count: int = 0

        state = MyState()

        # Private attributes should be allowed
        state._private = "ok"
        state.__very_private = "also ok"
        state._internal_counter = 42

        assert state._private == "ok" # type: ignore
        assert state.__very_private == "also ok" # type: ignore
        assert state._internal_counter == 42 # type: ignore

    def test_special_state_attributes_allowed(self):
        """Test that special State attributes can be set"""

        class MyState(ps.State):
            count: int = 0

        state = MyState()

        # These special attributes should be allowed
        from pulse.reactive import Scope

        new_scope = Scope()
        state.scope = new_scope
        assert state.scope is new_scope

    def test_assignment_during_custom_init(self):
        """Test that properties can be assigned during custom __init__ before full initialization"""

        assignments_during_init = []

        class MyState(ps.State):
            count: int = 0

            def __init__(self):
                # Before calling super().__init__, we should be able to assign anything
                assignments_during_init.append("before_super")

                # This should work - we're not fully initialized yet
                self.temp_property = "temporary"
                assignments_during_init.append("assigned_temp")

                super().__init__()
                assignments_during_init.append("after_super")

                # After initialization, assignment to non-reactive properties should fail
                try:
                    self.another_prop = "should fail"
                    assignments_during_init.append("ERROR: should not reach here")
                except AttributeError:
                    assignments_during_init.append("correctly_caught_post_init")

        state = MyState()

        # Verify the sequence worked as expected
        expected = [
            "before_super",
            "assigned_temp",
            "after_super",
            "correctly_caught_post_init",
        ]
        assert assignments_during_init == expected

        # The temp property assigned during init should exist
        assert hasattr(state, "temp_property")
        assert state.temp_property == "temporary"

        # But we can't assign new non-reactive properties now
        with pytest.raises(AttributeError):
            state.new_prop = "fail"

    def test_descriptors_still_work(self):
        """Test that computed properties and other descriptors still work correctly"""

        class MyState(ps.State):
            count: int = 0

            @ps.computed
            def double_count(self):
                return self.count * 2

        state = MyState()

        # Computed property should work
        assert state.double_count == 0

        state.count = 5
        assert state.double_count == 10

        # Trying to assign to computed property should still raise the original error
        with pytest.raises(
            AttributeError, match=r"Cannot set computed property 'double_count'"
        ):
            state.double_count = 100

    def test_helpful_error_message(self):
        """Test that the error message provides helpful guidance"""

        class MyState(ps.State):
            count: int = 0

        state = MyState()

        try:
            state.user_name = "john"
            assert False, "Should have raised AttributeError"
        except AttributeError as e:
            error_msg = str(e)
            assert "Cannot assign to non-reactive property 'user_name'" in error_msg
            assert "MyState" in error_msg
            assert "declare it with a type annotation at the class level" in error_msg
            assert "'user_name: <type> = <default_value>'" in error_msg
