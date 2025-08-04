"""
Tests for the reactive system in pulse.reactive.
"""

import pytest
from pulse.reactive import (
    Signal,
    Computed,
    Effect,
    untrack,
    batch,
)


class TestReactiveSystem:
    def test_signal_creation_and_access(self):
        s = Signal(10)
        assert s() == 10

    def test_signal_update(self):
        s = Signal(10)
        s.write(20)
        assert s() == 20

    def test_simple_computed(self):
        s = Signal(10)
        c = Computed(lambda: s() * 2)
        assert c() == 20
        s.write(20)
        assert c() == 40

    def test_simple_effect(self):
        s = Signal(10)
        runs = 0
        effect_value = 0

        def my_effect():
            nonlocal runs, effect_value
            runs += 1
            effect_value = s()

        Effect(my_effect)

        assert runs == 1
        assert effect_value == 10

        s.write(20)
        assert runs == 2
        assert effect_value == 20

        # Test that effect doesn't run if value is the same
        s.write(20)
        assert runs == 2

    def test_computed_chain(self):
        s = Signal(2)
        c1 = Computed(lambda: s() * 2)
        c2 = Computed(lambda: c1() * 2)

        assert c2() == 8

        s.write(3)

        assert c1() == 6
        assert c2() == 12

    def test_dynamic_dependencies(self):
        s1 = Signal(10)
        s2 = Signal(20)
        toggle = Signal(True)

        c = Computed(lambda: s1() if toggle() else s2())

        assert c() == 10

        toggle.write(False)
        assert c() == 20

        runs = 0
        c_val = None

        def effect_on_c():
            nonlocal runs, c_val
            c_val = c()
            runs += 1

        Effect(effect_on_c)
        assert runs == 1
        assert c_val == 20

        # Now that toggle is False, c depends on s2.
        # Changing s1 should not cause c to recompute or the effect to run.
        s1.write(50)
        assert runs == 1

        # Changing s2 should trigger a re-run.
        s2.write(200)
        assert c_val == 200
        assert runs == 2

    def test_untrack(self):
        s1 = Signal(1)
        s2 = Signal(10)

        runs = 0

        def my_effect():
            nonlocal runs
            runs += 1
            s1()  # dependency
            untrack(lambda: s2())  # no dependency

        Effect(my_effect)

        assert runs == 1

        s2.write(20)  # should not trigger effect
        assert runs == 1

        s1.write(2)  # should trigger effect
        assert runs == 2

    def test_batching(self):
        s1 = Signal(1)
        s2 = Signal(10)

        runs = 0

        c = Computed(lambda: s1() + s2())

        def my_effect():
            nonlocal runs
            c()
            runs += 1

        Effect(my_effect)

        assert runs == 1
        assert c() == 11

        batch(lambda: (s1.write(2), s2.write(20)))

        assert c() == 22
        assert runs == 2

    def test_cycle_detection(self):
        s1 = Signal(1)
        c1 = Computed(lambda: s1() if s1() < 10 else c2())
        c2 = Computed(lambda: c1())

        with pytest.raises(RuntimeError, match="Circular dependency detected"):
            c2()

    def test_unused_computed_are_not_recomputed(self):
        a = Signal(1)

        b_runs = 0

        def b_fn():
            nonlocal b_runs
            b_runs += 1
            return a() * 2

        b = Computed(b_fn)

        c_runs = 0

        def c_fn():
            nonlocal c_runs
            c_runs += 1
            return b() * 2

        c = Computed(c_fn)

        d_runs = 0

        def d_fn():
            nonlocal d_runs
            d_runs += 1
            return c() * 2

        d = Computed(d_fn)

        effect_runs = 0

        def effect():
            nonlocal effect_runs
            effect_runs += 1
            b()

        Effect(effect)

        assert b_runs == 1
        assert c_runs == 0  # c is not used yet
        assert d_runs == 0  # d is not used yet
        assert effect_runs == 1

        a.write(2)

        assert b_runs == 2
        assert c_runs == 0  # c is not used by the effect, so it shouldn't recompute
        assert d_runs == 0  # d is not used by the effect, so it shouldn't recompute
        assert effect_runs == 2

        # Now, let's use d in a new effect

        effect2_runs = 0

        def effect2():
            nonlocal effect2_runs
            effect2_runs += 1
            d()

        Effect(effect2)

        assert b_runs == 2  # b should not recompute
        assert c_runs == 1  # c is now used, so it computes once
        assert d_runs == 1  # d is now used, so it computes once
        assert effect2_runs == 1

        a.write(3)

        assert b_runs == 3
        assert c_runs == 2
        assert d_runs == 2
        assert effect_runs == 3
        assert effect2_runs == 2
