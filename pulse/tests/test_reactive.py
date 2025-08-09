import asyncio
import pytest
from pulse import (
    Signal,
    Computed,
    Effect,
    computed,
    effect,
    Untrack,
)
from pulse.reactive import Batch, flush_effects, ReactiveDict


def test_signal_creation_and_access():
    s = Signal(10, name="s")
    assert s() == 10


def test_signal_update():
    s = Signal(10, name="s")
    s.write(20)
    assert s() == 20


def test_simple_computed():
    s = Signal(10, name="s")
    c = Computed(lambda: s() * 2, name="c")
    assert c() == 20
    s.write(20)
    assert c() == 40


def test_simple_effect():
    s = Signal(10, name="s")
    effect_value = 0

    @effect
    def my_effect():
        nonlocal effect_value
        effect_value = s()

    flush_effects()

    assert my_effect.runs == 1
    assert effect_value == 10

    s.write(20)
    flush_effects()
    assert my_effect.runs == 2
    assert effect_value == 20

    # Test that effect doesn't run if value is the same
    s.write(20)
    flush_effects()
    assert my_effect.runs == 2


def test_computed_chain():
    s = Signal(2, name="s")
    c1 = Computed(lambda: s() * 2, name="c1")
    c2 = Computed(lambda: c1() * 2, name="c2")

    assert c2() == 8

    s.write(3)

    assert c1() == 6
    assert c2() == 12


def test_dynamic_dependencies():
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
    flush_effects()
    assert runs == 1
    assert c_val == 20

    # Now that toggle is False, c depends on s2.
    # Changing s1 should not cause c to recompute or the effect to run.
    s1.write(50)
    flush_effects()
    assert runs == 1

    # Changing s2 should trigger a re-run.
    s2.write(200)
    flush_effects()
    assert c_val == 200
    assert runs == 2


def test_untrack():
    s1 = Signal(1, name="s1")
    s2 = Signal(10, name="s2")

    runs = 0

    def my_effect():
        nonlocal runs
        runs += 1
        s1()  # dependency
        with Untrack():
            s2()  # no dependency

    Effect(my_effect, name="untrack_effect")
    flush_effects()

    assert runs == 1

    s2.write(20)  # should not trigger effect
    flush_effects()
    assert runs == 1

    s1.write(2)  # should trigger effect
    flush_effects()
    assert runs == 2


def test_batching():
    s1 = Signal(1, name="s1")
    s2 = Signal(10, name="s2")

    c = Computed(lambda: s1() + s2(), name="c")

    @effect
    def batching_effect():
        c()

    flush_effects()

    assert batching_effect.runs == 1
    assert c() == 11

    with Batch():
        s1.write(2)
        s2.write(20)

    assert c() == 22
    assert batching_effect.runs == 2


def test_effects_run_after_batch():
    with Batch():

        @effect(name="effect_in_batch")
        def e(): ...

        assert e.runs == 0

    assert e.runs == 1


def test_computed_updates_within_batch():
    s = Signal(1)
    double = Computed(lambda: 2 * s())
    with Batch():
        s.write(2)
        # Depending on the reactive architecture chosen, this may return `2`
        # still. To avoid surprises, Pulse favors consistency.
        assert double() == 4


def test_no_update_if_value_didnt_change():
    s = Signal(1)

    @effect
    def e():
        s()

    flush_effects()
    assert e.runs == 1
    s.write(2)
    flush_effects()
    assert e.runs == 2
    s.write(2)
    flush_effects()
    assert e.runs == 2


def test_cycle_detection():
    s1 = Signal(1, name="s1")
    c1 = Computed(lambda: s1() if s1() < 10 else c2(), name="c1")
    c2 = Computed(lambda: c1(), name="c2")

    # This should not raise an error
    c2()

    s1.write(10)

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        c2()


