from __future__ import annotations

from collections.abc import Callable
from typing import cast

from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.reactive import Effect, EffectFn, Untrack


class EffectsHookState(HookState):
	__slots__ = ("initialized", "effects", "key", "_called")

	def __init__(self) -> None:
		super().__init__()
		self.initialized = False
		self.effects: tuple[Effect, ...] = ()
		self.key: str | None = None
		self._called = False

	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		self._called = False

	def replace(self, effects: list[Effect], key: str | None) -> None:
		self.dispose_effects()
		self.effects = tuple(effects)
		self.key = key
		self.initialized = True

	def dispose_effects(self) -> None:
		for effect in self.effects:
			effect.dispose()
		self.effects = ()
		self.initialized = False
		self.key = None

	def dispose(self) -> None:
		self.dispose_effects()

	def ensure_not_called(self) -> None:
		if self._called:
			raise RuntimeError(
				"`pulse.effects` can only be called once per component render"
			)

	def mark_called(self) -> None:
		self._called = True


def _build_effects(
	fns: tuple[EffectFn, ...],
	on_error: Callable[[Exception], None] | None,
) -> list[Effect]:
	effects: list[Effect] = []
	with Untrack():
		for fn in fns:
			if not callable(fn):
				raise ValueError(
					"Only pass functions or callable objects to `ps.effects`"
				)
			effects.append(
				Effect(fn, name=getattr(fn, "__name__", "effect"), on_error=on_error)
			)
	return effects


def _effects_factory(*_: object) -> HookState:
	return EffectsHookState()


_effects_hook = hooks.create(
	"pulse:core.effects",
	_effects_factory,
	metadata=HookMetadata(
		owner="pulse.core",
		description="Internal storage for pulse.effects hook",
	),
)


def effects(
	*fns: EffectFn,
	on_error: Callable[[Exception], None] | None = None,
	key: str | None = None,
) -> None:
	state = cast(EffectsHookState, _effects_hook())
	state.ensure_not_called()

	if not state.initialized:
		state.replace(_build_effects(fns, on_error), key)
		state.mark_called()
		return

	if key is not None and key != state.key:
		state.replace(_build_effects(fns, on_error), key)
		state.mark_called()
		return

	state.mark_called()


__all__ = ["effects", "EffectsHookState"]
