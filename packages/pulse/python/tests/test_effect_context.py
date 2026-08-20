# pyright: reportUnusedFunction=false
from __future__ import annotations

import pulse as ps
import pytest
from pulse.context import PulseContext
from pulse.hooks.core import HookContext
from pulse.reactive import flush_effects
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteInfo, RouteTree
from pulse.test_helpers import wait_for


def make_route_info(pathname: str) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}


def make_session(pathname: str = "/"):
	def render():
		return ps.div()

	route = Route(pathname.lstrip("/") or "/", ps.component(render))
	routes = RouteTree([route])
	session = RenderSession("test", routes)
	app = ps.App(routes=[route])
	info = make_route_info(pathname)
	session.prerender([pathname], info)
	return app, session, session.route_mounts[pathname].route


class TestEffectPulseContext:
	def test_state_effect_reenters_render_and_route(self):
		seen: list[tuple[object, object]] = []

		class Tracked(ps.State):
			n: int = 0

			@ps.effect
			def track(self):
				_ = self.n
				ctx = PulseContext.get()
				seen.append((ctx.render, ctx.route))

		app, session, route_ctx = make_session()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = Tracked()
		flush_effects()
		assert seen == [(session, route_ctx)]

		state.n += 1
		flush_effects()
		assert seen == [(session, route_ctx), (session, route_ctx)]

	def test_state_effect_sees_updated_route(self):
		pathnames: list[str] = []

		class Tracked(ps.State):
			n: int = 0

			@ps.effect
			def track(self):
				_ = self.n
				route = PulseContext.get().route
				assert route is not None
				pathnames.append(route.pathname)

		app, session, route_ctx = make_session("/")
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = Tracked()
		flush_effects()
		assert pathnames == ["/"]

		route_ctx.update(make_route_info("/next"))
		state.n += 1
		flush_effects()
		assert pathnames == ["/", "/next"]

	def test_global_state_effect_has_render_but_no_route(self):
		seen: list[tuple[object, object]] = []

		class Tracked(ps.State):
			n: int = 0

			@ps.effect
			def track(self):
				_ = self.n
				ctx = PulseContext.get()
				seen.append((ctx.render, ctx.route))

		session_state = ps.global_state(Tracked)
		app, session, route_ctx = make_session()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = session_state()
		flush_effects()
		assert seen == [(session, None)]

		state.n += 1
		flush_effects()
		assert seen == [(session, None), (session, None)]

	def test_cleanup_reenters_context(self):
		cleaned: list[object] = []

		class Tracked(ps.State):
			n: int = 0

			@ps.effect
			def track(self):
				_ = self.n

				def cleanup():
					cleaned.append(PulseContext.get().render)

				return cleanup

		app, session, route_ctx = make_session()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = Tracked()
		flush_effects()
		assert cleaned == []

		state.n += 1
		flush_effects()
		assert cleaned == [session]

		state.dispose()
		assert cleaned == [session, session]

	def test_inline_effect_reenters_render_and_route(self):
		seen: list[tuple[object, object]] = []

		@ps.component
		def Comp():
			@ps.effect
			def track():
				ctx = PulseContext.get()
				seen.append((ctx.render, ctx.route))

			return ps.div()

		app, session, route_ctx = make_session()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			with HookContext():
				Comp.fn()
		flush_effects()
		assert seen == [(session, route_ctx)]

	def test_standalone_effect_without_render_is_unbound(self):
		from pulse.context import PULSE_CONTEXT

		ran = {"n": 0}

		@ps.effect
		def track():
			ran["n"] += 1
			ctx = PULSE_CONTEXT.get()
			assert ctx is None or ctx.render is None

		flush_effects()
		assert ran["n"] == 1

	@pytest.mark.asyncio
	async def test_async_state_effect_reenters_context(self):
		seen: list[object] = []

		class Tracked(ps.State):
			@ps.effect
			async def track(self):
				seen.append(PulseContext.get().render)

		app, session, route_ctx = make_session()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			Tracked()
		assert await wait_for(lambda: seen == [session], timeout=0.2)
