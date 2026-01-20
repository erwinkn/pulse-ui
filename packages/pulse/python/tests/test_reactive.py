import asyncio
import copy
from dataclasses import InitVar, asdict, astuple, dataclass, field, replace
from typing import Any, ClassVar, NamedTuple, cast

import pulse as ps
import pytest
from pulse import (
	AsyncEffect,
	Computed,
	Effect,
	Signal,
	Untrack,
	computed,
	effect,
	later,
	reactive,
	repeat,
)
from pulse.reactive import Batch, flush_effects
from pulse.reactive_extensions import (
	ReactiveDict,
	ReactiveList,
	ReactiveSet,
	reactive_dataclass,
	unwrap,
)


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


@pytest.mark.asyncio
async def test_later_does_not_track_dependencies():
	"""Test that later() callbacks run with Untrack() and don't create reactive dependencies."""
	s1 = Signal(1, name="s1")
	s2 = Signal(10, name="s2")

	effect_runs = 0
	callback_runs = 0

	def my_effect():
		nonlocal effect_runs
		effect_runs += 1
		# Read s1 to create a dependency
		_ = s1()

		# Schedule later() with a callback that reads s2
		# This should NOT create a dependency on s2 for the effect
		def callback():
			nonlocal callback_runs
			callback_runs += 1
			_ = s2()  # Read s2 inside callback

		later(0.01, callback)

	Effect(my_effect, name="later_effect")
	flush_effects()

	assert effect_runs == 1
	assert callback_runs == 0

	# Wait for callback to execute
	await asyncio.sleep(0.015)
	assert callback_runs == 1

	# Change s2 - should NOT trigger effect rerun
	s2.write(20)
	flush_effects()
	assert effect_runs == 1  # Effect should not rerun

	# Change s1 - should trigger effect rerun
	s1.write(2)
	flush_effects()
	assert effect_runs == 2  # Effect should rerun


@pytest.mark.asyncio
async def test_repeat_does_not_track_dependencies():
	"""Test that repeat() callbacks run with Untrack() and don't create reactive dependencies."""
	s1 = Signal(1, name="s1")
	s2 = Signal(10, name="s2")

	effect_runs = 0
	callback_runs = 0
	handle: Any = None

	def my_effect():
		nonlocal effect_runs, handle
		effect_runs += 1
		# Read s1 to create a dependency
		_ = s1()

		# Schedule repeat() with a callback that reads s2
		# This should NOT create a dependency on s2 for the effect
		# Only create handle once to avoid multiple timers
		if handle is None:

			def callback():
				nonlocal callback_runs
				callback_runs += 1
				_ = s2()  # Read s2 inside callback

			handle = repeat(0.01, callback)

	Effect(my_effect, name="repeat_effect")
	flush_effects()

	assert effect_runs == 1
	assert callback_runs == 0

	# Wait for callback to execute
	await asyncio.sleep(0.015)
	assert callback_runs >= 1

	initial_callback_runs = callback_runs

	# Change s2 - should NOT trigger effect rerun
	s2.write(20)
	flush_effects()
	assert effect_runs == 1  # Effect should not rerun

	# Wait a bit more - callback should continue running
	await asyncio.sleep(0.015)
	assert callback_runs > initial_callback_runs

	# Change s1 - should trigger effect rerun
	s1.write(2)
	flush_effects()
	assert effect_runs == 2  # Effect should rerun

	# Cleanup
	if handle:
		handle.cancel()


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
	c1 = Computed(lambda: s1() if s1() < 10 else c2(), name="c1")  # pyright: ignore[reportUnknownLambdaType]
	c2 = Computed(lambda: c1(), name="c2")  # pyright: ignore[reportUnknownLambdaType]

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
	def e():  # pyright: ignore[reportUnusedFunction]
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


def test_immediate_effect_runs_on_schedule_and_skips_batch():
	s = Signal(0)

	with Batch() as batch:

		@effect(immediate=True)
		def e():
			s()

		# Should have run immediately and not be in the batch
		assert e.runs == 1
		assert e.batch is None
		# And batch should not contain it
		assert e not in batch.effects

	# Exiting batch should not run e again
	assert e.runs == 1


def test_effect_flush_runs_when_scheduled_and_unschedules():
	s = Signal(0)

	@effect
	def e():
		_ = s()

	# Initially scheduled globally; flush effects to bring to first run
	flush_effects()
	assert e.runs == 1

	with Batch() as batch:
		# Write to schedule rerun in this batch
		s.write(1)
		# Verify scheduled
		assert e in batch.effects
		# Now flush the single effect
		e.flush()
		# It should have run immediately and have been removed from batch
		assert e.runs == 2
		assert e not in batch.effects

	# After exiting batch, no extra run should occur
	assert e.runs == 2


@pytest.mark.asyncio
async def test_async_effect_immediate_not_allowed():
	with pytest.raises(ValueError):

		@effect(immediate=True)
		async def e():  # pyright: ignore[reportUnusedFunction]
			await asyncio.sleep(0)


def test_cancel_on_effects():
	@effect
	def sync_e(): ...

	# Sync effect should be instance of Effect (base) and expose cancel
	assert isinstance(sync_e, Effect)
	assert not isinstance(sync_e, AsyncEffect)
	assert hasattr(sync_e, "cancel")
	# Should be safe to call even if not scheduled
	sync_e.cancel()

	@effect(lazy=True)
	async def async_e():
		await asyncio.sleep(0)

	assert isinstance(async_e, AsyncEffect)
	assert hasattr(async_e, "cancel")
	# Should be safe to call even if no task has started yet
	async_e.cancel()


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
		def e2():  # pyright: ignore[reportUnusedFunction]
			...

	flush_effects()
	assert len(e.children) == 1
	child = e.children[0]
	child.dispose()
	assert child.children == []


def test_effect_unregister_from_batch_on_disposal():
	with Batch() as batch:

		@effect
		def e(): ...

		assert batch.effects == [e]
		e.dispose()
		assert batch.effects == []


def test_effect_unset_batch_after_run():
	with Batch() as batch:

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


