# pyright: reportUnusedFunction=false
from typing import cast

import pulse as ps
import pytest
from pulse import HookContext, Signal
from pulse.reactive import AsyncEffect, Batch, Computed, Effect
from pulse.test_helpers import wait_for


class TestBasicCaching:
	def test_effect_created_once_on_first_render(self):
		effect_instances: list[Effect] = []

		@ps.component
		def Comp():
			@ps.effect
			def my_effect():
				pass

			effect_instances.append(my_effect)
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()
		with ctx:
			Comp.fn()
		with ctx:
			Comp.fn()

		assert len(effect_instances) == 3
		assert effect_instances[0] is effect_instances[1] is effect_instances[2]

	def test_effect_runs_on_first_render(self):
		runs = {"count": 0}

		@ps.component
		def Comp():
			@ps.effect(immediate=True)
			def my_effect():
				runs["count"] += 1

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert runs["count"] == 1

	def test_effect_reruns_on_dependency_change(self):
		runs: list[int] = []
		counter = Signal(0)

		@ps.component
		def Comp():
			@ps.effect(immediate=True)
			def my_effect():
				runs.append(counter())

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert runs == [0]

		with Batch():
			counter.write(1)

		assert runs == [0, 1]

	def test_multiple_effects_in_component(self):
		effects: list[Effect] = []

		@ps.component
		def Comp():
			@ps.effect
			def effect1():
				pass

			@ps.effect
			def effect2():
				pass

			effects.append(effect1)
			effects.append(effect2)
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()
		with ctx:
			Comp.fn()

		# 4 total - 2 effects per render, 2 renders
		assert len(effects) == 4
		# First render's effects
		assert effects[0] is effects[2]  # effect1 same across renders
		assert effects[1] is effects[3]  # effect2 same across renders
		# Different effects within same render
		assert effects[0] is not effects[1]


class TestIdentityAndKeying:
	def test_same_line_different_functions_are_different(self):
		effects: list[Effect] = []

		@ps.component
		def Comp1():
			@ps.effect
			def my_effect():
				pass

			effects.append(my_effect)
			return None

		@ps.component
		def Comp2():
			@ps.effect
			def my_effect():
				pass

			effects.append(my_effect)
			return None

		ctx1 = HookContext()
		ctx2 = HookContext()

		with ctx1:
			Comp1.fn()
		with ctx2:
			Comp2.fn()

		assert len(effects) == 2
		assert effects[0] is not effects[1]

	def test_key_parameter_disambiguates(self):
		effects: list[Effect] = []

		@ps.component
		def Comp():
			for i in range(3):

				@ps.effect(key=str(i))
				def my_effect():
					pass

				effects.append(my_effect)
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert len(effects) == 3
		assert len(set(id(e) for e in effects)) == 3

	def test_helper_callsites_are_distinct(self):
		effects: list[Effect] = []

		def helper():
			@ps.effect
			def my_effect():
				pass

			effects.append(my_effect)

		@ps.component
		def Comp():
			helper()
			helper()
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()
		with ctx:
			Comp.fn()

		assert len(effects) == 4
		assert effects[0] is effects[2]
		assert effects[1] is effects[3]
		assert effects[0] is not effects[1]

	def test_key_change_disposes_old_effect(self):
		disposed = {"count": 0}
		effects: list[Effect] = []
		key_val = Signal("a")

		@ps.component
		def Comp():
			@ps.effect(key=key_val.read(), immediate=True)
			def my_effect():
				def cleanup():
					disposed["count"] += 1

				return cleanup

			effects.append(my_effect)
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert len(effects) == 1
		assert disposed["count"] == 0

		key_val.write("b")
		with ctx:
			Comp.fn()

		assert len(effects) == 2
		assert effects[0] is not effects[1]  # Different effect instance
		assert disposed["count"] == 1  # Old effect was disposed

	def test_key_change_runs_old_cleanup(self):
		cleanup_runs: list[str] = []
		key_val = Signal("a")

		@ps.component
		def Comp():
			current_key = key_val.read()

			@ps.effect(key=current_key, immediate=True)
			def my_effect():
				def cleanup():
					cleanup_runs.append(current_key)

				return cleanup

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert cleanup_runs == []

		key_val.write("b")
		with ctx:
			Comp.fn()

		assert cleanup_runs == ["a"]


