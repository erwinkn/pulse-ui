import pytest
from pulse.reactive import Signal, Computed, Effect, batch, computed, effect, untrack


class TestReactiveSystem:
    def test_signal_creation_and_access(self):
        s = Signal(10, name="s")
        assert s() == 10

    def test_signal_update(self):
        s = Signal(10, name="s")
        s.write(20)
        assert s() == 20

    def test_simple_computed(self):
        s = Signal(10, name="s")
        c = Computed(lambda: s() * 2, name="c")
        assert c() == 20
        s.write(20)
        assert c() == 40

    def test_simple_effect(self):
        s = Signal(10, name="s")
        runs = 0
        effect_value = 0

        @effect
        def my_effect():
            nonlocal runs, effect_value
            runs += 1
            effect_value = s()


        assert runs == 1
        assert effect_value == 10

        s.write(20)
        assert runs == 2
        assert effect_value == 20

        # Test that effect doesn't run if value is the same
        s.write(20)
        assert runs == 2

    def test_computed_chain(self):
        s = Signal(2, name="s")
        c1 = Computed(lambda: s() * 2, name="c1")
        c2 = Computed(lambda: c1() * 2, name="c2")

        assert c2() == 8

        s.write(3)

        assert c1() == 6
        assert c2() == 12

    def test_dynamic_dependencies(self):
        s1 = Signal(10, name="s1")
        s2 = Signal(20, name="s2")
        toggle = Signal(True, name="toggle")

        c = Computed(lambda: s1() if toggle() else s2(), name="c")

        assert c() == 10

        toggle.write(False)
        assert c() == 20

        runs = 0
        c_val = None

        def effect_on_c():
            nonlocal runs, c_val
            c_val = c()
            runs += 1

        Effect(effect_on_c, name="effect_on_c")
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
        s1 = Signal(1, name="s1")
        s2 = Signal(10, name="s2")

        runs = 0

        def my_effect():
            nonlocal runs
            runs += 1
            s1()  # dependency
            with untrack():
                s2()  # no dependency

        Effect(my_effect, name="untrack_effect")

        assert runs == 1

        s2.write(20)  # should not trigger effect
        assert runs == 1

        s1.write(2)  # should trigger effect
        assert runs == 2

    def test_batching(self):
        s1 = Signal(1, name="s1")
        s2 = Signal(10, name="s2")

        runs = 0

        c = Computed(lambda: s1() + s2(), name="c")

        def my_effect():
            nonlocal runs
            c()
            runs += 1

        Effect(my_effect, name="batching_effect")

        assert runs == 1
        assert c() == 11

        with batch():
            s1.write(2)
            s2.write(20)

        assert c() == 22
        assert runs == 2

    def test_effects_run_after_batch(self):
        with batch():

            @effect(name="effect_in_batch")
            def e(): ...

            assert e.runs == 0

        assert e.runs == 1

    def test_computed_updated_within_batch(self):
        s = Signal(1)
        double = Computed(lambda: 2 * s())
        with batch():
            s.write(2)
            # Depending on the reactive architecture chosen, this may return `2`
            # still. To avoid surprises, Pulse favors consistency.
            assert double() == 4

    def test_no_update_if_value_didnt_change(self):
        s = Signal(1)

        @effect
        def e():
            s()

        assert e.runs == 1
        s.write(2)
        assert e.runs == 2
        s.write(2)
        assert e.runs == 2

    def test_cycle_detection(self):
        s1 = Signal(1, name="s1")
        c1 = Computed(lambda: s1() if s1() < 10 else c2(), name="c1")
        c2 = Computed(lambda: c1(), name="c2")

        # This should not raise an error
        c2()

        s1.write(10)

        with pytest.raises(RuntimeError, match="Circular dependency detected"):
            c2()

    def test_unused_computed_are_not_recomputed(self):
        a = Signal(1, name="a")

        b_runs = 0

        def b_fn():
            nonlocal b_runs
            b_runs += 1
            return a() * 2

        b = Computed(b_fn, name="b")

        c_runs = 0

        def c_fn():
            nonlocal c_runs
            c_runs += 1
            return b() * 2

        c = Computed(c_fn, name="c")

        d_runs = 0

        def d_fn():
            nonlocal d_runs
            d_runs += 1
            return c() * 2

        d = Computed(d_fn, name="d")

        effect_runs = 0

        def effect():
            nonlocal effect_runs
            effect_runs += 1
            b()

        Effect(effect, name="effect1")

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

        Effect(effect2, name="effect2")

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

    def test_diamond_problem(self):
        a = Signal(1, name="a")

        b = Computed(lambda: a() * 2, name="b")
        c = Computed(lambda: a() * 3, name="c")

        d_runs = 0

        @computed(name='d')
        def d():
            nonlocal d_runs
            d_runs += 1
            return b() + c()

        assert d_runs == 0, "d should not run unless used by an effect"

        result = 0

        @effect(name='diamond_effect')
        def e():
            nonlocal result
            result = d()

        assert result == 5
        assert d_runs == 1

        a.write(2)

        assert result == 10
        assert d_runs == 2, "d should only be recomputed once"

    def test_glitch_avoidance(self):
        a = Signal(1, name="a")
        b = Signal(10, name="b")

        c_values = []
        c = Computed(lambda: a() + b(), name="c")

        effect_runs = 0

        def effect():
            nonlocal effect_runs
            c_values.append(c())
            effect_runs += 1

        Effect(effect, name="glitch_effect")

        assert effect_runs == 1
        assert c_values == [11]

        with batch():
            a.write(2)
            b.write(20)

        assert effect_runs == 2, "Effect should only run once for a batched update"
        assert c_values == [11, 22]

    def test_effect_cleanup_on_rerun(self):
        s = Signal(0, name="s")
        cleanup_runs = 0

        def my_effect():
            s()  # depend on s

            def cleanup():
                nonlocal cleanup_runs
                cleanup_runs += 1

            return cleanup

        Effect(my_effect, name="cleanup_effect")

        assert cleanup_runs == 0
        s.write(1)
        assert cleanup_runs == 1
        s.write(2)
        assert cleanup_runs == 2

    def test_effect_manual_dispose(self):
        cleanup_runs = 0

        def my_effect():
            def cleanup():
                nonlocal cleanup_runs
                cleanup_runs += 1

            return cleanup

        effect = Effect(my_effect, name="disposable_effect")

        assert cleanup_runs == 0
        effect.dispose()
        assert cleanup_runs == 1

    def test_nested_effect_cleanup_on_rerun(self):
        s = Signal(0, name="s")
        child_cleanup_runs = 0

        def child_effect():
            def cleanup():
                nonlocal child_cleanup_runs
                child_cleanup_runs += 1

            return cleanup

        def parent_effect():
            s()  # depend on s
            Effect(child_effect, name="child")

        Effect(parent_effect, name="parent")

        assert child_cleanup_runs == 0
        s.write(1)
        assert child_cleanup_runs == 1
        s.write(2)
        assert child_cleanup_runs == 2

    def test_nested_effect_cleanup_on_dispose(self):
        child_cleanup_runs = 0

        def child_effect():
            def cleanup():
                nonlocal child_cleanup_runs
                child_cleanup_runs += 1

            return cleanup

        def parent_effect():
            Effect(child_effect, name="child")

        parent = Effect(parent_effect, name="parent")

        assert child_cleanup_runs == 0
        parent.dispose()
        assert child_cleanup_runs == 1