def test_effect_explicit_deps_disable_tracking():
	a = Signal(0, name="a")
	b = Signal(0, name="b")

	runs = 0

	@effect(deps=[a])
	def e():  # pyright: ignore[reportUnusedFunction]
		nonlocal runs
		runs += 1
		# Read both signals, but only `a` should be tracked
		_ = a()
		_ = b()

	flush_effects()
	assert runs == 1

	b.write(1)
	flush_effects()
	# Should NOT rerun because b is not tracked
	assert runs == 1

	a.write(1)
	flush_effects()
	# Should rerun because a is an explicit dep
	assert runs == 2


def test_effect_explicit_deps_only():
	a = Signal(0, name="a")
	b = Signal(0, name="b")

	@effect(deps=[b])
	def e():
		# Read a dynamically; only b should matter
		_ = a()
		_ = b()

	flush_effects()
	assert e.runs == 1

	a.write(1)
	flush_effects()
	assert e.runs == 1

	b.write(2)
	flush_effects()
	assert e.runs == 2


def test_effect_immediate_false_explicit_deps_registers_on_init():
	"""Test that an effect with immediate=False and explicit deps registers dependencies immediately upon initialization."""
	a = Signal(0, name="a")
	b = Signal(0, name="b")

	@effect(immediate=False, deps=[a, b])
	def e():
		_ = a()
		_ = b()

	# Explicit deps should be registered immediately upon initialization (before first run)
	assert e.runs == 0
	assert a.obs == [e]
	assert b.obs == [e]
	# Explicit deps should be stored in regular deps attribute (not _explicit_deps)
	assert e.update_deps is False
	assert e.deps == {a: a.last_change, b: b.last_change}

	# After first run, deps should still be registered
	flush_effects()
	assert e.runs == 1
	assert e.deps == {a: a.last_change, b: b.last_change}
	assert a.obs == [e]
	assert b.obs == [e]


def test_effect_explicit_deps_doesnt_track_dynamic_deps():
	"""Test that updating an explicit dependency triggers effect execution."""
	a = Signal(0, name="a")
	b = Signal(0, name="b")
	c = Signal(0, name="c")

	runs = 0
	values = []

	@effect(deps=[a, b])
	def e():  # pyright: ignore[reportUnusedFunction]
		nonlocal runs
		runs += 1
		# Read c but it shouldn't be tracked due to explicit deps
		values.append((a(), b(), c()))

	flush_effects()
	assert runs == 1
	assert values == [(0, 0, 0)]

	# Updating c should not trigger effect (not in explicit deps)
	c.write(10)
	flush_effects()
	assert runs == 1
	assert values == [(0, 0, 0)]

	# Updating a should trigger effect
	a.write(1)
	flush_effects()
	assert runs == 2
	assert values == [(0, 0, 0), (1, 0, 10)]

	# Updating b should trigger effect
	b.write(2)
	flush_effects()
	assert runs == 3
	assert values == [(0, 0, 0), (1, 0, 10), (1, 2, 10)]

	# Updating both a and b in batch should trigger once
	with Batch():
		a.write(3)
		b.write(4)
	flush_effects()
	assert runs == 4
	assert values == [(0, 0, 0), (1, 0, 10), (1, 2, 10), (3, 4, 10)]


def test_effect_seeded_deps_update_after_first_run():
	a = Signal(0, name="a")
	b = Signal(0, name="b")
	runs = 0

	@effect(deps=[a], update_deps=True, lazy=True)
	def e():
		nonlocal runs
		runs += 1
		_ = b()

	# Before first run, seeded dep should schedule
	a.write(1)
	flush_effects()
	assert runs == 1
	assert e in b.obs
	assert e not in a.obs

	# After first run, only tracked deps should schedule
	a.write(2)
	flush_effects()
	assert runs == 1

	b.write(3)
	flush_effects()
	assert runs == 2


def test_effect_update_deps_false_keeps_explicit_deps():
	a = Signal(0, name="a")
	b = Signal(0, name="b")

	@effect(deps=[a], update_deps=False)
	def e():
		_ = b()

	flush_effects()
	assert e.deps == {a: a.last_change}
	assert e in a.obs
	assert e not in b.obs

	b.write(1)
	flush_effects()
	assert e.runs == 1

	a.write(1)
	flush_effects()
	assert e.runs == 2


def test_effect_set_deps_dict_respects_last_change():
	s = Signal(0, name="s")

	@effect(lazy=True)
	def e():
		_ = s()

	e.set_deps({s: s.last_change})
	assert e.runs == 0
	flush_effects()
	assert e.runs == 0
	assert e in s.obs

	s.write(1)
	flush_effects()
	assert e.runs == 1


def test_effect_capture_deps_updates_observers():
	a = Signal(0, name="a")
	b = Signal(0, name="b")

	@effect(deps=[a], update_deps=False, lazy=True)
	def e(): ...

	assert e in a.obs
	assert e not in b.obs

	with e.capture_deps():
		_ = b()

	assert e.update_deps is False
	assert e not in a.obs
	assert e in b.obs
	assert e.deps == {b: b.last_change}


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


@pytest.mark.asyncio
async def test_async_effect_seeded_deps_update_after_first_run():
	a = Signal(0, name="a")
	b = Signal(0, name="b")
	runs = 0

	@effect(deps=[a], update_deps=True, lazy=True)
	async def e():
		nonlocal runs
		runs += 1
		_ = b()
		await asyncio.sleep(0)

	a.write(1)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert runs == 1
	assert e in b.obs
	assert e not in a.obs

	a.write(2)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert runs == 1

	b.write(3)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert runs == 2