class TestLoopDetection:
	def test_duplicate_identity_raises_error(self):
		@ps.component
		def BadComp():
			for _i in range(2):

				@ps.effect
				def my_effect():
					pass

			return None

		ctx = HookContext()
		with pytest.raises(RuntimeError, match="multiple times at the same location"):
			with ctx:
				BadComp.fn()

	def test_duplicate_identity_error_message_helpful(self):
		@ps.component
		def BadComp():
			for _i in range(2):

				@ps.effect
				def my_effect():
					pass

			return None

		ctx = HookContext()
		with pytest.raises(RuntimeError, match=r"key.*parameter"):
			with ctx:
				BadComp.fn()

	def test_loop_with_key_works(self):
		effects: list[Effect] = []

		@ps.component
		def GoodComp():
			for i in range(3):

				@ps.effect(key=str(i))
				def my_effect():
					pass

				effects.append(my_effect)
			return None

		ctx = HookContext()
		with ctx:
			GoodComp.fn()

		assert len(effects) == 3
		assert len(set(id(e) for e in effects)) == 3

	def test_duplicate_detection_resets_between_renders(self):
		runs = {"count": 0}

		@ps.component
		def Comp():
			@ps.effect(immediate=True)
			def my_effect():
				runs["count"] += 1

			return None

		ctx = HookContext()
		# Should not raise - only one call per render
		with ctx:
			Comp.fn()
		with ctx:
			Comp.fn()
		with ctx:
			Comp.fn()

		# Effect only runs once (first render), cached thereafter
		assert runs["count"] == 1


class TestCleanupAndDisposal:
	def test_cleanup_runs_on_dependency_change(self):
		cleanups: list[int] = []
		counter = Signal(0)

		@ps.component
		def Comp():
			@ps.effect(immediate=True)
			def my_effect():
				val = counter()

				def cleanup():
					cleanups.append(val)

				return cleanup

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert cleanups == []

		with Batch():
			counter.write(1)

		assert cleanups == [0]

	def test_cleanup_runs_on_unmount(self):
		cleanups = {"count": 0}

		@ps.component
		def Comp():
			@ps.effect(immediate=True)
			def my_effect():
				def cleanup():
					cleanups["count"] += 1

				return cleanup

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert cleanups["count"] == 0

		ctx.unmount()
		assert cleanups["count"] == 1

	def test_effects_disposed_on_component_unmount(self):
		effects: list[Effect] = []

		@ps.component
		def Comp():
			@ps.effect
			def effect1():
				pass

			@ps.effect
			def effect2():
				pass

			effects.append(effect1)
			effects.append(effect2)
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		ctx.unmount()

		# After unmount, effects should be disposed (deps cleared)
		for e in effects[:2]:
			assert len(e.deps) == 0


class TestContextDetection:
	def test_outside_component_creates_standalone_effect(self):
		@ps.effect
		def standalone():
			pass

		assert isinstance(standalone, Effect)

	def test_module_level_effect_unchanged(self):
		runs = {"count": 0}

		@ps.effect(immediate=True)
		def module_effect():
			runs["count"] += 1

		assert runs["count"] == 1
		assert isinstance(module_effect, Effect)

	def test_state_class_effect_unchanged(self):
		from pulse.state import State, StateEffect

		class MyState(State):
			@ps.effect
			def my_effect(self):
				pass

		# StateEffect is returned for state methods
		# (it gets converted to Effect at state instantiation)
		assert isinstance(MyState.__dict__["my_effect"], StateEffect)


class TestAsyncEffects:
	@pytest.mark.asyncio
	async def test_async_effect_cached(self):
		effect_instances: list[AsyncEffect] = []

		@ps.component
		def Comp():
			@ps.effect
			async def my_effect():
				pass

			effect_instances.append(my_effect)
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()
		with ctx:
			Comp.fn()

		assert len(effect_instances) == 2
		assert effect_instances[0] is effect_instances[1]
		assert isinstance(effect_instances[0], AsyncEffect)

	@pytest.mark.asyncio
	async def test_async_effect_runs_on_first_render(self):
		runs = {"count": 0}

		@ps.component
		def Comp():
			@ps.effect
			async def my_effect():
				runs["count"] += 1

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		# Wait for the async effect to complete
		assert await wait_for(lambda: runs["count"] == 1, timeout=0.2)

	@pytest.mark.asyncio
	async def test_async_cleanup_runs(self):
		cleanups = {"count": 0}
		runs = {"count": 0}
		counter = Signal(0)

		@ps.component
		def Comp():
			@ps.effect
			async def my_effect():
				counter()
				runs["count"] += 1

				def cleanup():
					cleanups["count"] += 1

				return cleanup

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert await wait_for(lambda: runs["count"] == 1, timeout=0.2)
		assert cleanups["count"] == 0

		counter.write(1)
		assert await wait_for(lambda: cleanups["count"] == 1, timeout=0.2)

		assert cleanups["count"] == 1


