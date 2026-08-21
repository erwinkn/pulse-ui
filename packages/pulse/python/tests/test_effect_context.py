# pyright: reportUnusedFunction=false
from __future__ import annotations

from typing import Any

import pulse as ps
import pytest
from pulse.context import PulseContext
from pulse.hooks.core import HookContext
from pulse.messages import ServerMessage
from pulse.reactive import flush_effects
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteInfo, RouteTree
from pulse.test_helpers import wait_for


def make_route_info(
	pathname: str, query_params: dict[str, str] | None = None
) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": query_params or {},
		"pathParams": {},
		"catchall": [],
	}


def navigations(msgs: list[ServerMessage]) -> list[Any]:
	return [m.get("path") for m in msgs if m.get("type") == "navigate_to"]


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
		seen: list[tuple[object, ...]] = []

		class Tracked(ps.State):
			n: int = 0

			@ps.effect
			def track(self):
				_ = self.n
				ctx = PulseContext.get()
				seen.append(
					(
						ctx.render,
						ctx.route,
						ctx.source_route_path,
						ctx.source_path,
						ctx.source_mount_id,
					)
				)

		app, session, route_ctx = make_session()
		mount = session.route_mounts["/"]
		with ps.PulseContext(
			app=app,
			render=session,
			route=route_ctx,
			source_route_path=route_ctx.route_path,
			source_path=route_ctx.pathname,
			source_mount_id=mount.mount_id,
		):
			state = Tracked()
		flush_effects()
		assert seen == [(session, route_ctx, route_ctx.route_path, "/", mount.mount_id)]

		state.n += 1
		flush_effects()
		identity = (session, route_ctx, route_ctx.route_path, "/", mount.mount_id)
		assert seen == [identity, identity]

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
		seen: list[tuple[object, ...]] = []

		class Tracked(ps.State):
			n: int = 0

			@ps.effect
			def track(self):
				_ = self.n
				ctx = PulseContext.get()
				seen.append(
					(
						ctx.render,
						ctx.route,
						ctx.source_route_path,
						ctx.source_path,
						ctx.source_mount_id,
					)
				)

		session_state = ps.global_state(Tracked)
		app, session, route_ctx = make_session()
		mount = session.route_mounts["/"]
		with ps.PulseContext(
			app=app,
			render=session,
			route=route_ctx,
			source_route_path=route_ctx.route_path,
			source_path=route_ctx.pathname,
			source_mount_id=mount.mount_id,
		):
			state = session_state()
		flush_effects()
		assert seen == [(session, None, None, None, None)]

		state.n += 1
		flush_effects()
		assert seen == [(session, None, None, None, None)] * 2

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

	@pytest.mark.asyncio
	async def test_async_cleanup_is_awaited_in_bound_context(self):
		cleaned: list[object] = []

		class Tracked(ps.State):
			n: int = 0

			@ps.effect
			async def track(self):
				_ = self.n

				async def cleanup():
					cleaned.append(PulseContext.get().render)

				return cleanup

		app, session, route_ctx = make_session()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = Tracked()
			assert await wait_for(lambda: state.track.runs == 1, timeout=0.2)
			state.n += 1
			assert await wait_for(lambda: cleaned == [session], timeout=0.2)


class TestEffectMountIdentity:
	"""Mount identity is resolved when the effect runs, never frozen."""

	def test_navigate_survives_strict_mode_replay(self):
		trigger = ps.Signal(0)

		@ps.component
		def Page():
			@ps.effect
			def go():
				if trigger() > 0:
					ps.navigate("/b")

			return ps.div()["page"]

		routes = [Route("a", Page), Route("b", ps.component(lambda: ps.div()))]
		app = ps.App(routes=routes)
		session = RenderSession(
			"s", RouteTree(routes), dev_strict_mode_detach_timeout=5.0
		)
		msgs: list[ServerMessage] = []
		session.connect(msgs.append)
		with ps.PulseContext(app=app, render=session):
			session.prerender(["/a"], make_route_info("/a"))
			session.attach("/a", make_route_info("/a"))
			# React StrictMode replays attach -> detach -> attach; detach renews
			# the mount id without re-rendering.
			session.detach("/a")
			session.attach("/a", make_route_info("/a"))
			trigger.write(1)
			session.flush()
			flush_effects()
		assert navigations(msgs) == ["/b"]
		session.close()

	def test_state_outliving_creating_mount_can_navigate(self):
		holder: list[Item] = []

		class Item(ps.State):
			n: int = 0

			@ps.effect
			def watch(self):
				if self.n > 0:
					ps.navigate("/c")

		@ps.component
		def PageA():
			def create():
				holder.append(Item())

			return ps.div(onClick=create)["a"]

		routes = [
			Route("a", PageA),
			Route("b", ps.component(lambda: ps.div())),
			Route("c", ps.component(lambda: ps.div())),
		]
		app = ps.App(routes=routes)
		session = RenderSession("s", RouteTree(routes))
		msgs: list[ServerMessage] = []
		session.connect(msgs.append)
		with ps.PulseContext(app=app, render=session):
			session.prerender(["/a"], make_route_info("/a"))
			session.attach("/a", make_route_info("/a"))
			key = next(iter(session.route_mounts["/a"].tree.callbacks))
			# State created while /a is the current mount, but kept outside it.
			session.execute_callback("/a", key, [])
			session.flush()
			flush_effects()
			session.prerender(["/b"], make_route_info("/b"))
			session.attach("/b", make_route_info("/b"))
			session.detach("/a")
			holder[0].n = 1
			session.flush()
			flush_effects()
		assert navigations(msgs) == ["/c"]
		session.close()

	def test_global_state_init_can_read_route(self):
		seen: list[RouteInfo] = []

		class Cfg(ps.State):
			def __init__(self):
				super().__init__()
				seen.append(ps.route())

		accessor = ps.global_state(Cfg)
		app, session, route_ctx = make_session("/a")
		mount = session.route_mounts["/a"]
		with ps.PulseContext(
			app=app,
			render=session,
			route=route_ctx,
			source_route_path=route_ctx.route_path,
			source_path=route_ctx.pathname,
			source_mount_id=mount.mount_id,
		):
			_ = accessor()
		assert [info["pathname"] for info in seen] == ["/a"]
		session.close()