# TODO: find a way to make this pass. Effect cancellation works in practice.
@pytest.mark.asyncio
async def test_async_effect_cancels_inflight_on_rerun():
	loop = asyncio.get_running_loop()
	gates: list[asyncio.Future[None]] = []
	finished = False

	s = Signal(0, name="s")

	@effect(deps=[s])
	async def e():
		nonlocal finished
		# Each run gets its own gate so cancelling one doesn't affect others
		gate = loop.create_future()
		gates.append(gate)
		await gate
		finished = True

	assert e.deps == {s: s.last_change}

	# Start first run and pause at gate
	initial_task = e._task  # pyright: ignore[reportPrivateUsage]
	assert initial_task is not None, "Effect's task should be set after first run"
	assert not finished, "Effect should not have finished after first run"

	# Let the task actually start running (blocked at gate)
	await asyncio.sleep(0)
	assert len(gates) == 1, "First run should have created a gate"

	# Trigger rerun -> should cancel in-flight task
	s.write(1)
	# Effect restarts immediately, so _task should be a new task
	assert e._task is not None  # pyright: ignore[reportPrivateUsage]
	assert e._task is not initial_task  # pyright: ignore[reportPrivateUsage]
	assert not finished, "Effect should not have finished after signal write"
	await asyncio.sleep(0)
	assert initial_task.cancelled(), (
		"Initial task should be cancelled after signal write"
	)
	assert e._task is not None, "Effect's task should be set after rescheduling"  # pyright: ignore[reportPrivateUsage]
	assert len(gates) == 2, "Second run should have created another gate"

	# Let the effect finish
	gates[1].set_result(None)
	await asyncio.sleep(0)
	assert e._task is None, "Effect's task should be cleared after run"  # pyright: ignore[reportPrivateUsage]
	assert finished, "Effect should have finished after rerun"


@pytest.mark.asyncio
async def test_async_effect_skips_restart_when_task_not_started():
	"""
	When multiple signals change before the task starts executing,
	we should not cancel and recreate the task multiple times.
	"""
	loop = asyncio.get_running_loop()
	gates: list[asyncio.Future[None]] = []
	run_count = 0

	s1 = Signal(0, name="s1")
	s2 = Signal(0, name="s2")

	@effect(deps=[s1, s2])
	async def e():
		nonlocal run_count
		run_count += 1
		gate = loop.create_future()
		gates.append(gate)
		await gate

	initial_task = e._task  # pyright: ignore[reportPrivateUsage]
	assert initial_task is not None
	assert not e._task_started  # pyright: ignore[reportPrivateUsage]

	# Write to both signals before task starts - should not restart
	s1.write(1)
	s2.write(2)

	# Task should still be the same (not cancelled and recreated)
	assert e._task is initial_task  # pyright: ignore[reportPrivateUsage]

	# Let it run
	await asyncio.sleep(0)
	assert len(gates) == 1, "Should only have created one gate (one run)"
	assert run_count == 1

	gates[0].set_result(None)
	await asyncio.sleep(0)
	assert e._task is None  # pyright: ignore[reportPrivateUsage]


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


@pytest.mark.asyncio
async def test_async_effect_retains_dependency_across_cancellations():
	"""If an async effect is cancelled repeatedly before reading a dep,
	it should not lose previously established dependencies.

	Regressions here can cause unkeyed queries to lose their auto-tracked signal
	dependencies when the key changes rapidly.
	"""

	id_sig = Signal(1, name="id_sig")
	churn = Signal(0, name="churn")

	runs: list[int] = []

	@effect
	async def e():
		# Simulate some pre-work before binding dep
		await asyncio.sleep(0)
		await asyncio.sleep(0)
		# Bind dependency late
		runs.append(id_sig())

	# Establish initial dependency by letting first run finish
	flush_effects()
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	await asyncio.sleep(0)
	assert e.runs == 1
	assert runs[-1] == 1

	# Now churn: schedule reruns and cancel them before they read the dep
	for _ in range(5):
		churn.write(churn() + 1)  # schedule rerun
		await asyncio.sleep(0)  # let task start
		# Immediately schedule again to cancel the in-flight run
		churn.write(churn() + 1)
		await asyncio.sleep(0)  # allow cancellation to happen

	# Change the dependency signal -> effect should eventually rerun and read it
	id_sig.write(2)
	await asyncio.sleep(0)  # schedule rerun
	await asyncio.sleep(0)  # run to first await
	await asyncio.sleep(0)  # run to completion
	await asyncio.sleep(0)  # just to be sure
	assert runs[-1] == 2


def test_reactive_dict_basic_reads_and_writes():
	ctx = ReactiveDict({"a": 1})
	reads = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
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
	def e():  # pyright: ignore[reportUnusedFunction]
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


def test_reactive_dict_get_after_delete_uses_default_when_absent():
	ctx = ReactiveDict({"a": 1})

	# Remove key: value signal remains but marks logical absence
	del ctx["a"]

	assert "a" in ctx._signals  # pyright: ignore[reportPrivateUsage]

	# Without default -> None
	assert ctx.get("a") is None

	# With default -> provided default
	assert ctx.get("a", 42) == 42


def test_reactive_dict_get_absent_subscribes_and_updates_on_set():
	ctx = ReactiveDict({})

	reads: list[int] = []

	@effect
	def e():
		reads.append(int(cast(Any, ctx.get("x", 0))))

	flush_effects()
	assert reads == [0]

	# Setting the key should trigger a rerun and pick up the new value
	ctx["x"] = 7
	flush_effects()
	assert reads == [0, 7]

	# Same-value write should not rerun
	runs = e.runs
	ctx["x"] = 7
	flush_effects()
	assert e.runs == runs

	# Deleting should write missing and cause get() to return the default again
	del ctx["x"]
	flush_effects()
	assert reads[-1] == 0


def test_reactive_list_basic_index_reactivity():
	lst = ReactiveList([1, 2, 3])
	assert isinstance(lst, list)

	seen: list[int] = []

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
	first_values: list[int] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
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
		tags: list[int] = None  # pyright: ignore[reportAssignmentType]

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
		{
			"user": {
				"name": "Ada",
				"tags": ["a", "b"],
			}
		}
	)

	# ensure wrapping
	user = ctx["user"]
	assert isinstance(user, ReactiveDict)
	assert isinstance(user["tags"], ReactiveList)

	name_reads: list[str] = []
	v_reads: list[int] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
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


