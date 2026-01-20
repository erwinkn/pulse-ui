from collections.abc import Callable
from typing import Any, override

from pulse.hooks.core import HookMetadata, HookState, hooks
from pulse.reactive import AsyncEffect, Effect


class InlineEffectHookState(HookState):
	"""Stores inline effects keyed by function identity or explicit key."""

	__slots__ = ("effects", "_seen_this_render")  # pyright: ignore[reportUnannotatedClassAttribute]

	def __init__(self) -> None:
		super().__init__()
		self.effects: dict[tuple[str, Any], Effect | AsyncEffect] = {}
		self._seen_this_render: set[tuple[str, Any]] = set()

	def _make_key(self, identity: Any, key: str | None) -> tuple[str, Any]:
		if key is None:
			return ("code", identity)
		return ("key", key)

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
		identity: Any,
		key: str | None,
		factory: Callable[[], Effect | AsyncEffect],
	) -> Effect | AsyncEffect:
		"""Return cached effect or create a new one."""
		# Effects with explicit keys fully bypass identity matching.
		full_identity = self._make_key(identity, key)

		if full_identity in self._seen_this_render:
			if key is None:
				raise RuntimeError(
					"@ps.effect decorator called multiple times at the same location during a single render. "
					+ "This usually happens when using @ps.effect inside a loop. "
					+ "Use the `key` parameter to disambiguate: @ps.effect(key=unique_value)"
				)
			raise RuntimeError(
				f"@ps.effect decorator called multiple times with the same key='{key}' during a single render."
			)
		self._seen_this_render.add(full_identity)

		existing = self.effects.get(full_identity)
		if existing is not None:
			return existing

		effect = factory()
		self.effects[full_identity] = effect
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
