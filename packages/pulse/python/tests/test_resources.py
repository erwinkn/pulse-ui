from typing import override

import pytest
from pulse.reactive import Effect
from pulse.resources import Resource, ResourceScope
from pulse.state.state import State


class TrackedResource(Resource):
	name: str
	events: list[str]
	fail: bool

	def __init__(self, name: str, events: list[str], *, fail: bool = False) -> None:
		self.name = name
		self.events = events
		self.fail = fail

	@override
	def dispose(self) -> None:
		self.events.append(self.name)
		if self.fail:
			raise RuntimeError(self.name)


def test_resource_scope_disposes_lifo_and_continues_after_error():
	events: list[str] = []
	scope = ResourceScope()
	scope.own(TrackedResource("first", events))
	scope.own(TrackedResource("failing", events, fail=True))

	with pytest.raises(RuntimeError, match="failing"):
		scope.dispose()

	assert events == ["failing", "first"]


def test_resource_scope_transfers_exclusive_ownership():
	events: list[str] = []
	resource = TrackedResource("resource", events)
	first = ResourceScope()
	second = ResourceScope()

	first.own(resource)
	second.own(resource)
	first.dispose()
	assert events == []

	second.dispose()
	assert events == ["resource"]


def test_resource_scope_rejects_self_ownership():
	scope = ResourceScope()

	with pytest.raises(RuntimeError, match="cannot own itself"):
		scope.own(scope)


def test_state_owns_effect_created_in_constructor():
	class EffectState(State):
		_effect: Effect

		def __init__(self) -> None:
			self._effect = Effect(lambda: None, lazy=True)

	state = EffectState()
	effect = state._effect  # pyright: ignore[reportPrivateUsage]
	state.dispose()

	assert effect.__disposed__


def test_state_owns_resource_assigned_after_construction():
	class LateState(State):
		_late: Effect | None = None

		def attach(self) -> None:
			self._late = Effect(lambda: None, lazy=True)

	state = LateState()
	state.attach()
	effect = state._late  # pyright: ignore[reportPrivateUsage]
	assert effect is not None
	assert not effect.__disposed__

	state.dispose()

	assert effect.__disposed__


def test_state_reassignment_disposes_replaced_resource():
	class LateState(State):
		_late: Effect | None = None

		def attach(self) -> None:
			self._late = Effect(lambda: None, lazy=True)

	state = LateState()
	state.attach()
	first = state._late  # pyright: ignore[reportPrivateUsage]
	state.attach()
	second = state._late  # pyright: ignore[reportPrivateUsage]

	assert first is not None and first.__disposed__
	assert second is not None and not second.__disposed__

	state.dispose()
	assert second.__disposed__


def test_state_assignment_does_not_steal_from_unrelated_scope():
	external = ResourceScope()
	effect = Effect(lambda: None, lazy=True)
	external.own(effect)

	class RefState(State):
		_ref: Effect | None = None

		def attach(self, resource: Effect) -> None:
			self._ref = resource

	state = RefState()
	state.attach(effect)
	state.dispose()
	assert not effect.__disposed__

	external.dispose()
	assert effect.__disposed__


def test_state_claims_constructor_resource_from_enclosing_scope():
	class Holder(State):
		_res: Effect

		def __init__(self, resource: Effect) -> None:
			self._res = resource

	outer = ResourceScope()
	with outer:
		effect = Effect(lambda: None, lazy=True)
		holder = Holder(effect)

	holder.dispose()

	assert effect.__disposed__
	outer.dispose()


def test_state_subclass_cannot_override_dispose():
	with pytest.raises(TypeError, match="on_dispose"):

		class BadState(State):  # pyright: ignore[reportUnusedClass]
			@override
			def dispose(self) -> None:
				pass


def test_disposed_state_error_names_the_state():
	class NamedState(State):
		_late: Effect | None = None

		def attach(self) -> None:
			self._late = Effect(lambda: None, lazy=True)

	state = NamedState()
	state.dispose()

	with pytest.raises(RuntimeError, match="NamedState"):
		state.attach()