def test_reactive_list_iter_subscribes_to_items_and_structure():
	lst = ReactiveList([1, 2, 3])

	iter_counts: list[int] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
		iter_counts.append(sum(1 for _ in lst))

	flush_effects()
	assert iter_counts == [3]

	# Change a value in place: should rerun since __iter__ subscribes to items
	lst[0] = 10
	flush_effects()
	assert iter_counts == [3, 3]

	# Structural change via append triggers rerun
	lst.append(4)
	flush_effects()
	assert iter_counts[-1] == 4

	# Equal-length slice replacement should rerun (items changed)
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
	def e():  # pyright: ignore[reportUnusedFunction]
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
	def e():  # pyright: ignore[reportUnusedFunction]
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
	def e():  # pyright: ignore[reportUnusedFunction]
		item = lst[0]
		seen.append(item.v)

	flush_effects()
	assert seen == [1]

	item2 = lst[0]
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
	with pytest.raises(AttributeError):
		a1.x = 10  # pyright: ignore[reportAttributeAccessIssue]


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
		RD(1)  # pyright: ignore[reportCallIssue]
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
		items: list[int]
		flags: set[str]
		items = [1, 2]
		flags = {"a"}

	s = S()
	assert isinstance(s.items, ReactiveList)
	assert isinstance(s.flags, ReactiveSet)

	seen = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
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


def test_reactive_dict_len_and_iter_reactivity():
	ctx = ReactiveDict({"a": 1})

	snapshots: list[tuple[int, list[str]]] = []

	@effect
	def e():
		# Depend on structure via len() and iteration
		snapshots.append((len(ctx), list(iter(ctx))))

	flush_effects()
	assert snapshots == [(1, ["a"])]

	# Non-structural value change should not rerun
	runs = e.runs
	ctx["a"] = 10
	flush_effects()
	assert e.runs == runs

	# Structural add triggers rerun
	ctx["b"] = 2
	flush_effects()
	assert snapshots[-1] == (2, ["a", "b"])

	# Structural delete triggers rerun
	del ctx["a"]
	flush_effects()
	assert snapshots[-1] == (1, ["b"])

	# update with new key triggers rerun
	ctx.update({"c": 3})
	flush_effects()
	assert snapshots[-1] == (2, ["b", "c"])

	# clear triggers rerun
	ctx.clear()
	flush_effects()
	assert snapshots[-1] == (0, [])


def test_reactive_dict_contains_reactivity_add_delete():
	ctx = ReactiveDict({})

	checks: list[bool] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
		# Presence check should subscribe to the key's value signal
		checks.append("x" in ctx)

	flush_effects()
	assert checks == [False]

	ctx["x"] = 1
	flush_effects()
	assert checks[-1] is True

	del ctx["x"]
	flush_effects()
	assert checks[-1] is False


def test_reactive_dict_views_and_methods():
	ctx = ReactiveDict({"a": 1, "b": 2})

	lens: list[tuple[int, int, int]] = []

	@effect
	def e():
		# keys/items/values should be reactive to structure
		lens.append((len(ctx.keys()), len(ctx.items()), len(ctx.values())))

	flush_effects()
	assert lens == [(2, 2, 2)]

	# Value-only change should not rerun when depending only on structure/len
	runs = cast(Any, e).runs
	ctx["a"] = 10
	flush_effects()
	assert e.runs == runs

	# pop changes structure
	v = ctx.pop("a")
	assert v == 10
	flush_effects()
	assert lens[-1] == (1, 1, 1)

	# setdefault adds when absent, no-op when present
	v = ctx.setdefault("c", 3)
	assert v == 3 and "c" in ctx
	flush_effects()
	assert lens[-1] == (2, 2, 2)
	v = ctx.setdefault("c", 9)
	assert v == 3
	runs_after = cast(Any, e).runs
	flush_effects()
	assert e.runs == runs_after

	# popitem removes last item
	k, _ = ctx.popitem()
	assert k in ("b", "c")
	flush_effects()
	assert lens[-1] == (1, 1, 1)

	# copy returns ReactiveDict
	cpy = ctx.copy()
	assert isinstance(cpy, ReactiveDict)

	# fromkeys builds a ReactiveDict with given default
	fk = ReactiveDict.fromkeys(["x", "y"], 9)
	assert isinstance(fk, ReactiveDict)
	assert sorted(list(fk)) == ["x", "y"]

	# Union operators
	u = ctx | {"z": 10}
	assert isinstance(u, ReactiveDict) and "z" in u
	ctx |= {"m": 3}
	assert "m" in ctx


def test_reactive_dict_values_reacts_to_value_changes():
	ctx = ReactiveDict({"a": 1, "b": 2})

	sums: list[int] = []

	@effect
	def e():
		# Iterating values should subscribe to each key's value signal
		vals: list[int] = list(ctx.values())
		sums.append(sum(vals))

	flush_effects()
	assert sums == [3]

	# Value-only change should rerun
	ctx["a"] = 5
	flush_effects()
	assert sums == [3, 7]

	# No rerun on same-value write
	runs = e.runs
	ctx["a"] = 5
	flush_effects()
	assert e.runs == runs


def test_reactive_dict_items_reacts_to_value_changes():
	ctx = ReactiveDict({"a": 1, "b": 2})

	snapshots: list[list[tuple[str, int]]] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
		# Iterating items should subscribe to each key's value signal
		snapshots.append(sorted((str(k), int(cast(Any, v))) for k, v in ctx.items()))

	flush_effects()
	assert snapshots[-1] == [("a", 1), ("b", 2)]

	# Value-only change should rerun
	ctx["b"] = 9
	flush_effects()
	assert snapshots[-1] == [("a", 1), ("b", 9)]


def test_reactive_dict_setdefault_absent_subscribes_and_updates_on_write():
	ctx = ReactiveDict({})

	reads: list[int] = []

	@effect
	def e():
		reads.append(int(cast(Any, ctx.setdefault("k", 9))))

	flush_effects()
	assert reads == [9]

	# Changing the value should rerun if setdefault subscribed properly
	ctx["k"] = 10
	flush_effects()
	assert reads == [9, 10]

	# Same-value write should not rerun
	runs = e.runs
	ctx["k"] = 10
	flush_effects()
	assert e.runs == runs


def test_signal_copy_isolated_graph():
	s = Signal({"count": 1})
	tracker = Computed(lambda: s()["count"])
	assert tracker() == 1
	assert tracker in s.obs

	copied = copy.copy(s)

	assert copied is not s
	assert copied.value == s.value
	assert copied.value is s.value
	assert len(copied.obs) == 0
	assert copied.last_change == -1

	s.write({"count": 2})
	assert s() == {"count": 2}
	assert copied.read()["count"] == 1