class TestEffectOptions:
	def test_immediate_effect_runs_synchronously(self):
		runs: list[str] = []

		@ps.component
		def Comp():
			runs.append("before")

			@ps.effect(immediate=True)
			def my_effect():
				runs.append("effect")

			runs.append("after")
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert runs == ["before", "effect", "after"]

	def test_lazy_effect_does_not_autorun(self):
		runs = {"count": 0}

		@ps.component
		def Comp():
			@ps.effect(lazy=True)
			def my_effect():
				runs["count"] += 1

			return my_effect

		ctx = HookContext()
		with ctx:
			effect = cast(Effect, Comp.fn())

		# Lazy effect should not run automatically
		from pulse.reactive import flush_effects

		flush_effects()
		assert runs["count"] == 0

		# But can be run manually
		effect.run()
		assert runs["count"] == 1

	def test_deps_parameter_respected(self):
		runs: list[int] = []
		dep1 = Signal(0)
		dep2 = Signal(100)

		@ps.component
		def Comp():
			@ps.effect(deps=[dep1], immediate=True)
			def my_effect():
				runs.append(dep1() + dep2())

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert runs == [100]

		# Changing dep1 triggers
		with Batch():
			dep1.write(1)
		assert runs == [100, 101]

		# Changing dep2 does NOT trigger (not in deps)
		with Batch():
			dep2.write(200)
		assert runs == [100, 101]

	def test_on_error_handler_works(self):
		errors: list[Exception] = []

		def error_handler(e: Exception):
			errors.append(e)

		@ps.component
		def Comp():
			@ps.effect(on_error=error_handler, immediate=True)
			def my_effect():
				raise ValueError("test error")

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert len(errors) == 1
		assert isinstance(errors[0], ValueError)
		assert str(errors[0]) == "test error"


class TestEdgeCases:
	def test_conditional_effect_first_true(self):
		effects: list[Effect] = []
		flag = Signal(True)

		@ps.component
		def Comp():
			if flag():

				@ps.effect
				def my_effect():
					pass

				effects.append(my_effect)
			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert len(effects) == 1

		# Second render with same flag
		with ctx:
			Comp.fn()

		assert len(effects) == 2
		assert effects[0] is effects[1]

	def test_conditional_effect_disposed_when_condition_becomes_false(self):
		"""When a conditional becomes false, the effect inside should be disposed."""
		cleanups: list[str] = []
		flag = Signal(True)

		@ps.component
		def Comp():
			if flag():

				@ps.effect(immediate=True)
				def my_effect():
					def cleanup():
						cleanups.append("disposed")

					return cleanup

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert cleanups == []  # No cleanup yet

		# Change condition to false
		flag.write(False)
		with ctx:
			Comp.fn()

		# Effect should have been disposed and cleanup should have run
		assert cleanups == ["disposed"]

	def test_conditional_effect_not_triggered_after_disposed(self):
		"""A disposed conditional effect should not run when its dependencies change."""
		runs: list[int] = []
		flag = Signal(True)
		counter = Signal(0)

		@ps.component
		def Comp():
			if flag():

				@ps.effect(immediate=True)
				def my_effect():
					runs.append(counter())

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn()

		assert runs == [0]  # Effect ran once

		# Disable the effect
		flag.write(False)
		with ctx:
			Comp.fn()

		# Change counter - effect should NOT run since it's disposed
		with Batch():
			counter.write(1)

		assert runs == [0]  # Effect did NOT run again

	def test_effect_with_closure_captures_current_values(self):
		captured: list[int] = []

		@ps.component
		def Comp(value: int):
			@ps.effect(immediate=True)
			def my_effect():
				captured.append(value)

			return None

		ctx = HookContext()
		with ctx:
			Comp.fn(1)

		# Effect runs once on first render
		assert captured == [1]

		# On rerender, effect is cached but closure had value=1
		# The effect doesn't rerun because no deps changed
		with ctx:
			Comp.fn(2)

		assert captured == [1]

	def test_nested_component_effects_isolated(self):
		parent_effects: list[Effect] = []
		child_effects: list[Effect] = []

		@ps.component
		def Child():
			@ps.effect
			def child_effect():
				pass

			child_effects.append(child_effect)
			return None

		@ps.component
		def Parent():
			@ps.effect
			def parent_effect():
				pass

			parent_effects.append(parent_effect)
			return None

		parent_ctx = HookContext()
		child_ctx = HookContext()

		# Render parent and child separately (each needs its own HookContext)
		with parent_ctx:
			Parent.fn()
		with child_ctx:
			Child.fn()

		assert len(parent_effects) == 1
		assert len(child_effects) == 1
		assert parent_effects[0] is not child_effects[0]


