from asyncio import iscoroutine
import logging
from typing import Any, Callable, Optional
import uuid
import asyncio
import traceback

from pulse.context import PulseContext
from pulse.helpers import create_future_on_loop
from pulse.messages import (
    RouteInfo,
    ServerInitMessage,
    ServerMessage,
    ServerUpdateMessage,
    ServerErrorMessage,
)
from pulse.reactive import Effect, flush_effects
from pulse.reconciler import RenderRoot
from pulse.routing import Layout, Route, RouteContext, RouteTree
from pulse.state import State
from pulse.hooks import RedirectInterrupt, NotFoundInterrupt


logger = logging.getLogger(__file__)


class RouteMount:
    def __init__(
        self, render: "RenderSession", route: Route | Layout, route_info: RouteInfo
    ) -> None:
        self.render = render
        self.root = RenderRoot(route.render.fn)
        self.route = RouteContext(route_info)
        self.effect: Optional[Effect] = None
        self._pulse_ctx: PulseContext | None = None


class RenderSession:
    def __init__(
        self,
        id: str,
        routes: RouteTree,
        *,
        server_address: Optional[str] = None,
        client_address: Optional[str] = None,
    ) -> None:
        self.id = id
        self.routes = routes
        self.route_mounts: dict[str, RouteMount] = {}
        # Base server address for building absolute API URLs (e.g., http://localhost:8000)
        self._server_address: Optional[str] = server_address
        # Best-effort client address, captured at prerender or socket connect time
        self._client_address: Optional[str] = client_address
        self._send_message: Callable[[ServerMessage], Any] | None = None
        self._pending_api: dict[str, asyncio.Future] = {}
        # Registry of per-session global singletons (created via ps.global_state without id)
        self._global_states: dict[str, State] = {}
        # Connection state
        self.connected: bool = False

    @property
    def server_address(self) -> str:
        if self._server_address is None:
            raise RuntimeError("Server address not set")
        return self._server_address

    @property
    def client_address(self) -> str:
        if self._client_address is None:
            raise RuntimeError("Client address not set")
        return self._client_address

    # Effect error handler (batch-level) to surface runtime errors
    def _on_effect_error(self, effect, exc: Exception):
        # TODO: wirte into effects created within a Render

        # We don't want to couple effects to routing; broadcast to all active paths
        details = {"effect": getattr(effect, "name", "<unnamed>")}
        for path in list(self.route_mounts.keys()):
            self.report_error(path, "effect", exc, details)

    def connect(self, send_message: Callable[[ServerMessage], Any]):
        self._send_message = send_message
        self.connected = True

    def send(self, message: ServerMessage):
        if not self._send_message:
            raise RuntimeError("RenderSession is not connected")
        print(f"[Render {self.id}, send] {message}")
        self._send_message(message)

    def report_error(
        self,
        path: str,
        phase: str,
        exc: Exception,
        details: dict[str, Any] | None = None,
    ):
        error_msg: ServerErrorMessage = {
            "type": "server_error",
            "path": path,
            "error": {
                "message": str(exc),
                "stack": traceback.format_exc(),
                "phase": phase,  # type: ignore
                "details": details or {},
            },
        }
        self.send(error_msg)
        logger.error(
            "Error reported for path %r during %s: %s\n%s",
            path,
            phase,
            exc,
            traceback.format_exc(),
        )

    def close(self):
        # The effect will be garbage collected, and with it the dependencies
        self._send_message = None
        self.connected = False
        for path in list(self.route_mounts.keys()):
            self.unmount(path)
        self.route_mounts.clear()
        # Dispose per-session global singletons if they expose dispose()
        for value in list(self._global_states.values()):
            try:
                value.dispose()
            except Exception as e:  # noqa: BLE001
                # Best-effort: report but continue cleanup
                logger.exception("Error disposing session global state: %s", e)
        self._global_states.clear()

    def execute_callback(self, path: str, key: str, args: list | tuple):
        mount = self.route_mounts[path]
        try:
            cb = mount.root.callbacks[key]
            fn, n_params = cb.fn, cb.n_args
            res = fn(*args[:n_params])
            if iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(res)
                except RuntimeError:
                    from anyio import from_thread

                    async def _schedule():
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(res)
                        return task

                    task = from_thread.run(_schedule)

                def _on_task_done(t):
                    try:
                        t.result()
                    except Exception as e:  # noqa: BLE001 - forward all
                        self.report_error(
                            path,
                            "callback",
                            e,
                            {"callback": key, "async": True},
                        )

                task.add_done_callback(_on_task_done)
        except Exception as e:  # noqa: BLE001 - forward all
            self.report_error(path, "callback", e, {"callback": key})

    async def call_api(
        self,
        url_or_path: str,
        *,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        body: Any | None = None,
        credentials: str = "include",
    ) -> dict[str, Any]:
        """Request the client to perform a fetch and await the result.

        Accepts either an absolute URL (http/https) or a relative path. When a
        relative path is provided, it is resolved against this session's
        server_address.
        """
        # Resolve to absolute URL if a relative path is passed
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            url = url_or_path
        else:
            base = self.server_address
            if not base:
                raise RuntimeError(
                    "Server address unavailable. Ensure App.run_codegen/asgi_factory set server_address."
                )
            path = url_or_path if url_or_path.startswith("/") else "/" + url_or_path
            url = f"{base}{path}"
        corr_id = uuid.uuid4().hex
        fut = create_future_on_loop()
        self._pending_api[corr_id] = fut
        headers = headers or {}
        headers["x-pulse-render-id"] = self.id
        self.send(
            {
                "type": "api_call",
                "id": corr_id,
                "url": url,
                "method": method,
                "headers": headers,
                "body": body,
                "credentials": "include" if credentials == "include" else "omit",
            }
        )
        result = await fut
        return result

    def handle_api_result(self, data: dict[str, Any]):
        id_ = data.get("id")
        if id_ is None:
            return
        id_ = str(id_)
        fut = self._pending_api.pop(id_, None)
        if fut and not fut.done():
            fut.set_result(
                {
                    "ok": data.get("ok", False),
                    "status": data.get("status", 0),
                    "headers": data.get("headers", {}),
                    "body": data.get("body"),
                }
            )

    def create_route_mount(self, path: str, route_info: Optional[RouteInfo] = None):
        route = self.routes.find(path)
        mount = RouteMount(self, route, route_info or route.default_route_info())
        self.route_mounts[path] = mount
        return mount

    def prerender_mount_capture(
        self, path: str, route_info: Optional[RouteInfo] = None
    ):
        """
        Mount the route and run the render effect immediately, capturing the
        initial message instead of sending over a socket.

        Returns a dict:
          { "type": "vdom_init", "vdom": VDOM } or
          { "type": "navigate_to", "path": str, "replace": bool }
        """
        # If already mounted (e.g., repeated prerender), do nothing special.
        if path in self.route_mounts:
            # Run a diff and synthesize an update; however, for prerender we
            # expect initial mount. Return current tree as a full VDOM.
            mount = self.get_route_mount(path)
            vdom = mount.root.render_vdom()
            return {"type": "vdom_init", "vdom": vdom}

        captured: dict | None = None

        def _capture(msg: ServerMessage):
            nonlocal captured
            # Only capture the first relevant message for this path
            if captured is not None:
                return
            mtype = msg.get("type") if isinstance(msg, dict) else None
            if mtype == "vdom_init" and msg.get("path") == path:
                captured = {"type": "vdom_init", "vdom": msg.get("vdom")}
            elif mtype == "navigate_to":
                captured = {
                    "type": "navigate_to",
                    "path": msg.get("path"),
                    "replace": bool(msg.get("replace")),
                }

        prev_sender = self._send_message
        try:
            self._send_message = _capture
            # Reuse normal mount flow which creates and runs the effect
            self.mount(path, route_info or self.routes.find(path).default_route_info())
            # Flush any scheduled effects to stabilize output
            self.flush()
        finally:
            self._send_message = prev_sender

        # Fallback: if nothing captured (shouldn't happen), return full VDOM
        if captured is None:
            mount = self.get_route_mount(path)
            vdom = mount.root.render_vdom()
            return {"type": "vdom_init", "vdom": vdom}

        return captured

    def get_route_mount(
        self,
        path: str,
    ):
        mount = self.route_mounts.get(path)
        if not mount:
            raise ValueError(f"No active route for '{path}'")
        return mount

    # ---- Session-local global state registry ----
    def get_global_state(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return a per-session singleton for the provided key."""
        inst = self._global_states.get(key)
        if inst is None:
            inst = factory()
            self._global_states[key] = inst
        return inst

    def render(
        self, path: str, route_info: Optional[RouteInfo] = None
    ):
        mount = self.create_route_mount(path, route_info)
        with PulseContext.update(route=mount.route):
            return mount.root.render_vdom()

    def rerender(self, path: str):
        mount = self.get_route_mount(path)
        with PulseContext.update(route=mount.route):
            return mount.root.render_diff()

    def mount(self, path: str, route_info: RouteInfo):
        if path in self.route_mounts:
            # No logging, this is bound to happen with React strict mode
            # logger.error(f"Route already mounted: '{path}'")
            return

        mount = self.create_route_mount(path, route_info)
        # Get current context + add RouteContext. Save it to be able to mount it
        # whenever the render effect reruns.
        ctx = PulseContext.update(route=mount.route)

        def _render_effect():
            with ctx:
                try:
                    if mount.root.render_count == 0:
                        vdom = mount.root.render_vdom()
                        self.send(
                            ServerInitMessage(type="vdom_init", path=path, vdom=vdom)
                        )
                    else:
                        result = mount.root.render_diff()
                        if result.ops:
                            self.send(
                                ServerUpdateMessage(
                                    type="vdom_update", path=path, ops=result.ops
                                )
                            )
                except RedirectInterrupt as r:
                    # Prefer client-side navigation over emitting VDOM operations
                    self.send(
                        {"type": "navigate_to", "path": r.path, "replace": r.replace}
                    )
                except NotFoundInterrupt:
                    # Use app-configured not-found path; fallback to '/404'
                    self.send(
                        {
                            "type": "navigate_to",
                            "path": ctx.app.not_found,
                            "replace": True,
                        }
                    )

        mount.effect = Effect(
            _render_effect,
            immediate=True,
            name=f"{path}:render",
            on_error=lambda e: self.report_error(path, "render", e),
        )

    def flush(self):
        flush_effects()

    def navigate(self, path: str, route_info: RouteInfo):
        # Route is already mounted, we can just update the routing state
        try:
            mount = self.get_route_mount(path)
            mount.route.update(route_info)
        except Exception as e:  # noqa: BLE001
            self.report_error(path, "navigate", e)

    def unmount(self, path: str):
        if path not in self.route_mounts:
            return
        try:
            mount = self.route_mounts.pop(path)
            mount.root.unmount()
            if mount.effect:
                mount.effect.dispose()
        except Exception as e:  # noqa: BLE001
            self.report_error(path, "unmount", e)