def test_signal_deepcopy_clones_value_without_dependents():
	s = Signal({"count": 1})
	Computed(lambda: s()["count"])()
	deep_copied = copy.deepcopy(s)

	assert deep_copied is not s
	assert deep_copied.value == s.value
	assert deep_copied.value is not s.value
	assert len(deep_copied.obs) == 0
	assert deep_copied.last_change == -1

	s.write({"count": 5})
	assert deep_copied.read()["count"] == 1


def test_computed_copy_has_fresh_dependency_graph():
	source = Signal(1)
	comp = Computed(lambda: source() + 1)
	assert comp() == 2
	assert source in comp.deps

	copied = copy.copy(comp)
	assert copied is not comp
	assert copied.deps == {}
	assert copied.obs == []

	assert copied() == 2
	assert source in copied.deps
	assert copied.deps is not comp.deps

	source.write(5)
	assert comp() == 6
	assert copied() == 6


def test_computed_deepcopy_is_independent():
	source = Signal(10)
	comp = Computed(lambda: source() * 2)
	assert comp() == 20

	deep_copied = copy.deepcopy(comp)
	assert deep_copied is not comp
	assert deep_copied.deps == {}
	assert deep_copied.obs == []
	assert deep_copied() == 20

	source.write(15)
	assert comp() == 30
	assert deep_copied() == 30


def test_effect_copy_and_deepcopy_create_new_effects():
	signal = Signal(0)

	def runner(label: str):
		def _run():
			signal()
			return None

		_run.__name__ = f"runner_{label}"
		return _run

	original = Effect(runner("original"))
	copied = copy.copy(original)
	deep_copied = copy.deepcopy(original)

	flush_effects()

	assert original.runs == 1
	assert copied.runs == 1
	assert deep_copied.runs == 1
	assert original.deps is not copied.deps
	assert original.deps is not deep_copied.deps

	signal.write(1)
	flush_effects()
	assert original.runs == 2
	assert copied.runs == 2
	assert deep_copied.runs == 2

	original.dispose()
	copied.dispose()
	deep_copied.dispose()


def test_effect_copy_preserves_lazy_flag():
	signal = Signal(0)
	calls: list[str] = []

	def run(label: str):
		def _run():
			calls.append(label)
			signal()
			return None

		_run.__name__ = f"lazy_{label}"
		return _run

	lazy = Effect(run("orig"), lazy=True)
	lazy_copy = copy.copy(lazy)
	lazy_deep = copy.deepcopy(lazy)

	flush_effects()
	assert lazy.runs == 0
	assert lazy_copy.runs == 0
	assert lazy_deep.runs == 0

	lazy.schedule()
	lazy_copy.schedule()
	lazy_deep.schedule()
	flush_effects()

	assert lazy.runs == 1
	assert lazy_copy.runs == 1
	assert lazy_deep.runs == 1
	assert calls == ["orig", "orig", "orig"]

	lazy.dispose()
	lazy_copy.dispose()
	lazy_deep.dispose()


def test_reactive_dict_copy_uses_new_signals():
	ctx = ReactiveDict({"a": 1})
	copied = copy.copy(ctx)

	assert copied is not ctx
	assert copied._signals != ctx._signals  # pyright: ignore[reportPrivateUsage]
	assert copied._signals["a"] is not ctx._signals["a"]  # pyright: ignore[reportPrivateUsage]
	assert copied._structure is not ctx._structure  # pyright: ignore[reportPrivateUsage]

	ctx["a"] = 2
	assert copied["a"] == 1
	copied["a"] = 3
	assert ctx["a"] == 2


def test_reactive_dict_deepcopy_clones_nested_values():
	ctx = ReactiveDict({"a": {"x": 1}})
	deep_copied = copy.deepcopy(ctx)

	assert deep_copied is not ctx
	assert deep_copied._signals["a"] is not ctx._signals["a"]  # pyright: ignore[reportPrivateUsage]

	original_nested = ctx["a"]
	copied_nested = deep_copied["a"]
	assert isinstance(original_nested, ReactiveDict)
	assert isinstance(copied_nested, ReactiveDict)
	assert copied_nested is not original_nested
	assert copied_nested.unwrap() == {"x": 1}

	original_nested["x"] = 9
	assert copied_nested.unwrap() == {"x": 1}


def test_reactive_list_copy_and_deepcopy_use_new_signals():
	items = ReactiveList([1, {"nested": 2}])
	copied = copy.copy(items)
	deep_copied = copy.deepcopy(items)

	assert copied is not items
	assert deep_copied is not items
	assert copied._signals[0] is not items._signals[0]  # pyright: ignore[reportPrivateUsage]
	assert deep_copied._signals[0] is not items._signals[0]  # pyright: ignore[reportPrivateUsage]

	items[0] = 5
	assert copied[0] == 1
	assert deep_copied[0] == 1

	nested_original = items[1]
	nested_copy = copied[1]
	nested_deep = deep_copied[1]
	assert isinstance(nested_copy, dict)
	assert isinstance(nested_deep, dict)
	assert isinstance(nested_original, dict)
	nested_original["nested"] = 7
	assert nested_copy["nested"] == 2
	assert nested_deep["nested"] == 2


def test_reactive_set_copy_and_deepcopy_use_new_signals():
	values = ReactiveSet({1, 2})
	copied = copy.copy(values)
	deep_copied = copy.deepcopy(values)

	assert copied is not values
	assert deep_copied is not values
	assert copied._signals is not values._signals  # pyright: ignore[reportPrivateUsage]
	assert deep_copied._signals is not values._signals  # pyright: ignore[reportPrivateUsage]

	values.add(3)
	assert 3 not in copied
	assert 3 not in deep_copied

	copied.add(4)
	deep_copied.add(5)
	assert 4 not in values
	assert 5 not in values


def test_computed_exception_does_not_cause_circular_dependency():
	"""Test that exceptions in computed properties don't cause circular dependency errors."""
	s = Signal(10, name="s")

	def failing_computed():
		if s() > 5:
			raise ValueError("Computed failed")
		return s() * 2

	c = Computed(failing_computed, name="c")

	# First access should raise the original exception
	with pytest.raises(ValueError, match="Computed failed"):
		c()

	# Subsequent accesses should still raise the original exception, not circular dependency
	with pytest.raises(ValueError, match="Computed failed"):
		c()

	# After fixing the condition, it should work
	s.write(3)
	assert c() == 6