class TestNoDoubleDispose:
	"""Test that inline effects don't get double-disposed.

	Inline effects are tracked by InlineEffectHookState. They should NOT also
	be tracked as children of the parent render Effect's scope, otherwise
	both disposal paths would run.
	"""

	def test_inline_effect_not_in_parent_scope(self):
		"""Inline effects should not become children of a parent Effect."""
		inline_effect_ref: list[Effect] = []

		@ps.component
		def Comp():
			@ps.effect
			def my_effect():
				pass

			inline_effect_ref.append(my_effect)
			return None

		# Create a parent Effect that renders the component
		ctx = HookContext()
		parent_effect_ref: list[Effect] = []

		def parent_fn():
			with ctx:
				Comp.fn()

		parent_effect = Effect(parent_fn, immediate=True)
		parent_effect_ref.append(parent_effect)

		# The inline effect should NOT be a child of the parent effect
		assert len(inline_effect_ref) == 1
		inline_effect = inline_effect_ref[0]
		assert len(parent_effect.children) == 0, (
			"Inline effects should not be registered as children of parent effects"
		)
		assert inline_effect.parent is None, (
			"Inline effects should not have a parent effect set"
		)

		# Clean up
		ctx.unmount()
		parent_effect.dispose()

	def test_inline_effect_dispose_only_once(self):
		"""Inline effects should be disposed exactly once on unmount."""
		dispose_count = 0

		@ps.component
		def Comp():
			@ps.effect(immediate=True)
			def my_effect():
				def cleanup():
					nonlocal dispose_count
					dispose_count += 1

				return cleanup

			return None

		# Simulate render within a parent Effect (like render Effect does)
		ctx = HookContext()

		def parent_fn():
			with ctx:
				Comp.fn()

		parent_effect = Effect(parent_fn, immediate=True)

		assert dispose_count == 0

		# Dispose both - should not cause double-dispose
		ctx.unmount()
		parent_effect.dispose()

		assert dispose_count == 1, (
			f"Effect cleanup should run exactly once, got {dispose_count}"
		)


class TestComputedInteraction:
	def test_inline_effect_in_computed_still_errors(self):
		"""Inline effects created inside computed should still raise."""
		@ps.component
		def Comp():
			def compute():
				@ps.effect
				def my_effect():
					pass

				return 1

			value = Computed(compute, name="c")
			_ = value()
			return None

		ctx = HookContext()
		with pytest.raises(RuntimeError, match="effect was created within a computed"):
			with ctx:
				Comp.fn()


class TestIntegration:
	def test_effect_with_init_state(self):
		runs: list[int] = []

		@ps.component
		def Comp():
			with ps.init():
				counter = {"value": 0}

			counter["value"] += 1

			@ps.effect(immediate=True)
			def my_effect():
				runs.append(counter["value"])

			return counter["value"]

		ctx = HookContext()
		with ctx:
			result1 = cast(int, Comp.fn())
		with ctx:
			result2 = cast(int, Comp.fn())

		assert result1 == 1
		assert result2 == 2
		# Effect only runs once (first render, cached thereafter)
		assert runs == [1]

	def test_full_component_lifecycle(self):
		events: list[str] = []
		counter = Signal(0)

		@ps.component
		def Comp():
			@ps.effect(immediate=True)
			def my_effect():
				val = counter()
				events.append(f"effect:{val}")

				def cleanup():
					events.append(f"cleanup:{val}")

				return cleanup

			return None

		ctx = HookContext()

		# Mount
		with ctx:
			Comp.fn()
		assert events == ["effect:0"]

		# Update
		with Batch():
			counter.write(1)
		assert events == ["effect:0", "cleanup:0", "effect:1"]

		# Rerender (no change)
		with ctx:
			Comp.fn()
		assert events == ["effect:0", "cleanup:0", "effect:1"]

		# Unmount
		ctx.unmount()
		assert events == ["effect:0", "cleanup:0", "effect:1", "cleanup:1"]
