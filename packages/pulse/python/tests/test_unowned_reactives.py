# pyright: reportUnusedFunction=false
"""App(unowned_reactives=...): Effects/States constructed during a component
render without an owner are flagged (error by default) instead of leaking."""

import logging
from typing import override

import pulse as ps
import pytest
from pulse.app import App
from pulse.reactive import Effect, Signal, flush_effects
from pulse.renderer import RenderTree


class Plain(ps.State):
	count: int = 0


class _HookOwnedState(ps.hooks.State):
	owned: Plain

	def __init__(self) -> None:
		super().__init__()
		self.owned = Plain()

	@override
	def dispose(self) -> None:
		self.owned.dispose()


def test_raw_effect_in_component_body_errors():
	@ps.component
	def Comp():
		Effect(lambda: None, name="orphan")
		return ps.div()

	tree = RenderTree(Comp())
	with pytest.raises(RuntimeError, match="orphan"):
		tree.render()


def test_raw_state_in_component_body_errors():
	created: list[Plain] = []

	@ps.component
	def Comp():
		state = Plain()
		created.append(state)
		return ps.div(f"{state.count}")

	tree = RenderTree(Comp())
	with pytest.raises(RuntimeError, match="Plain"):
		tree.render()
	# The orphan is disposed before raising so it cannot leak.
	assert created[0].__disposed__


def test_warn_policy_logs_and_renders(caplog: pytest.LogCaptureFixture):
	@ps.component
	def Comp():
		Plain()
		return ps.div("ok")

	with ps.PulseContext(app=App(unowned_reactives="warn")):
		tree = RenderTree(Comp())
		with caplog.at_level(logging.WARNING, logger="pulse.renderer"):
			vdom = tree.render()
		tree.unmount()
	assert vdom == {"tag": "div", "children": ["ok"]}
	assert any("Plain" in record.message for record in caplog.records)


def test_ignore_policy_renders_silently(caplog: pytest.LogCaptureFixture):
	@ps.component
	def Comp():
		Plain()
		return ps.div("ok")

	with ps.PulseContext(app=App(unowned_reactives="ignore")):
		tree = RenderTree(Comp())
		with caplog.at_level(logging.WARNING, logger="pulse.renderer"):
			tree.render()
		tree.unmount()
	assert not caplog.records


# Registered at import time: some suites lock the hook registry mid-run.
custom_hook = ps.hooks.create(
	"test:unowned.owned-by-hook", factory=lambda: _HookOwnedState()
)


def test_owned_patterns_do_not_trigger():
	sig = Signal(0)

	class WithEffect(ps.State):
		count: int = 0

		@ps.effect
		def watch(self):
			_ = self.count

	@ps.component
	def Comp():
		with ps.init():
			a = WithEffect()
		b = ps.state(lambda: Plain())
		c = custom_hook()

		@ps.effect
		def inline():
			_ = sig()

		return ps.div(f"{a.count}{b.count}{c.render_cycle}")

	tree = RenderTree(Comp())
	tree.render()
	flush_effects()
	# Re-render must stay clean too.
	sig.write(1)
	flush_effects()
	tree.unmount()


def test_state_instance_passed_to_ps_state_is_adopted():
	"""ps.state(SomeState()) constructs the instance in the component body;
	the hook adopts it, so the check must not flag it."""

	@ps.component
	def Comp():
		state = ps.state(Plain())
		return ps.div(f"{state.count}")

	tree = RenderTree(Comp())
	tree.render()
	# Re-render: the freshly constructed instance is disposed by the hook in
	# favor of the cached one - still not a violation.
	tree.rerender()
	tree.unmount()