def test_computed_with_previous_value_parameter():
	"""Test that computed functions can optionally receive the previous value."""
	s = Signal(1, name="s")

	prev_values: list[int | None] = []

	def computed_with_prev(prev: int | None) -> int:
		prev_values.append(prev)
		return s() * 2

	c = Computed(computed_with_prev, name="c")

	# First access: prev should be None (initial value)
	assert c() == 2
	assert prev_values == [None]

	# Second access: prev should be 2
	s.write(2)
	assert c() == 4
	assert prev_values == [None, 2]

	# Third access: prev should be 4
	s.write(3)
	assert c() == 6
	assert prev_values == [None, 2, 4]


def test_computed_with_previous_value_parameter_first_run():
	"""Test that computed receives None on first run when it accepts previous value."""
	s = Signal(10, name="s")

	first_prev: int | None = None

	def computed_with_prev(prev: int | None) -> int:
		nonlocal first_prev
		if first_prev is None:
			first_prev = prev
		return s() * 2

	c = Computed(computed_with_prev, name="c")

	# First access
	result = c()
	assert result == 20
	assert first_prev is None


def test_computed_without_previous_value_parameter():
	"""Test that computed functions without parameters still work normally."""
	s = Signal(5, name="s")

	def computed_no_params():
		return s() * 3

	c = Computed(computed_no_params, name="c")

	assert c() == 15
	s.write(10)
	assert c() == 30


def test_computed_previous_value_with_computed_chain():
	"""Test previous value parameter works in computed chains."""
	s = Signal(1, name="s")

	prev_values_c1: list[int | None] = []
	prev_values_c2: list[int | None] = []

	def c1_fn(prev: int | None) -> int:
		prev_values_c1.append(prev)
		return s() * 2

	def c2_fn(prev: int | None) -> int:
		prev_values_c2.append(prev)
		return c1() * 2

	c1 = Computed(c1_fn, name="c1")
	c2 = Computed(c2_fn, name="c2")

	# First access
	assert c2() == 4
	assert prev_values_c1 == [None]
	assert prev_values_c2 == [None]

	# Second access
	s.write(2)
	assert c2() == 8
	assert prev_values_c1 == [None, 2]
	assert prev_values_c2 == [None, 4]


def test_computed_previous_value_with_dynamic_dependencies():
	"""Test previous value parameter works with dynamic dependencies."""
	s1 = Signal(10, name="s1")
	s2 = Signal(20, name="s2")
	toggle = Signal(True, name="toggle")

	prev_values: list[int | None] = []

	def c_fn(prev: int | None) -> int:
		prev_values.append(prev)
		return s1() if toggle() else s2()

	c = Computed(c_fn, name="c")

	# First access
	assert c() == 10
	assert prev_values == [None]

	# Change toggle - should see previous value
	toggle.write(False)
	assert c() == 20
	assert prev_values == [None, 10]

	# Change s2 - should see previous value
	s2.write(30)
	assert c() == 30
	assert prev_values == [None, 10, 20]


@pytest.mark.asyncio
async def test_async_effect_skips_batch():
	s = Signal(0)
	runs = 0

	@effect
	async def e():
		nonlocal runs
		runs += 1
		s()
		await asyncio.sleep(0)

	# Starts immediately
	assert e.runs == 0  # Task created but not run yet
	await asyncio.sleep(0.01)
	assert e.runs == 1

	# Update inside batch
	with Batch() as batch:
		s.write(1)
		# AsyncEffect should ignore batch and run immediately (task created)
		assert e not in batch.effects
		assert e.runs == 1  # Task created, not run yet
		await asyncio.sleep(0.01)
		assert e.runs == 2

	# Exiting batch does nothing extra
	await asyncio.sleep(0.01)
	assert e.runs == 2


@pytest.mark.asyncio
async def test_async_effect_await_run():
	s = Signal(0)
	finished = False

	@effect(lazy=True)
	async def e():
		nonlocal finished
		s()
		await asyncio.sleep(0.01)
		finished = True

	# Run and await
	await e.run()
	assert finished
	assert e.runs == 1


@pytest.mark.asyncio
async def test_async_effect_await_call():
	s = Signal(0)
	finished = False

	@effect(lazy=True)
	async def e():
		nonlocal finished
		s()
		await asyncio.sleep(0.01)
		finished = True

	# Call and await
	await e()
	assert finished
	assert e.runs == 1


@pytest.mark.asyncio
async def test_async_effect_copy_and_deepcopy():
	s = Signal(0)

	async def fn():
		s()

	e = AsyncEffect(fn, name="test")

	# Copy
	e_copy = copy.copy(e)
	assert isinstance(e_copy, AsyncEffect)
	assert e_copy.name == "test"
	# It starts immediately, so it might have a task
	assert e_copy._task is not None  # pyright: ignore[reportPrivateUsage]
	assert e_copy._task is not e._task  # pyright: ignore[reportPrivateUsage]
	assert e_copy is not e

	# Deepcopy
	e_deep = copy.deepcopy(e)
	assert isinstance(e_deep, AsyncEffect)
	assert e_deep.name == "test"
	assert e_deep._task is not None  # pyright: ignore[reportPrivateUsage]
	assert e_deep._task is not e._task  # pyright: ignore[reportPrivateUsage]
	assert e_deep is not e

	e.dispose()
	e_copy.dispose()
	e_deep.dispose()


@pytest.mark.asyncio
async def test_async_effect_wait_does_not_start_task_if_not_running():
	finished = False

	@effect(lazy=True)
	async def e():
		nonlocal finished
		await asyncio.sleep(0.01)
		finished = True

	# No task running initially
	assert e._task is None  # pyright: ignore[reportPrivateUsage]

	# Wait should NOT start a task if none is running
	await e.wait()
	assert not finished
	assert e.runs == 0
	assert e._task is None  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_async_effect_wait_waits_for_existing_task():
	loop = asyncio.get_running_loop()
	gate: asyncio.Future[None] = loop.create_future()
	finished = False

	@effect(lazy=True)
	async def e():
		nonlocal finished
		await gate
		finished = True

	# Start the task
	e.run()
	assert e.is_scheduled is True
	assert not finished

	# Wait should wait for the existing task
	wait_task = asyncio.create_task(e.wait())
	await asyncio.sleep(0)  # Let wait start

	# Release the gate
	gate.set_result(None)
	await wait_task

	assert finished
	assert e.runs == 1
	assert e.is_scheduled is False


