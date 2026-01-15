from collections.abc import Callable
from typing import Any, override

from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.reactive import AsyncEffect, Effect


class InlineEffectHookState(HookState):
	"""Stores inline effects keyed by (code, lineno, key)."""

	__slots__ = ("effects", "_seen_this_render")  # pyright: ignore[reportUnannotatedClassAttribute]

	def __init__(self) -> None:
		super().__init__()
		self.effects: dict[tuple[Any, ...], Effect | AsyncEffect] = {}
		self._seen_this_render: set[tuple[Any, ...]] = set()

	@override
	def on_render_start(self, render_cycle: int) -> None:
		super().on_render_start(render_cycle)
		self._seen_this_render.clear()

	@override
	def on_render_end(self, render_cycle: int) -> None:
		super().on_render_end(render_cycle)
		# Dispose effects that weren't seen this render (e.g., inside conditionals that became false)
		for key in list(self.effects.keys()):
			if key not in self._seen_this_render:
				self.effects[key].dispose()
				del self.effects[key]

	def get_or_create(
		self,
		identity: tuple[Any, int],
		key: str | None,
		factory: Callable[[], Effect | AsyncEffect],
	) -> Effect | AsyncEffect:
		# Detect duplicate calls in same render (e.g., effect in a loop)
		# Include key in the seen check - different keys are allowed at same location
		full_identity = (*identity, key)
		if full_identity in self._seen_this_render:
			if key is None:
				raise RuntimeError(
					"@ps.effect decorator called multiple times at the same location during a single render. "
					+ "This usually happens when using @ps.effect inside a loop. "
					+ "Use the `key` parameter to disambiguate: @ps.effect(key=unique_value)"
				)
			raise RuntimeError(
				f"@ps.effect decorator called multiple times with the same key='{key}' "
				+ "during a single render. Each effect in a loop needs a unique key."
			)
		self._seen_this_render.add(full_identity)

		full_key = (*identity, key)
		existing = self.effects.get(full_key)

		if existing is not None:
			return existing

		# If key changed, dispose old effect with same identity but different key
		if key is not None:
			for old_key, eff in list(self.effects.items()):
				if old_key[:2] == identity and old_key[2] != key:
					eff.dispose()
					del self.effects[old_key]

		effect = factory()
		self.effects[full_key] = effect
		return effect

	@override
	def dispose(self) -> None:
		for eff in self.effects.values():
			eff.dispose()
		self.effects.clear()
		self._seen_this_render.clear()


inline_effect_hook = hooks.create(
	"pulse:core.inline_effects",
	lambda: InlineEffectHookState(),
	metadata=HookMetadata(
		owner="pulse.core",
		description="Storage for inline @ps.effect decorators in components",
	),
)


__all__ = [
	"InlineEffectHookState",
	"inline_effect_hook",
]
