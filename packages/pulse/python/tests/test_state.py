"""
Tests for the State class and computed properties.
"""

from typing import Any, TypeVar, cast, override

import pulse as ps
import pytest
from pulse.reactive import flush_effects
from pulse.reactive_extensions import ReactiveDict, ReactiveList, ReactiveSet, unwrap
from pulse.state import StateFieldKind

TState = TypeVar("TState", bound=ps.State)


def hydrate_new(cls: type[TState], payload: dict[str, Any]) -> TState:
	instance = cls.__new__(cls)
	return instance.hydrate(payload)


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
			count: int
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
			custom: bool

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
			count: int
			count = 1

		class Child(Base):
			count: int
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
			count: int
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
			data: dict[str, Any]
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
		def track():  # pyright: ignore[reportUnusedFunction]
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
			match=r"Strict mode forbids setting undeclared attribute 'dynamic_prop'",
		):
			state.dynamic_prop = "should fail"

	def test_strict_mode_blocks_undeclared_private_attributes(self):
		"""Strict mode should reject undeclared private attribute assignments"""

		class MyState(ps.State):
			count: int = 0

		state = MyState()

		with pytest.raises(
			AttributeError, match=r"Strict mode forbids setting undeclared attribute"
		):
			state._private = "ok"
		with pytest.raises(
			AttributeError, match=r"Strict mode forbids setting undeclared attribute"
		):
			state.__very_private = "also ok"
		with pytest.raises(
			AttributeError, match=r"Strict mode forbids setting undeclared attribute"
		):
			state._internal_counter = 42

	def test_non_strict_mode_allows_private_attributes(self):
		"""Non-strict mode retains permissive private attribute behavior"""

		class MyState(ps.State):
			count: int = 0

		app = ps.App(strict=False)
		with ps.PulseContext(app=app):
			state = MyState()
			state._private = "ok"
			state.__very_private = "also ok"
			state._internal_counter = 42

			assert state._private == "ok"  # pyright: ignore[reportAttributeAccessIssue]
			assert state.__very_private == "also ok"  # pyright: ignore[reportAttributeAccessIssue]
			assert state._internal_counter == 42  # pyright: ignore[reportAttributeAccessIssue]

	def test_special_state_attributes_allowed(self):
		"""Test that special State attributes can be set"""

		class MyState(ps.State):
			count: int = 0

		state = MyState()

		# These special attributes should be allowed
		from pulse.reactive import Scope

		new_scope = Scope()
		state._scope = new_scope  # pyright: ignore[reportPrivateUsage]
		assert state._scope is new_scope  # pyright: ignore[reportPrivateUsage]

	def test_assignment_to_private_property(self):
		"""Test that properties can be assigned during custom __init__ before full initialization"""

		class MyState(ps.State):
			count: int = 0
			_private: str

			def __init__(self):
				# This should work - we're not fully initialized yet
				self._private = "private"

		state = MyState()
		assert state._private == "private"  # pyright: ignore[reportPrivateUsage]
		state._private = "updated"  # pyright: ignore[reportPrivateUsage]
		assert state._private == "updated"  # pyright: ignore[reportPrivateUsage]

	def test_undeclared_private_attribute_disallowed_in_init(self):
		class BadPrivate(ps.State):
			def __init__(self):
				self._temp: str = "nope"

		with pytest.raises(
			AttributeError,
			match=r"Strict mode forbids setting undeclared attribute '_temp'",
		):
			BadPrivate()

	def test_post_init_allows_declared_private_attribute(self):
		class GoodPrivate(ps.State):
			_temp: str

			def __post_init__(self):
				self._temp = "ok"

		state = GoodPrivate()
		assert state._temp == "ok"  # pyright: ignore[reportPrivateUsage]

	def test_strict_mode_blocks_post_init_undeclared_private(self):
		class BadPrivate(ps.State):
			def __post_init__(self):
				self._temp: str = "nope"

		with pytest.raises(
			AttributeError, match=r"Strict mode forbids setting undeclared attribute"
		):
			BadPrivate()

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

		with pytest.raises(AttributeError) as excinfo:
			state.user_name = "john"

		error_msg = str(excinfo.value)
		assert "Strict mode forbids setting undeclared attribute" in error_msg
		assert "MyState" in error_msg
		assert "App(strict=False)" in error_msg

	def test_helpful_error_message_non_strict_mode(self):
		class MyState(ps.State):
			count: int = 0

		app = ps.App(strict=False)
		with ps.PulseContext(app=app):
			state = MyState()
			with pytest.raises(AttributeError) as excinfo:
				state.user_name = "john"

		error_msg = str(excinfo.value)
		assert "Cannot set non-reactive property 'user_name'" in error_msg
		assert "declare it with a type annotation at the class level" in error_msg

	def test_strict_mode_enforces_picklable_values(self):
		class MyState(ps.State):
			count: int = 0

		state = MyState()
		with open(__file__, "rb") as handle:
			with pytest.raises(TypeError, match=r"cloudpickle-serializable"):
				state.count = handle  # pyright: ignore[reportAttributeAccessIssue]

	def test_non_strict_allows_non_picklable_values(self):
		class MyState(ps.State):
			count: int = 0

		app = ps.App(strict=False)
		with ps.PulseContext(app=app):
			state = MyState()
			with open(__file__, "rb") as handle:
				state.count = handle  # pyright: ignore[reportAttributeAccessIssue]
				assert state.count is handle

	def test_effects_dont_run_during_initialization(self):
		"""Test that effects don't trigger during State initialization"""

		effect_runs = []

		class MyState(ps.State):
			count: int = 5
			name: str

			def __init__(self, name: str):
				self.name = name

			@ps.effect
			def track_count(self):
				effect_runs.append(f"count={self.count}")

			@ps.effect
			def track_name(self):
				effect_runs.append(f"name={self.name}")

		# During initialization, effects should not run even though
		# reactive properties get their initial values
		state = MyState("initial")
		# Verify no epoch bump from reactive writes during __init__
		assert effect_runs == [], f"Effects ran during initialization: {effect_runs}"

		# But effects should run when we manually schedule them
		state.track_count.schedule()
		state.track_name.schedule()
		flush_effects()
		assert len(effect_runs) == 2  # pyright: ignore[reportUnknownArgumentType]
		assert "count=5" in effect_runs
		assert "name=initial" in effect_runs

		# And effects should run when properties change
		effect_runs.clear()
		state.count = 10
		flush_effects()
		assert "count=10" in effect_runs

		effect_runs.clear()
		state.name = "updated"
		flush_effects()
		assert "name=updated" in effect_runs

	def test_underscore_annotated_properties_are_non_reactive(self):
		class S(ps.State):
			_x: int = 1
			y: int = 2

			@ps.computed
			def total(self):
				# If _x were reactive, changing it would invalidate this computed.
				return self._x + self.y

		s = S()

		# _x should not appear in reactive properties
		prop_names = {str(sig.name).split(".", 1)[1] for sig in s.properties()}
		assert "_x" not in prop_names
		assert "y" in prop_names

		# Initial computed
		assert s.total == 3

		# Changing non-reactive underscore property should not invalidate computed
		s._x = 10  # pyright: ignore[reportPrivateUsage]
		assert s.total == 3

		# Changing reactive property should invalidate and recompute
		s.y = 3
		assert s.total == 13

	def test_underscore_unannotated_properties_are_non_reactive(self):
		class S(ps.State):
			_data: dict[str, int]
			_data = {"a": 1}
			value: int = 1

			@ps.computed
			def view(self):
				# Access underscore field to ensure it doesn't become reactive
				return self._data["a"] + self.value

		s = S()

		# _data should not be wrapped in a ReactiveDict
		assert not isinstance(s._data, ReactiveDict)  # pyright: ignore[reportPrivateUsage]

		# Changing underscore data should not affect computed caching
		assert s.view == 2
		s._data["a"] = 5  # pyright: ignore[reportPrivateUsage]
		assert s.view == 2

		# Changing reactive property should recompute
		s.value = 2
		assert s.view == 7

	def test_computed_exception_does_not_cause_circular_dependency(self):
		"""Test that exceptions in computed properties don't cause circular dependency errors."""

		class TestState(ps.State):
			count: int = 10

			@ps.computed
			def failing_computed(self):
				if self.count > 5:
					raise ValueError("Computed failed")
				return self.count * 2

		state = TestState()

		# First access should raise the original exception
		with pytest.raises(ValueError, match="Computed failed"):
			_ = state.failing_computed

		# Subsequent accesses should still raise the original exception, not circular dependency
		with pytest.raises(ValueError, match="Computed failed"):
			_ = state.failing_computed

		# After fixing the condition, it should work
		state.count = 3
		assert state.failing_computed == 6

	def test_state_metadata_captures_signals_queries_private(self):
		class Base(ps.State):
			count: int = 1
			message: str
			_secret_value: int = 3

			@ps.query(preserve=True)
			async def user(self):
				return {"name": "pulse"}

		meta = Base.__state_metadata__
		fields = meta.fields

		count_meta = fields["count"]
		assert count_meta.kind is StateFieldKind.SIGNAL
		assert count_meta.has_default is True
		assert count_meta.default == 1
		assert count_meta.drain is True
		assert count_meta.defined_on is Base

		message_meta = fields["message"]
		assert message_meta.kind is StateFieldKind.SIGNAL
		assert message_meta.has_default is False
		assert message_meta.default is None

		query_meta = fields["user"]
		assert query_meta.kind is StateFieldKind.QUERY
		assert query_meta.drain is True
		assert query_meta.preserve is True
		assert query_meta.descriptor is Base.__dict__["user"]
		assert query_meta.defined_on is Base

		secret_meta = fields["_secret_value"]
		assert secret_meta.kind is StateFieldKind.PRIVATE
		assert secret_meta.has_default is True
		assert secret_meta.default == 3
		assert secret_meta.drain is False
		assert secret_meta.defined_on is Base

	def test_state_metadata_inheritance_clone(self):
		class Parent(ps.State):
			alpha: int = 1

			@ps.query()
			async def fetch(self):
				return 1

		class Child(Parent):
			beta: str = "hi"
			_hidden: int

		parent_meta = Parent.__state_metadata__
		child_meta = Child.__state_metadata__

		assert child_meta.fields is not parent_meta.fields

		alpha_parent = parent_meta.fields["alpha"]
		alpha_child = child_meta.fields["alpha"]
		assert alpha_child is not alpha_parent
		assert alpha_child.defined_on is Parent

		beta_meta = child_meta.fields["beta"]
		assert beta_meta.kind is StateFieldKind.SIGNAL
		assert beta_meta.defined_on is Child
		assert beta_meta.has_default is True
		assert beta_meta.default == "hi"

		hidden_meta = child_meta.fields["_hidden"]
		assert hidden_meta.kind is StateFieldKind.PRIVATE
		assert hidden_meta.has_default is False
		assert hidden_meta.default is None
		assert hidden_meta.defined_on is Child

		query_meta = child_meta.fields["fetch"]
		assert query_meta.kind is StateFieldKind.QUERY
		assert query_meta.preserve is False
		assert query_meta.defined_on is Parent

	def test_state_version_defaults_and_migrate_override(self):
		class VersionBase(ps.State):
			__version__: int = 5

			@override
			@classmethod
			def __migrate__(
				cls, start_version: int, target_version: int, values: dict[str, Any]
			) -> dict[str, Any]:
				assert start_version == 4
				assert target_version == 5
				return {"upgraded": True, **values}

		class VersionChild(VersionBase):
			__version__: int = 6

		class Fresh(ps.State):
			pass

		assert Fresh.__version__ == 1

		with pytest.raises(NotImplementedError):
			Fresh.__migrate__(1, 2, {})

		assert VersionBase.__version__ == 5
		assert VersionChild.__version__ == 6

		result = VersionChild.__migrate__(4, 5, {"count": 1})
		assert result["upgraded"] is True
		assert result["count"] == 1

	def test_state_post_init_runs(self):
		class PostInitState(ps.State):
			counter: int = 0
			_init_flag: bool
			_post_init_flag: bool

			def __init__(self):
				self._init_flag = True
				super().__init__()

			def __post_init__(self):
				self._post_init_flag = True
				self.counter = 10

		state = PostInitState()
		assert getattr(state, "_init_flag", False) is True
		assert getattr(state, "_post_init_flag", False) is True
		assert state.counter == 10

	def test_state_drain_payload(self):
		class DrainState(ps.State):
			numbers: list[int]
			config: dict[str, int] = {"a": 1}
			_internal: str = "secret"

			@ps.query(preserve=True)
			async def preserved(self):
				return {"value": 1}

			@ps.query()
			async def ephemeral(self):
				return {"value": 2}

		state = DrainState()
		state.numbers = [1, 2]
		state.config["b"] = 2

		# Seed query results manually to avoid running asynchronous effects
		state.preserved.set_success({"value": 99})
		state.ephemeral.set_success({"value": -1})

		payload = state.drain()

		assert payload["__version__"] == DrainState.__version__
		values = payload["values"]
		assert isinstance(values, dict)

		assert "numbers" in values
		assert values["numbers"] == [1, 2]
		assert not isinstance(values["numbers"], ReactiveList)

		assert "config" in values
		assert values["config"] == {"a": 1, "b": 2}
		assert not isinstance(values["config"], ReactiveDict)

		assert "_internal" not in values
		assert "ephemeral" not in values

		assert "preserved" in values
		preserved_snapshot = values["preserved"]
		assert preserved_snapshot["data"] == {"value": 99}
		assert preserved_snapshot["has_loaded"] is True
		assert preserved_snapshot["is_loading"] is False
		assert preserved_snapshot["is_error"] is False
		assert preserved_snapshot["error"] is None

		assert state.__getstate__() == payload

		cloudpickle = pytest.importorskip("cloudpickle")
		cloudpickle.dumps(payload)

	def test_state_hydrate_round_trip(self):
		class HydrateState(ps.State):
			value: int = 1
			config: dict[str, int] = {"a": 1}
			secret: str = "visible"
			_secret: str = "secret"
			_post_hook_ran: bool = False

			@ps.query(preserve=True)
			async def preserved(self):
				return {"value": 0}

			@ps.query()
			async def ephemeral(self):
				return {"value": -1}

			def __post_init__(self):
				self._post_hook_ran = True

		state = HydrateState()
		state.value = 42
		state.config["b"] = 2
		state.secret = "changed"
		state._secret = "altered"  # pyright: ignore[reportPrivateUsage]

		preserved_query = state.preserved
		ephemeral_query = state.ephemeral
		preserved_query.set_success({"value": 99})
		ephemeral_query.set_success({"value": -99})

		payload = state.drain()

		rehydrated = hydrate_new(HydrateState, payload)

		assert isinstance(rehydrated, HydrateState)
		assert rehydrated.value == 42
		assert isinstance(rehydrated.config, ReactiveDict)
		assert rehydrated.config.unwrap() == {"a": 1, "b": 2}
		assert rehydrated.secret == "changed"
		assert rehydrated._secret == "secret"  # pyright: ignore[reportPrivateUsage]
		assert rehydrated._post_hook_ran is True  # pyright: ignore[reportPrivateUsage]

		preserved_after = rehydrated.preserved
		assert preserved_after.data == {"value": 99}
		assert preserved_after.is_loading is False
		assert preserved_after.is_error is False
		assert preserved_after.has_loaded is True

		ephemeral_after = rehydrated.ephemeral
		assert ephemeral_after.has_loaded is False
		assert ephemeral_after.is_loading is True

		def quick_compare(state_obj: HydrateState) -> dict[str, Any]:
			return {
				"value": state_obj.value,
				"config": unwrap(state_obj.config),
				"secret": state_obj.secret,
				"_secret": state_obj._secret,  # pyright: ignore[reportPrivateUsage]
			}

		assert quick_compare(rehydrated) == quick_compare(
			hydrate_new(HydrateState, payload)
		)

		def build_from_setstate() -> HydrateState:
			target = HydrateState.__new__(HydrateState)
			target.__setstate__(payload)
			return target

		from_setstate = build_from_setstate()
		assert quick_compare(from_setstate) == quick_compare(rehydrated)
		assert getattr(from_setstate, "_post_hook_ran", False) is True

	def test_state_hydrate_requires_migration(self):
		class NeedsMigration(ps.State):
			__version__: int = 2
			value: int = 0

		with pytest.raises(RuntimeError, match=r"missing migration coverage"):
			hydrate_new(NeedsMigration, {"__version__": 1, "values": {"value": 5}})

	def test_state_hydrate_missing_required_field(self):
		class MissingValue(ps.State):
			name: str

		with pytest.raises(
			ValueError, match=r"missing values for fields without defaults: name"
		):
			hydrate_new(MissingValue, {"__version__": 1, "values": {}})

	def test_state_hydrate_migration_applies_defaults(self):
		class Migrating(ps.State):
			__version__: int = 3
			count: int
			label: str = "ready"

			@override
			@classmethod
			def __migrate__(
				cls, start_version: int, target_version: int, values: dict[str, Any]
			) -> dict[str, Any]:
				assert start_version == 1
				assert target_version == 3
				updated = dict(values)
				updated.setdefault("count", 7)
				return updated

		payload: dict[str, Any] = {"__version__": 1, "values": {}}
		state = hydrate_new(Migrating, payload)
		assert state.count == 7
		assert state.label == "ready"

	def test_state_hydrate_requires_private_fields(self):
		class PrivateState(ps.State):
			value: int = 1
			_token: str

		with pytest.raises(
			ValueError, match=r"missing private fields after initialization: _token"
		):
			hydrate_new(PrivateState, {"__version__": 1, "values": {"value": 9}})