@pytest.mark.asyncio
async def test_async_effect_wait_handles_cancellation():
	started = 0
	finished = 0

	def on_error(e: Exception):
		raise e

	@effect(lazy=True, on_error=on_error)
	async def e():
		nonlocal started
		nonlocal finished
		started += 1
		await asyncio.sleep(0.01)
		finished += 1

	# Start first run. Won't finish until we execute two awaits.
	e.run()
	assert e.is_scheduled is True
	await asyncio.sleep(0)  # Let effect start
	assert started == 1
	assert finished == 0

	# Start waiting
	wait_task = asyncio.create_task(e.wait())
	await asyncio.sleep(0)
	assert started == 1
	assert finished == 0

	e.run()
	await asyncio.sleep(0)

	assert started == 2
	assert finished == 0
	assert not wait_task.cancelled()

	await wait_task

	assert started == 2
	assert finished == 1
	assert e.runs == 1
	assert e.is_scheduled is False


@pytest.mark.asyncio
async def test_async_effect_wait_handles_multiple_cancellations():
	started = 0
	finished = 0

	def on_error(e: Exception):
		raise e

	@effect(lazy=True, on_error=on_error)
	async def e():
		nonlocal started, finished
		started += 1
		await asyncio.sleep(0.01)
		finished += 1

	# Start first run
	e.run()
	await asyncio.sleep(0)  # Let effect start
	assert started == 1
	assert finished == 0

	# Start waiting
	wait_task = asyncio.create_task(e.wait())
	await asyncio.sleep(0)

	# Cancel and restart multiple times
	for _ in range(2):
		e.run()
		await asyncio.sleep(0)

	# Final run should complete
	await wait_task

	assert started == 3
	assert finished == 1
	assert e.runs == 1  # Only the final run completes
	assert e.is_scheduled is False


@pytest.mark.asyncio
async def test_async_effect_wait_after_completion():
	started = 0
	finished = 0

	def on_error(e: Exception):
		raise e

	@effect(lazy=True, on_error=on_error)
	async def e():
		nonlocal started, finished
		started += 1
		await asyncio.sleep(0.01)
		finished += 1

	# Run and complete
	await e.run()
	assert started == 1
	assert finished == 1
	assert e.is_scheduled is False

	# Wait after completion should NOT start a new run
	await e.wait()
	assert started == 1
	assert finished == 1
	assert e.runs == 1
	assert e.is_scheduled is False


def test_effect_explicit_deps_rerun_on_internal_modification():
	"""
	Test that if a synchronous effect modifies one of its explicit dependencies,
	it re-runs. This happens because we capture the dependency version
	at the *start* of execution. Since the version changes during execution,
	at the end the dependency is considered changed relative to the start.
	"""
	count = Signal(0, name="count")
	runs = 0

	@effect(deps=[count])
	def e():  # pyright: ignore[reportUnusedFunction]
		nonlocal runs
		runs += 1
		if count() < 2:
			count.write(count() + 1)

	flush_effects()
	# Run 1: sees count=0. writes count=1.
	# End of Run 1: deps updated to what they were at START (count=0).
	# Check: count=1 > last_seen=0 -> Rerun.

	# Run 2: sees count=1. writes count=2.
	# End of Run 2: deps updated to what they were at START (count=1).
	# Check: count=2 > last_seen=1 -> Rerun.

	# Run 3: sees count=2. No write.
	# End of Run 3: deps updated to what they were at START (count=2).
	# Check: count=2 == last_seen=2 -> Done.

	assert runs == 3
	assert count() == 2


@pytest.mark.asyncio
async def test_async_effect_explicit_deps_rerun_on_external_modification_during_run():
	"""
	Test that if an async effect's explicit dependency changes while the effect
	is awaiting, the effect re-runs.
	"""
	s = Signal(0, name="s")

	@effect(deps=[s])
	async def e():
		await asyncio.sleep(0.01)

	# Allow effect to start
	await asyncio.sleep(0)
	assert e.runs == 0

	# Modify s while e is running/awaiting
	s.write(1)
	assert e.runs == 0

	# Allow effect to finish its first run
	await asyncio.sleep(0.015)
	assert e.runs == 1

	s.write(2)
	await asyncio.sleep(0.015)
	assert e.runs == 2


def test_unwrap_preserves_namedtuple_type():
	"""unwrap should preserve namedtuple types, not convert them to plain tuples."""

	class Point(NamedTuple):
		x: int
		y: int

	p = Point(1, 2)

	result = unwrap(p)

	assert type(result) is Point
	assert result.x == 1
	assert result.y == 2


def test_reactive_list_iteration_subscribes_to_items():
	"""Iterating a ReactiveList should subscribe to each item's signal."""
	rl = ReactiveList([1, 2, 3])
	results: list[list[int]] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
		results.append(list[int](rl))

	flush_effects()
	assert results == [[1, 2, 3]]

	# Mutating an item should trigger the effect
	rl[1] = 99
	flush_effects()
	assert results == [[1, 2, 3], [1, 99, 3]]


def test_reactive_set_iteration_subscribes_to_membership():
	"""Iterating a ReactiveSet should subscribe to membership signals."""
	rs = ReactiveSet([1, 2, 3])
	results: list[set[int]] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
		collected = set[int]()
		for item in rs:
			collected.add(item)
		results.append(collected)

	flush_effects()
	assert results == [{1, 2, 3}]

	# Removing an item should trigger the effect
	rs.discard(2)
	flush_effects()
	assert results == [{1, 2, 3}, {1, 3}]


def test_reactive_dict_items_subscribes_to_values():
	"""Iterating d.items() should subscribe to value signals."""
	rd = ReactiveDict({"a": 1, "b": 2})
	results: list[dict[str, int]] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
		results.append(dict(rd.items()))

	flush_effects()
	assert results == [{"a": 1, "b": 2}]

	# Changing a value should trigger the effect
	rd["a"] = 99
	flush_effects()
	assert results == [{"a": 1, "b": 2}, {"a": 99, "b": 2}]


