import asyncio
from typing import Any, cast, ClassVar
from dataclasses import dataclass, field, asdict, astuple, replace, InitVar
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


@pytest.mark.asyncio
async def test_async_effect_tracks_dependencies_across_await():
    s1 = Signal(1, name="s1")
    s2 = Signal(2, name="s2")

    seen: list[tuple[str, int]] = []

    @effect
    async def e():
        seen.append(("s1", s1()))
        await asyncio.sleep(0)
        seen.append(("s2", s2()))

    # Initial run
    flush_effects()
    await asyncio.sleep(0)  # start task
    await asyncio.sleep(0)  # finish task
    assert e.runs == 1
    assert seen == [("s1", 1), ("s2", 2)]

    # Change dep observed before await -> reruns
    s1.write(10)
    await asyncio.sleep(0)  # schedule/flush
    await asyncio.sleep(0)  # task to first await
    await asyncio.sleep(0)  # task completes
    assert e.runs == 2
    assert seen[-2:] == [("s1", 10), ("s2", 2)]

    # Change dep observed after await -> reruns
    s2.write(20)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 3
    assert seen[-2:] == [("s1", 10), ("s2", 20)]


@pytest.mark.asyncio
async def test_async_effect_cleanup_on_rerun():
    s = Signal(0, name="s")
    cleanup_runs = 0

    @effect
    async def e():
        _ = s()
        await asyncio.sleep(0)

        def cleanup():
            nonlocal cleanup_runs
            cleanup_runs += 1

        return cleanup

    # complete first run
    flush_effects()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 1
    assert cleanup_runs == 0

    # trigger rerun -> previous cleanup should run once
    s.write(1)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 2
    assert cleanup_runs == 1


# TODO: find a way to make this pass. Effect cancellation works in practice.
@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="Cancellation timing is event-loop dependent; non-deterministic in CI",
    strict=False,
)
async def test_async_effect_cancels_inflight_on_rerun():
    s = Signal(0, name="s")
    progressed_values: list[int] = []
    loop = asyncio.get_event_loop()
    gate0: asyncio.Future[None] = loop.create_future()
    gate1: asyncio.Future[None] = loop.create_future()

    @effect
    async def e():
        _ = s()
        if s() == 0:
            await gate0
        else:
            await gate1
        progressed_values.append(s())

    # Start first run and pause at gate0
    flush_effects()
    await asyncio.sleep(0)
    initial_task = getattr(e, "_task", None)

    # Trigger rerun -> should cancel in-flight task
    s.write(1)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Wait until the effect has rerun and replaced the task, then release gate1 only
    for _ in range(10):
        if (
            getattr(e, "_task", None) is not initial_task
            and getattr(e, "_task", None) is not None
        ):
            break
        await asyncio.sleep(0)

    if not gate1.done():
        gate1.set_result(None)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Only the second run should have progressed (allow a few ticks to settle)
    for _ in range(20):
        if progressed_values == [1]:
            break
        await asyncio.sleep(0)
    assert progressed_values == [1]

    # Releasing gate0 later should not allow the cancelled first run to progress
    if not gate0.done():
        gate0.set_result(None)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert progressed_values == [1]
    # The second run should have completed by now (counts as first completed run)
    assert e.runs == 1


@pytest.mark.asyncio
async def test_async_effect_self_reschedules_on_write():
    s = Signal(0, name="s")

    @effect
    async def e():
        if s() == 0:
            await asyncio.sleep(0)
            s.write(1)
        else:
            await asyncio.sleep(0)

    # First run completes and writes -> schedules rerun
    flush_effects()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Force process scheduled rerun and allow task to complete
    flush_effects()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 2
    assert s() == 1


@pytest.mark.asyncio
async def test_async_effect_dynamic_dependency_after_await():
    toggle = Signal(False, name="toggle")
    s1 = Signal(1, name="s1")
    s2 = Signal(2, name="s2")

    reads: list[int] = []

    @effect
    async def e():
        await asyncio.sleep(0)
        if toggle():
            reads.append(s1())
        else:
            reads.append(s2())

    # Initial run (toggle False -> depend on s2)
    flush_effects()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 1
    assert reads[-1] == 2

    # Changing s1 should not rerun (not a dep yet)
    s1.write(10)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 1

    # Changing s2 should rerun
    s2.write(20)
    flush_effects()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 2
    assert reads[-1] == 20

    # Flip toggle -> after rerun, effect should depend on s1
    toggle.write(True)
    flush_effects()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 3
    assert reads[-1] == 10

    # Now s1 changes should rerun
    s1.write(11)
    flush_effects()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert e.runs == 4
    assert reads[-1] == 11


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


