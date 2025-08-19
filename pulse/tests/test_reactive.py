import asyncio
from typing import Any
import pytest
from pulse import (
    Signal,
    Computed,
    Effect,
    computed,
    effect,
    Untrack,
)
from pulse import reactive
from pulse.reactive import Batch, flush_effects
from pulse.reactive_extensions import (
    ReactiveDict,
    ReactiveList,
    ReactiveSet,
    reactive_dataclass,
)
import pulse as ps


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

    @effect
    def e():
        if s() < 10:
            s.write(s() + 1)

    flush_effects()
    assert s() == 10
    assert e.runs == 11  # 10 increment runs + 1 run without a write


def test_effect_doesnt_rerun_if_read_after_write():
    s = Signal(0)
    t = Signal(False)

    @effect
    def e():
        if t():
            s.write(1)
            # read after write
            s()

    flush_effects()
    assert e.runs == 1
    t.write(True)

    flush_effects()
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


def test_reactive_list_basic_index_reactivity():
    lst = ReactiveList([1, 2, 3])
    assert isinstance(lst, list)

    seen: list = []

    @effect
    def e():
        seen.append(lst[1])  # subscribe to index 1

    flush_effects()
    assert e.runs == 1
    assert seen == [2]

    # mutate a different index -> no rerun
    lst[0] = 10
    flush_effects()
    assert e.runs == 1
    assert seen == [2]

    # mutate the observed index
    lst[1] = 20
    flush_effects()
    assert e.runs == 2
    assert seen == [2, 20]

    # setting same value should not trigger
    lst[1] = 20
    flush_effects()
    assert e.runs == 2
    assert seen == [2, 20]


def test_reactive_list_structural_changes_bump_version_and_remap_dependencies():
    lst = ReactiveList([3, 1, 2])

    versions: list[int] = []
    first_values: list = []

    @effect
    def e():
        # depend on structural version and first item
        versions.append(lst.version)
        first_values.append(lst[0])

    flush_effects()
    assert versions[-1] == 0 and first_values[-1] == 3

    lst.append(0)
    flush_effects()
    assert versions[-1] == 1 and first_values[-1] == 3

    lst.pop()
    flush_effects()
    assert versions[-1] == 2 and first_values[-1] == 3

    # sort should reorder signals and cause effect to rerun; first item changes to 1
    lst.sort()
    flush_effects()
    assert versions[-1] == 3
    assert first_values[-1] == 1


def test_reactive_set_membership_reactivity_add_remove():
    s = ReactiveSet({"a"})
    assert isinstance(s, set)

    checks: list[bool] = []

    @effect
    def e():
        # subscribe to membership for "b"
        checks.append("b" in s)

    flush_effects()
    assert checks == [False]

    s.add("b")
    flush_effects()
    assert checks == [False, True]

    s.discard("b")
    flush_effects()
    assert checks == [False, True, False]

    # discarding again should not change
    runs = e.runs
    s.discard("b")
    flush_effects()
    assert e.runs == runs


def test_reactive_dataclass_fields_are_signals_and_wrapped():
    @reactive_dataclass
    class Model:
        x: int = 1
        tags: list[int] = None  # type: ignore[assignment]

    m = Model()
    m.x = 2
    m.tags = [1, 2]

    # fields read/write go through signals
    seen: list[int] = []

    @effect
    def e():
        seen.append(m.x)

    flush_effects()
    assert seen == [2]

    m.x = 5
    flush_effects()
    assert seen == [2, 5]

    # collections are auto-wrapped
    assert isinstance(m.tags, ReactiveList)
    m.tags.append(3)
    # structural change shouldn't affect x subscribers
    runs = e.runs
    flush_effects()
    assert e.runs == runs


def test_nested_reactive_dict_and_list_deep_reactivity():
    ctx: dict[str, Any] = reactive(
        (
            {
                "user": {
                    "name": "Ada",
                    "tags": ["a", "b"],
                }
            }
        )
    )

    # ensure wrapping
    user = ctx["user"]
    assert isinstance(user, ReactiveDict)
    assert isinstance(user["tags"], ReactiveList)

    name_reads: list[str] = []
    v_reads: list[int] = []

    @effect
    def e():
        u = ctx["user"]  # depend on user key
        name_reads.append(u["name"])  # and nested name key
        v_reads.append(u["tags"].version)

    flush_effects()
    assert name_reads == ["Ada"] and v_reads == [0]

    # Update unrelated top-level key should not rerun
    ctx["other"] = 1
    flush_effects()
    assert name_reads == ["Ada"] and v_reads == [0]

    # Update nested name should rerun
    u2 = ctx["user"]
    u2["name"] = "Grace"
    flush_effects()
    assert name_reads == ["Ada", "Grace"]

    # Structural change to nested tags should bump version and rerun
    u2["tags"].append("c")
    flush_effects()
    assert v_reads[-1] == 1

    # Changing a non-watched index shouldn't change name dependency
    len_v_reads = len(v_reads)
    u2["tags"][1] = "bb"
    flush_effects()
    assert name_reads[-1] == "Grace"
    assert len(v_reads) == len_v_reads


def test_reactive_list_len_is_reactive_and_slice_optimization():
    lst = ReactiveList([1, 2, 3, 4])

    len_reads: list[int] = []

    @effect
    def e():
        len_reads.append(len(lst))

    flush_effects()
    assert len_reads == [4]

    # In-place per-index change should not affect len-based effect
    runs = e.runs
    lst[1] = 20
    flush_effects()
    assert e.runs == runs

    # Equal-length slice assignment: should not bump len
    lst[1:3] = [200, 300]
    flush_effects()
    assert e.runs == runs
    assert len_reads == [4]

    # Unequal-length slice assignment: should bump len
    lst[0:2] = [100]
    flush_effects()
    assert len_reads[-1] == 3

    # Structural ops bump len
    lst.append(9)
    flush_effects()
    assert len_reads[-1] == 4
    lst.pop()
    flush_effects()
    assert len_reads[-1] == 3


def test_reactive_list_iter_is_reactive_to_structure_only():
    lst = ReactiveList([1, 2, 3])

    iter_counts: list[int] = []

    @effect
    def e():
        # Depend only on iteration count, not values
        iter_counts.append(sum(1 for _ in lst))

    flush_effects()
    assert iter_counts == [3]

    # Change a value in place: should not rerun, since __iter__ depends on structure only
    runs = e.runs
    lst[0] = 10
    flush_effects()
    assert e.runs == runs

    # Structural change via append triggers rerun
    lst.append(4)
    flush_effects()
    assert iter_counts[-1] == 4

    # Equal-length slice replacement should not rerun
    lst[1:3] = [20, 30]
    flush_effects()
    assert iter_counts[-1] == 4

    # Unequal-length slice replacement should rerun
    lst[0:2] = [100]
    flush_effects()
    assert iter_counts[-1] == 3


def test_state_wraps_collection_defaults_and_sets():
    class S(ps.State):
        items = [1, 2]
        flags = {"a"}

    s = S()
    assert isinstance(s.items, ReactiveList)
    assert isinstance(s.flags, ReactiveSet)

    seen = []

    @effect
    def e():
        seen.append(s.items[0])

    flush_effects()
    assert seen == [1]

    s.items[0] = 9
    flush_effects()
    assert seen == [1, 9]

    # setting a new collection value gets wrapped
    s.items = [7]
    assert isinstance(s.items, ReactiveList)
    assert s.items[0] == 7


# TODO:
# - Tests to verify that effects unregister themselves from their batch
# - The above, BUT the effect is rescheduled into the same batch as a result of running