def test_reactive_dict_values_subscribes_to_values():
	"""Iterating d.values() should subscribe to value signals."""
	rd = ReactiveDict({"a": 1, "b": 2})
	results: list[list[int]] = []

	@effect
	def e():  # pyright: ignore[reportUnusedFunction]
		results.append(list(rd.values()))

	flush_effects()
	assert results == [[1, 2]]

	# Changing a value should trigger the effect
	rd["a"] = 99
	flush_effects()
	assert results == [[1, 2], [99, 2]]


# ---------------------- Effect Interval Tests ----------------------


@pytest.mark.asyncio
async def test_effect_interval_runs_periodically():
	"""Test that an effect with interval runs periodically."""
	runs: list[int] = []

	@effect(interval=0.01)
	def e():
		runs.append(len(runs))

	flush_effects()
	assert len(runs) == 1

	# Wait for interval to trigger (just over 1 interval, under 2)
	await asyncio.sleep(0.012)
	assert len(runs) == 2

	# Wait for another interval
	await asyncio.sleep(0.012)
	assert len(runs) == 3

	e.dispose()


@pytest.mark.asyncio
async def test_effect_cancel_with_cancel_interval_true():
	"""Test that cancel(cancel_interval=True) stops the interval."""
	runs: list[int] = []

	@effect(interval=0.01)
	def e():
		runs.append(len(runs))

	flush_effects()
	assert len(runs) == 1

	# Cancel with interval cancellation (default)
	e.cancel(cancel_interval=True)
	assert e._interval_handle is None  # pyright: ignore[reportPrivateUsage]

	# Wait - interval should not trigger
	await asyncio.sleep(0.015)
	flush_effects()
	assert len(runs) == 1

	e.dispose()


@pytest.mark.asyncio
async def test_effect_cancel_with_cancel_interval_false():
	"""Test that cancel(cancel_interval=False) preserves the interval."""
	runs: list[int] = []

	@effect(interval=0.01)
	def e():
		runs.append(len(runs))

	flush_effects()
	assert len(runs) == 1
	assert e._interval_handle is not None  # pyright: ignore[reportPrivateUsage]

	# Cancel without interval cancellation
	e.cancel(cancel_interval=False)
	# Interval handle should still exist
	assert e._interval_handle is not None  # pyright: ignore[reportPrivateUsage]

	# Wait - interval should still trigger
	await asyncio.sleep(0.015)
	flush_effects()
	assert len(runs) == 2

	e.dispose()


@pytest.mark.asyncio
async def test_effect_run_restarts_cancelled_interval():
	"""Test that running an effect restarts a cancelled interval."""
	runs: list[int] = []

	@effect(interval=0.01)
	def e():
		runs.append(len(runs))

	flush_effects()
	assert len(runs) == 1

	# Cancel with interval cancellation
	e.cancel(cancel_interval=True)
	assert e._interval_handle is None  # pyright: ignore[reportPrivateUsage]

	# Manually run the effect - should restart interval
	e.run()
	assert len(runs) == 2
	assert e._interval_handle is not None  # pyright: ignore[reportPrivateUsage]

	# Wait - interval should trigger again
	await asyncio.sleep(0.015)
	flush_effects()
	assert len(runs) == 3

	e.dispose()


@pytest.mark.asyncio
async def test_async_effect_interval_runs_periodically():
	"""Test that an async effect with interval runs periodically."""
	runs: list[int] = []

	@effect(interval=0.01, lazy=True)
	async def e():
		runs.append(len(runs))
		await asyncio.sleep(0)

	# Start the effect
	await e.run()
	assert len(runs) == 1

	# Wait for interval to trigger (just over 1 interval, under 2)
	await asyncio.sleep(0.012)
	await e.wait()
	assert len(runs) == 2

	# Wait for another interval
	await asyncio.sleep(0.012)
	await e.wait()
	assert len(runs) == 3

	e.dispose()


@pytest.mark.asyncio
async def test_async_effect_cancel_with_cancel_interval_true():
	"""Test that async cancel(cancel_interval=True) stops the interval."""
	runs: list[int] = []

	@effect(interval=0.01, lazy=True)
	async def e():
		runs.append(len(runs))
		await asyncio.sleep(0)

	await e.run()
	assert len(runs) == 1

	# Cancel with interval cancellation (default)
	e.cancel(cancel_interval=True)
	assert e._interval_handle is None  # pyright: ignore[reportPrivateUsage]

	# Wait - interval should not trigger
	await asyncio.sleep(0.015)
	assert len(runs) == 1

	e.dispose()


@pytest.mark.asyncio
async def test_async_effect_cancel_with_cancel_interval_false():
	"""Test that async cancel(cancel_interval=False) preserves the interval."""
	runs: list[int] = []

	@effect(interval=0.01, lazy=True)
	async def e():
		runs.append(len(runs))
		await asyncio.sleep(0)

	await e.run()
	assert len(runs) == 1
	assert e._interval_handle is not None  # pyright: ignore[reportPrivateUsage]

	# Cancel without interval cancellation
	e.cancel(cancel_interval=False)
	# Interval handle should still exist
	assert e._interval_handle is not None  # pyright: ignore[reportPrivateUsage]

	# Wait - interval should still trigger
	await asyncio.sleep(0.015)
	await e.wait()
	assert len(runs) == 2

	e.dispose()


@pytest.mark.asyncio
async def test_async_effect_run_restarts_cancelled_interval():
	"""Test that running an async effect restarts a cancelled interval."""
	runs: list[int] = []

	@effect(interval=0.01, lazy=True)
	async def e():
		runs.append(len(runs))
		await asyncio.sleep(0)

	await e.run()
	assert len(runs) == 1

	# Cancel with interval cancellation
	e.cancel(cancel_interval=True)
	assert e._interval_handle is None  # pyright: ignore[reportPrivateUsage]

	# Manually run the effect - should restart interval
	await e.run()
	assert len(runs) == 2
	assert e._interval_handle is not None  # pyright: ignore[reportPrivateUsage]

	# Wait - interval should trigger again
	await asyncio.sleep(0.015)
	await e.wait()
	assert len(runs) == 3

	e.dispose()