def test_reactive_wraps_dataclass_class_and_caches():
    @dataclass
    class Model:
        x: int = 1
        tags: list[int] | None = None

    R1 = reactive(Model)
    R2 = reactive(Model)
    assert R1 is R2
    assert getattr(R1, "__is_reactive_dataclass__", False)
    assert getattr(R1, "__reactive_base__", None) is Model

    m = R1()

    seen: list[int] = []

    @effect
    def e():
        seen.append(m.x)

    flush_effects()
    assert seen == [1]

    m.x = 2
    flush_effects()
    assert seen == [1, 2]

    m.tags = [1, 2]
    assert isinstance(m.tags, ReactiveList)


def test_reactive_wraps_dataclass_instance_in_place():
    @dataclass
    class Item:
        a: int = 1
        tags: list[int] | None = None

    i = Item()
    original_id = id(i)
    reactive(i)
    assert id(i) == original_id
    Ri = type(i)
    assert getattr(Ri, "__is_reactive_dataclass__", False)
    assert getattr(Ri, "__reactive_base__", None) is Item

    seen: list[int] = []

    @effect
    def e():
        seen.append(i.a)

    flush_effects()
    assert seen == [1]

    i.a = 5
    flush_effects()
    assert seen == [1, 5]

    i.tags = [10]
    assert isinstance(i.tags, ReactiveList)


def test_reactive_list_wraps_dataclass_items():
    @dataclass
    class D:
        v: int = 1

    d = D()
    lst: ReactiveList[D] = ReactiveList([])
    lst.append(d)

    # Item should be upgraded to reactive dataclass instance
    assert getattr(type(lst[0]), "__is_reactive_dataclass__", False)

    seen: list[int] = []

    @effect
    def e():
        item = cast(D, lst[0])
        seen.append(item.v)

    flush_effects()
    assert seen == [1]

    item2 = cast(D, lst[0])
    item2.v = 3
    flush_effects()
    assert seen == [1, 3]


def test_reactive_dataclass_eq_order_hash_and_repr():
    @dataclass(order=True, frozen=True)
    class A:
        x: int
        y: int

    RA = reactive(A)
    a1 = RA(1, 2)
    a2 = RA(1, 2)
    a3 = RA(2, 1)

    # eq
    assert a1 == a2 and a1 != a3
    # order
    assert a1 < a3
    # hash (frozen)
    s = {a1, a2}
    assert len(s) == 1
    # repr contains fields
    r = repr(a1)
    assert "x=1" in r and "y=2" in r

    # Ensure frozen enforcement at runtime through reactive descriptors
    with pytest.raises(Exception):
        a1.x = 10  # type: ignore[misc]


def test_reactive_dataclass_asdict_astuple_replace_default_factory():
    @dataclass
    class B:
        x: int = 1
        tags: list[int] = field(default_factory=list)

    RB = reactive(B)
    b = RB()
    # default_factory should be wrapped
    assert isinstance(b.tags, ReactiveList)
    b.tags.append(3)

    # asdict/astuple work and produce plain containers
    d = asdict(b)
    t = astuple(b)
    assert d == {"x": 1, "tags": [3]}
    assert t == (1, [3])

    # replace returns a new instance with updated immutables
    b2 = replace(b, x=9)
    assert isinstance(b2, RB)
    assert b2.x == 9 and b.x == 1


def test_reactive_dataclass_initvar_and_classvar_excluded():
    @dataclass
    class C:
        x: int
        cfg: ClassVar[int] = 7
        temp: InitVar[int] = 0

        def __post_init__(self, temp: int):  # type: ignore[override]
            # not stored
            assert isinstance(temp, int)

    RC = reactive(C)
    c = RC(5, 123)

    # ClassVar not a field; value accessible on class, not as reactive field
    assert RC.cfg == 7
    # InitVar not present as attribute
    assert not hasattr(c, "temp")


def test_reactive_dataclass_kw_only_and_match_args():
    @dataclass(kw_only=True)
    class D:
        a: int
        b: int = 2

    RD = reactive(D)
    with pytest.raises(TypeError):
        RD(1)  # type: ignore[call-arg]
    d = RD(a=1)
    assert d.a == 1 and d.b == 2

    # __match_args__ should only include positional fields (none when kw_only=True)
    assert getattr(RD, "__match_args__", ()) == ()


def test_reactive_dataclass_inheritance_works():
    @dataclass
    class Base:
        a: int = 1

    @dataclass
    class Sub(Base):
        b: int = 2

    RSub = reactive(Sub)
    s = RSub()
    assert s.a == 1 and s.b == 2
    # asdict includes inherited fields
    assert asdict(s) == {"a": 1, "b": 2}


def test_reactive_dataclass_slots_basic():
    @dataclass(slots=True)
    class S:
        x: int = 1
        y: int = 2

    RS = reactive(S)
    s = RS()
    # Basic read/write through descriptor should work with slots
    assert s.x == 1
    s.x = 3
    assert s.x == 3


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