def test_unused_computed_are_not_recomputed():
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
    flush_effects()

    assert b_runs == 1
    assert c_runs == 0  # c is not used yet
    assert d_runs == 0  # d is not used yet
    assert effect_runs == 1

    a.write(2)
    flush_effects()

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
    flush_effects()

    assert b_runs == 2  # b should not recompute
    assert c_runs == 1  # c is now used, so it computes once
    assert d_runs == 1  # d is now used, so it computes once
    assert effect2_runs == 1

    a.write(3)
    flush_effects()
    assert b_runs == 3
    assert c_runs == 2
    assert d_runs == 2
    assert effect_runs == 3
    assert effect2_runs == 2


def test_diamond_problem():
    a = Signal(1, name="a")

    b = Computed(lambda: a() * 2, name="b")
    c = Computed(lambda: a() * 3, name="c")

    d_runs = 0

    @computed(name="d")
    def d():
        nonlocal d_runs
        d_runs += 1
        return b() + c()

    assert d_runs == 0, "d should not run unless used by an effect"

    result = 0

    @effect(name="diamond_effect")
    def e():
        nonlocal result
        result = d()

    flush_effects()
    assert result == 5
    assert d_runs == 1

    a.write(2)
    flush_effects()

    assert result == 10
    assert d_runs == 2, "d should only be recomputed once"


def test_glitch_avoidance():
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
    flush_effects()

    assert effect_runs == 1
    assert c_values == [11]

    with Batch():
        a.write(2)
        b.write(20)

    assert effect_runs == 2, "Effect should only run once for a batched update"
    assert c_values == [11, 22]


def test_effect_cleanup_on_rerun():
    s = Signal(0, name="s")
    cleanup_runs = 0

    def my_effect():
        s()  # depend on s

        def cleanup():
            nonlocal cleanup_runs
            cleanup_runs += 1

        return cleanup

    Effect(my_effect, name="cleanup_effect")
    flush_effects()

    assert cleanup_runs == 0
    s.write(1)
    flush_effects()
    assert cleanup_runs == 1
    s.write(2)
    flush_effects()
    assert cleanup_runs == 2


def test_effect_manual_cleanup():
    cleanup_runs = 0

    def my_effect():
        def cleanup():
            nonlocal cleanup_runs
            cleanup_runs += 1

        return cleanup

    effect = Effect(my_effect, name="disposable_effect")
    flush_effects()

    assert cleanup_runs == 0
    effect.dispose()
    assert cleanup_runs == 1


def test_nested_effect_cleanup_on_rerun():
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
    flush_effects()

    assert child_cleanup_runs == 0
    s.write(1)
    flush_effects()
    assert child_cleanup_runs == 1
    s.write(2)
    flush_effects()
    assert child_cleanup_runs == 2


def test_nested_effect_cleanup_on_dispose():
    child_cleanup_runs = 0

    def child_effect():
        def cleanup():
            nonlocal child_cleanup_runs
            child_cleanup_runs += 1

        return cleanup

    def parent_effect():
        Effect(child_effect, name="child")

    parent = Effect(parent_effect, name="parent")
    flush_effects()

    assert child_cleanup_runs == 0
    parent.dispose()
    assert child_cleanup_runs == 1


@pytest.mark.asyncio
async def test_sync_writes_are_batched():
    a = Signal(1, "a")
    b = Signal(2, "b")

    @effect
    def e():
        a()
        b()

    assert e.runs == 0

    # Give the async loop time to run the effect
    await asyncio.sleep(0)
    assert e.runs == 1

    a.write(2)
    assert e.runs == 1
    b.write(4)
    assert e.runs == 1

    # Give the async loop time to process queued tasks
    await asyncio.sleep(0)
    assert e.runs == 2

    a.write(3)
    assert e.runs == 2
    await asyncio.sleep(0)
    assert e.runs == 3
    b.write(6)
    assert e.runs == 3


def test_immediate_effect():
    s = Signal(1)

    @effect()
    def e1():
        s()

    assert e1.runs == 0

    @effect(immediate=True)
    def e2():
        s()

    assert e2.runs == 1
    flush_effects()
    assert e1.runs == 1
    assert e2.runs == 1


def test_disposed_effect_doesnt_rerun():
    s = Signal(1)

    @effect()
    def e():
        s()

    flush_effects()
    assert e.runs == 1

    s.write(2)
    flush_effects()
    assert e.runs == 2

    e.dispose()
    s.write(3)
    flush_effects()
    assert e.runs == 2


def test_schedule_lazy_effect():
    s = Signal(1)

    @effect(lazy=True)
    def e():
        s()

    assert e.runs == 0
    flush_effects()
    assert e.runs == 0

    e.schedule()
    flush_effects()
    assert e.runs == 1

    s.write(2)
    flush_effects()
    assert e.runs == 2


def test_run_lazy_effect():
    s = Signal(1)

    @effect(lazy=True)
    def e():
        s()

    assert e.runs == 0
    flush_effects()
    assert e.runs == 0

    e.run()
    assert e.runs == 1
    flush_effects()
    assert e.runs == 1

    s.write(2)
    flush_effects()
    assert e.runs == 2


def test_dispose_effect_removes_from_exact_batch():
    @effect
    def e(): ...

    assert e.runs == 0

    with Batch():
        e.dispose()
    flush_effects()
    assert e.runs == 0


def test_effect_unregister_from_parent_on_disposal():
    @effect
    def e():
        @effect
        def e2(): ...

    flush_effects()
    assert len(e.children) == 1
    e = e.children[0]
    e.dispose()
    assert e.children == []


def test_effect_unregister_from_batch_on_disposal():
    with Batch() as batch:  # noqa: F841

        @effect
        def e(): ...

        assert batch.effects == [e]
        e.dispose()
        assert batch.effects == []


def test_effect_unset_batch_after_run():
    with Batch() as batch:  # noqa: F841

        @effect
        def e(): ...

        assert e.batch == batch
    assert e.batch is None


def test_effect_rescheduling_itself():
    s = Signal(0)
    with Batch() as batch:

        @effect
        def e():
            print("Running e")
            val = s()
            if val == 0:
                print("Writing to s")
                print(f"s observers: {s.obs}")
                s.write(1)

    assert e.runs == 2


def test_reactive_dict_basic_reads_and_writes():
    ctx = ReactiveDict({"a": 1})
    reads = []

    @effect
    def e():
        reads.append(ctx["a"])  # subscribe to key 'a'

    flush_effects()
    assert reads == [1]

    ctx["a"] = 2
    flush_effects()
    assert reads == [1, 2]

    # setting same value should not schedule effect run
    @effect
    def e2():
        _ = ctx["a"]

    flush_effects()
    runs = e2.runs
    ctx["a"] = 2
    flush_effects()
    assert e2.runs == runs


def test_reactive_dict_per_key_isolation():
    ctx = ReactiveDict({"a": 1, "b": 10})

    @effect
    def ea():
        _ = ctx["a"]

    @effect
    def eb():
        _ = ctx["b"]

    flush_effects()
    assert ea.runs == 1 and eb.runs == 1

    ctx["a"] = 2
    flush_effects()
    assert ea.runs == 2 and eb.runs == 1

    ctx["b"] = 20
    flush_effects()
    assert ea.runs == 2 and eb.runs == 2


def test_reactive_dict_delete_sets_none_preserving_subscribers():
    ctx = ReactiveDict({"a": 1})
    values = []

    @effect
    def e():
        values.append(ctx["a"])  # subscribe

    flush_effects()
    assert values == [1]

    del ctx["a"]
    flush_effects()
    assert values == [1, None]

    # re-set should notify again
    ctx["a"] = 3
    flush_effects()
    assert values == [1, None, 3]


# TODO:
# - Tests to verify that effects unregister themselves from their batch
# - The above, BUT the effect is rescheduled into the same batch as a result of running
