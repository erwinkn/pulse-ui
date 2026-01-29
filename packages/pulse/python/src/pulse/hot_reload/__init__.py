from __future__ import annotations

import asyncio
import fnmatch
import importlib
import logging
import os
import sys
import traceback
from dataclasses import dataclass
from importlib import util as importlib_util
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

import anyio
from watchfiles import awatch

from pulse.env import (
	ENV_PULSE_HOT_RELOAD,
	ENV_PULSE_HOT_RELOAD_DIRS,
	ENV_PULSE_HOT_RELOAD_EXCLUDES,
	ENV_PULSE_HOT_RELOAD_TRIGGER,
	env,
)
from pulse.hot_reload.context import hot_reload_context
from pulse.hot_reload.deps import set_active_module_index
from pulse.hot_reload.signatures import compute_component_signature_data
from pulse.transpiler import (
	clear_asset_registry,
	clear_function_cache,
	clear_import_registry,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HotReloadError:
	message: str
	exc: BaseException | None
	traceback: str | None


@dataclass(slots=True)
class HotReloadPlan:
	changed_paths: set[Path]
	python_paths: set[Path]
	module_names: list[str]
	requires_client_reload: bool
	requires_process_reload: bool
	reason: str | None
	new_app: Any | None = None
	new_signature: "AppSignature | None" = None
	app_module_name: str | None = None
	app_var: str | None = None


@dataclass(slots=True)
class ModuleInfo:
	name: str
	file: Path
	package_root: Path
	reloadable: bool


@dataclass(slots=True)
class ModuleIndex:
	by_file: dict[Path, ModuleInfo]
	by_name: dict[str, ModuleInfo]
	watch_roots: list[Path]

	@classmethod
	def from_sys_modules(cls, watch_roots: list[Path]) -> "ModuleIndex":
		by_file: dict[Path, ModuleInfo] = {}
		by_name: dict[str, ModuleInfo] = {}
		for name, module in list(sys.modules.items()):
			file_attr = getattr(module, "__file__", None)
			if not file_attr:
				continue
			path = Path(file_attr)
			if path.suffix == ".pyc":
				path = path.with_suffix(".py")
			try:
				resolved = path.resolve()
			except Exception:
				continue
			if _is_site_package(resolved):
				continue
			if not resolved.exists():
				continue
			package_root = resolved.parent
			reloadable = _is_under_any(resolved, watch_roots)
			info = ModuleInfo(
				name=name,
				file=resolved,
				package_root=package_root,
				reloadable=reloadable,
			)
			by_file[resolved] = info
			by_name[name] = info
		return cls(by_file=by_file, by_name=by_name, watch_roots=watch_roots)

	def resolve_module(self, path: Path) -> ModuleInfo | None:
		return self.by_file.get(path)


@dataclass(slots=True)
class ModuleGraph:
	deps: dict[str, set[str]]
	rdeps: dict[str, set[str]]

	@classmethod
	def build_from_ast(cls, index: ModuleIndex) -> "ModuleGraph":
		deps: dict[str, set[str]] = {}
		rdeps: dict[str, set[str]] = {}
		for name, info in index.by_name.items():
			if not info.reloadable:
				continue
			imports = _parse_imports(info.file, name, index)
			deps[name] = imports
			for dep in imports:
				rdeps.setdefault(dep, set()).add(name)
		return cls(deps=deps, rdeps=rdeps)

	def dirty_set(self, changed: set[str]) -> set[str]:
		dirty = set(changed)
		stack = list(changed)
		while stack:
			mod = stack.pop()
			for dep in self.rdeps.get(mod, set()):
				if dep in dirty:
					continue
				dirty.add(dep)
				stack.append(dep)
		return dirty


@dataclass(slots=True)
class AppSignature:
	mode: str
	api_prefix: str
	not_found: str
	codegen_web_dir: str
	codegen_pulse_dir: str
	routes_signature: tuple[Any, ...]
	middleware_signature: tuple[str, ...]
	plugin_signature: tuple[str, ...]
	cookie_signature: tuple[Any, ...]
	session_signature: tuple[Any, ...]

	@classmethod
	def from_app(cls, app: Any) -> "AppSignature":
		return cls(
			mode=app.mode,
			api_prefix=app.api_prefix,
			not_found=app.not_found,
			codegen_web_dir=str(app.codegen.cfg.web_dir),
			codegen_pulse_dir=str(app.codegen.cfg.pulse_dir),
			routes_signature=_routes_signature(app.routes.tree),
			middleware_signature=_middleware_signature(app),
			plugin_signature=_plugin_signature(app),
			cookie_signature=_cookie_signature(app),
			session_signature=_session_signature(app),
		)


class HotReloadManager:
	app: Any
	watch_roots: list[Path]
	exclude_globs: list[str]
	debounce_ms: int
	trigger_path: Path | None
	task: asyncio.Task[None] | None
	lock: asyncio.Lock
	last_error: HotReloadError | None

	def __init__(
		self,
		*,
		app: Any,
		watch_roots: list[Path],
		exclude_globs: list[str],
		debounce_ms: int = 250,
		trigger_path: Path | None = None,
	) -> None:
		self.app = app
		self.watch_roots = watch_roots
		self.exclude_globs = exclude_globs
		self.debounce_ms = debounce_ms
		self.trigger_path = trigger_path
		self.task = None
		self.lock = asyncio.Lock()
		self.last_error = None
		self._stop_event: anyio.Event = anyio.Event()
		self._queued_changes: set[Path] | None = None
		self._module_index: ModuleIndex = ModuleIndex.from_sys_modules(self.watch_roots)
		set_active_module_index(self._module_index)
		self._refresh_component_deps(set())

	def start(self) -> None:
		if self.task is not None and not self.task.done():
			return
		if self.task is not None and self.task.done():
			self.task = None
		if self._stop_event.is_set():
			self._stop_event = anyio.Event()
		if not self.watch_roots:
			return
		self.task = self.app._tasks.create_task(
			self._watch_loop(),
			name="hot-reload",
		)

	def stop(self) -> None:
		self._stop_event.set()
		if self.task is not None and not self.task.done():
			self.task.cancel()
		self.task = None

	async def _watch_loop(self) -> None:
		roots = [str(root) for root in self.watch_roots]
		try:
			while not self._stop_event.is_set():
				try:
					async for changes in awatch(
						*roots,
						stop_event=self._stop_event,
						debounce=self.debounce_ms,
					):
						pending = _paths_from_changes(changes)
						pending = self._filter_paths(pending)
						if not pending:
							continue
						try:
							await self.request_reload(pending)
						except Exception as exc:
							self.last_error = HotReloadError(
								message="hot reload failed",
								exc=exc,
								traceback=traceback.format_exc(),
							)
							logger.exception("Hot reload failed")
					if not self._stop_event.is_set():
						logger.warning("Hot reload watcher stopped; restarting")
				except Exception:
					if self._stop_event.is_set():
						return
					logger.exception("Hot reload watcher crashed; restarting")
				await asyncio.sleep(0.5)
		except asyncio.CancelledError:
			return

	async def request_reload(self, changed_paths: set[Path]) -> None:
		if self.lock.locked():
			if self._queued_changes is None:
				self._queued_changes = set()
			self._queued_changes.update(changed_paths)
			return

		pending = changed_paths
		while pending:
			async with self.lock:
				await self._reload_with_changes(pending)
			pending = self._queued_changes or set()
			self._queued_changes = None

	async def _reload_with_changes(self, changed_paths: set[Path]) -> None:
		plan = self._build_plan(changed_paths)
		if plan is None:
			return
		await self.reload(plan)

	def _filter_paths(self, paths: set[Path]) -> set[Path]:
		allowed_ext = {".py", ".pyi", ".toml", ".yaml", ".yml", ".json"}
		filtered: set[Path] = set()
		for path in paths:
			if path.suffix not in allowed_ext:
				continue
			if self._is_excluded(path):
				continue
			filtered.add(path)
		return filtered

	def _is_excluded(self, path: Path) -> bool:
		posix = path.as_posix()
		for pattern in self.exclude_globs:
			if fnmatch.fnmatch(posix, pattern):
				return True
			for root in self.watch_roots:
				try:
					rel = path.relative_to(root)
				except ValueError:
					continue
				if fnmatch.fnmatch(rel.as_posix(), pattern):
					return True
		return False

	def _build_plan(self, changed_paths: set[Path]) -> HotReloadPlan | None:
		if not changed_paths:
			return None

		python_paths = {p for p in changed_paths if p.suffix in {".py", ".pyi"}}
		config_paths = changed_paths - python_paths

		requires_client_reload = False
		requires_process_reload = False
		reason: str | None = None

		index = self._module_index
		changed_modules: set[str] = set()
		for path in python_paths:
			info = index.resolve_module(path)
			if info is None:
				if _is_under_any(path, index.watch_roots):
					requires_process_reload = True
					reason = reason or "untracked module"
				continue
			changed_modules.add(info.name)

		if config_paths:
			requires_process_reload = True
			reason = reason or "config change"

		dirty_modules: set[str] = set()
		if changed_modules:
			try:
				graph = ModuleGraph.build_from_ast(index)
				dirty_modules = graph.dirty_set(changed_modules)
			except Exception as exc:
				requires_process_reload = True
				reason = reason or f"module graph error: {exc}"

		new_app = None
		new_signature = None
		app_file = env.pulse_app_file
		if app_file and any(path == Path(app_file).resolve() for path in python_paths):
			try:
				new_app = load_app_for_hot_reload(env.pulse_app_file or "")
				new_signature = AppSignature.from_app(new_app.app)
				current_signature = AppSignature.from_app(self.app)
				requires_client, requires_process, app_reason = compare_app_signatures(
					current_signature,
					new_signature,
				)
				requires_client_reload = requires_client_reload or requires_client
				requires_process_reload = requires_process_reload or requires_process
				reason = reason or app_reason
			except Exception as exc:
				requires_process_reload = True
				reason = reason or f"app reload error: {exc}"

		module_list = (
			sorted(dirty_modules) if dirty_modules else sorted(changed_modules)
		)

		return HotReloadPlan(
			changed_paths=changed_paths,
			python_paths=python_paths,
			module_names=module_list,
			requires_client_reload=requires_client_reload,
			requires_process_reload=requires_process_reload,
			reason=reason,
			new_app=new_app.app if new_app else None,
			new_signature=new_signature,
			app_module_name=new_app.module_name if new_app else None,
			app_var=new_app.app_var if new_app else None,
		)

	async def reload(self, plan: HotReloadPlan) -> None:
		self.app._hot_reload_in_progress = True
		for render in self.app.render_sessions.values():
			render.pause_updates()

		try:
			clear_function_cache()
			clear_import_registry()
			clear_asset_registry()
			importlib.invalidate_caches()

			reload_error = None
			reloaded = False
			reload_failed = False
			if plan.module_names:
				try:
					self._reload_modules(plan.module_names)
					reloaded = True
				except Exception as exc:
					reload_error = exc

			if reload_error is not None:
				plan.requires_process_reload = True
				reload_failed = True
				self.last_error = HotReloadError(
					message="module reload failed",
					exc=reload_error,
					traceback=traceback.format_exc(),
				)
				logger.exception("Hot reload module reload failed")
				# Skip patch steps; continue to process reload fallback.

			if reloaded and not reload_failed:
				self._module_index = ModuleIndex.from_sys_modules(self.watch_roots)
				set_active_module_index(self._module_index)
				self._refresh_component_deps(set(plan.module_names))
				self._refresh_state_instances()

			if plan.new_app is not None:
				updated_app = (
					self._resolve_runtime_app(plan.app_module_name, plan.app_var)
					or plan.new_app
				)
				self.app.routes = updated_app.routes
				self.app.codegen.routes = updated_app.routes
				self.app.not_found = updated_app.not_found
				for render in self.app.render_sessions.values():
					render.routes = self.app.routes

			if reloaded and not reload_failed:
				try:
					self.app.run_codegen(
						self.app.server_address,
						self.app.internal_server_address,
					)
				except Exception as exc:
					plan.requires_process_reload = True
					self.last_error = HotReloadError(
						message="codegen failed",
						exc=exc,
						traceback=traceback.format_exc(),
					)
					logger.exception("Hot reload codegen failed")
				self._rerender_sessions()

			if plan.requires_client_reload:
				self._broadcast_reload()

			if plan.requires_process_reload:
				self._broadcast_reload()
				self._trigger_process_reload()
		finally:
			for render in self.app.render_sessions.values():
				render.resume_updates()
			self.app._hot_reload_in_progress = False

	def _rerender_sessions(self) -> None:
		with hot_reload_context(True):
			for render in self.app.render_sessions.values():
				for path, mount in list(render.route_mounts.items()):
					if mount.state != "active":
						continue
					try:
						new_route = render.routes.find(path)
						mount.route.pulse_route = new_route
						new_root = mount.route.pulse_route.render()
						ops = mount.tree.rerender(new_root)
						if ops:
							render.send(
								{
									"type": "vdom_update",
									"path": path,
									"ops": ops,
								}
							)
					except Exception as exc:
						render.report_error(path, "render", exc, {"hot_reload": True})
				try:
					render.flush()
				except Exception as exc:
					render.report_error("/", "effect", exc, {"hot_reload": True})

	def _broadcast_reload(self) -> None:
		for render in self.app.render_sessions.values():
			render.send({"type": "reload"})

	def _trigger_process_reload(self) -> None:
		if self.trigger_path is not None:
			try:
				self.trigger_path.parent.mkdir(parents=True, exist_ok=True)
				self.trigger_path.touch()
				return
			except Exception:
				logger.exception("Failed to touch hot reload trigger file")
		raise SystemExit(3)

	def _reload_modules(self, module_names: list[str]) -> None:
		graph = ModuleGraph.build_from_ast(self._module_index)
		order = _topological_sort(graph.deps, module_names)
		for name in order:
			module = sys.modules.get(name)
			if module is None:
				continue
			importlib.reload(module)

	def _resolve_runtime_app(
		self, module_name: str | None, app_var: str | None
	) -> Any | None:
		if not module_name or not app_var:
			return None
		module = sys.modules.get(module_name)
		if module is None:
			return None
		app_candidate = getattr(module, app_var, None)
		if app_candidate is None:
			return None
		from pulse.app import App

		if not isinstance(app_candidate, App):
			return None
		return app_candidate

	def _refresh_component_deps(self, dirty_modules: set[str]) -> None:
		from pulse.component import COMPONENT_BY_ID
		from pulse.hot_reload.deps import compute_component_deps, get_unknown_deps

		for component in COMPONENT_BY_ID.values():
			module_name = getattr(component.raw_fn, "__module__", "")
			if component.unknown_deps:
				pass
			elif component.deps.intersection(dirty_modules):
				pass
			elif module_name in dirty_modules:
				pass
			elif dirty_modules:
				continue
			deps = compute_component_deps(component.fn)
			component.deps = deps
			component.unknown_deps = get_unknown_deps(component.fn)
			signature, digest = compute_component_signature_data(component.raw_fn)
			component.signature_hash = digest
			component.signature = signature

	def _refresh_state_instances(self) -> None:
		from pulse.hooks.state import StateHookState

		for render in self.app.render_sessions.values():
			for state in render._global_states.values():
				self._refresh_state_instance(state)
			for mount in render.route_mounts.values():
				self._collect_state_instances(mount.tree.element, StateHookState)

	def _collect_state_instances(self, node: Any, hook_state_type: type[Any]) -> None:
		from pulse.hooks.init import InitState
		from pulse.hooks.setup import SetupHookState
		from pulse.state import State
		from pulse.transpiler.nodes import Element, PulseNode

		if isinstance(node, PulseNode):
			hooks = node.hooks
			if hooks is not None:
				namespace = hooks.namespaces.get("pulse:core.state")
				if namespace is not None:
					for hook_state in namespace.states.values():
						if isinstance(hook_state, hook_state_type):
							for state in hook_state.instances.values():
								self._refresh_state_instance(state)
				init_namespace = hooks.namespaces.get("init_storage")
				if init_namespace is not None:
					for hook_state in init_namespace.states.values():
						if isinstance(hook_state, InitState):
							for entry in hook_state.storage.values():
								for value in entry.get("vars", {}).values():
									if isinstance(value, State):
										self._refresh_state_instance(value)
				setup_namespace = hooks.namespaces.get("pulse:core.setup")
				if setup_namespace is not None:
					for hook_state in setup_namespace.states.values():
						if isinstance(hook_state, SetupHookState):
							value = hook_state.value
							if isinstance(value, State):
								self._refresh_state_instance(value)
			if node.contents is not None:
				self._collect_state_instances(node.contents, hook_state_type)
			return
		if isinstance(node, Element):
			props = node.props_dict()
			for value in props.values():
				if isinstance(value, (Element, PulseNode)):
					self._collect_state_instances(value, hook_state_type)
			for child in node.children or []:
				if isinstance(child, (Element, PulseNode)):
					self._collect_state_instances(child, hook_state_type)

	def _refresh_state_instance(self, state: Any) -> None:
		from pulse.state import State

		if not isinstance(state, State):
			return
		module_name = getattr(state.__class__, "__module__", "")
		class_name = getattr(state.__class__, "__name__", "")
		module = sys.modules.get(module_name)
		if module is None:
			return
		new_cls = module.__dict__.get(class_name)
		if new_cls is None:
			return
		if new_cls is state.__class__:
			return
		if not isinstance(new_cls, type) or not issubclass(new_cls, State):
			return
		try:
			state.__class__ = new_cls
			state._refresh_reactive_layout()  # pyright: ignore[reportPrivateUsage]
		except Exception:
			logger.exception("Failed to refresh State instance %s", class_name)


# -------------------------- helpers --------------------------


def compare_app_signatures(
	current: AppSignature, new: AppSignature
) -> tuple[bool, bool, str | None]:
	requires_process = False
	requires_client = False
	reason: str | None = None

	if current.mode != new.mode:
		requires_process = True
		reason = reason or "mode changed"
	if current.api_prefix != new.api_prefix:
		requires_process = True
		reason = reason or "api prefix changed"
	if current.cookie_signature != new.cookie_signature:
		requires_process = True
		reason = reason or "cookie config changed"
	if current.session_signature != new.session_signature:
		requires_process = True
		reason = reason or "session config changed"
	if current.middleware_signature != new.middleware_signature:
		requires_process = True
		reason = reason or "middleware changed"
	if current.plugin_signature != new.plugin_signature:
		requires_process = True
		reason = reason or "plugins changed"

	if current.routes_signature != new.routes_signature:
		requires_client = True
		reason = reason or "routes changed"
	if (
		current.codegen_web_dir != new.codegen_web_dir
		or current.codegen_pulse_dir != new.codegen_pulse_dir
	):
		requires_client = True
		reason = reason or "codegen config changed"

	return requires_client, requires_process, reason


def load_app_for_hot_reload(target: str) -> Any:
	from pulse.app import App
	from pulse.cli.helpers import parse_app_target
	from pulse.cli.models import AppLoadResult

	parsed = parse_app_target(target)
	module_name = parsed["module_name"]
	app_var = parsed["app_var"]
	file_path = parsed["file_path"]
	server_cwd = parsed["server_cwd"]

	module: ModuleType | None = None
	unique_name = f"{module_name}.__hot_reload__"
	try:
		if file_path is None:
			spec = importlib_util.find_spec(module_name)
			if spec is None or spec.origin is None:
				raise RuntimeError(f"Unable to find module: {module_name}")
			file_path = Path(spec.origin)

		sys.path.insert(0, str(file_path.parent.absolute()))
		spec: ModuleSpec | None = importlib_util.spec_from_file_location(
			unique_name, file_path
		)
		if spec is None or spec.loader is None:
			raise RuntimeError(f"Unable to load module from {file_path}")
		module = importlib_util.module_from_spec(spec)
		module.__package__ = module_name.rpartition(".")[0]
		sys.modules[unique_name] = module
		loader = spec.loader
		loader.exec_module(module)
	finally:
		if file_path is not None:
			path_str = str(file_path.parent.absolute())
			if path_str in sys.path:
				sys.path.remove(path_str)
		sys.modules.pop(unique_name, None)

	if not hasattr(module, app_var):
		raise RuntimeError(f"App variable '{app_var}' not found in {module_name}")
	app_candidate = getattr(module, app_var)
	if not isinstance(app_candidate, App):
		raise RuntimeError(f"'{app_var}' in {module_name} is not a pulse.App instance")

	return AppLoadResult(
		target=target,
		mode=parsed["mode"],
		app=app_candidate,
		module_name=module_name,
		app_var=app_var,
		app_file=file_path.resolve() if file_path else None,
		app_dir=file_path.parent.resolve() if file_path else None,
		server_cwd=server_cwd,
	)


# -------------------------- internal helpers --------------------------


def _paths_from_changes(changes: Any) -> set[Path]:
	paths: set[Path] = set()
	for change in changes:
		try:
			path = Path(change[1])
			paths.add(path.resolve())
		except Exception:
			continue
	return paths


def _is_site_package(path: Path) -> bool:
	parts = {p.lower() for p in path.parts}
	return "site-packages" in parts or "dist-packages" in parts


def _is_under_any(path: Path, roots: list[Path]) -> bool:
	for root in roots:
		try:
			path.relative_to(root)
		except ValueError:
			continue
		return True
	return False


def _parse_imports(path: Path, module_name: str, index: ModuleIndex) -> set[str]:
	import ast

	try:
		source = path.read_text()
	except Exception as exc:
		raise RuntimeError(f"Unable to read {path}: {exc}") from exc
	try:
		ast_tree = ast.parse(source)
	except Exception as exc:
		raise RuntimeError(f"Unable to parse {path}: {exc}") from exc

	imports: set[str] = set()
	for node in ast_tree.body:
		if isinstance(node, ast.Import):
			for alias in node.names:
				imports.add(alias.name)
		if isinstance(node, ast.ImportFrom):
			imports.update(_resolve_import_from(node, module_name))

	filtered: set[str] = set()
	for name in imports:
		info = index.by_name.get(name)
		if info is None:
			continue
		if not info.reloadable:
			continue
		filtered.add(name)
	return filtered


def _resolve_import_from(node: Any, module_name: str) -> set[str]:
	level = node.level or 0
	parts = module_name.split(".")
	if level:
		if len(parts) < level:
			return set()
		parts = parts[:-level]
	module = node.module
	if module:
		parts += module.split(".")
	base = ".".join([p for p in parts if p])
	resolved: set[str] = set()
	if base:
		resolved.add(base)
	for alias in node.names:
		if alias.name == "*":
			continue
		if base:
			resolved.add(f"{base}.{alias.name}")
	return resolved


def _topological_sort(deps: dict[str, set[str]], modules: list[str]) -> list[str]:
	remaining = {m for m in modules}
	incoming: dict[str, int] = {m: 0 for m in remaining}
	adj: dict[str, set[str]] = {m: set() for m in remaining}
	for mod in remaining:
		for dep in deps.get(mod, set()):
			if dep in remaining:
				incoming[mod] += 1
				adj.setdefault(dep, set()).add(mod)

	queue = [mod for mod, count in incoming.items() if count == 0]
	order: list[str] = []
	while queue:
		mod = queue.pop()
		order.append(mod)
		for dependent in adj.get(mod, set()):
			incoming[dependent] -= 1
			if incoming[dependent] == 0:
				queue.append(dependent)
	if len(order) != len(remaining):
		raise RuntimeError("Module dependency cycle detected")
	return order


def _routes_signature(routes: list[Any]) -> tuple[Any, ...]:
	out: list[Any] = []
	for route in routes:
		kind = "layout" if route.__class__.__name__ == "Layout" else "route"
		children = _routes_signature(list(route.children or []))
		out.append((kind, route.unique_path(), bool(route.dev), children))
	return tuple(out)


def _middleware_signature(app: Any) -> tuple[str, ...]:
	stack = getattr(app.middleware, "_middlewares", [])
	return tuple(_qualname(mw) for mw in stack)


def _plugin_signature(app: Any) -> tuple[str, ...]:
	return tuple(_qualname(plugin) for plugin in app.plugins)


def _cookie_signature(app: Any) -> tuple[Any, ...]:
	cookie = app.cookie
	return (
		cookie.__class__.__module__,
		cookie.__class__.__name__,
		cookie.name,
		cookie.samesite,
		cookie.max_age_seconds,
	)


def _session_signature(app: Any) -> tuple[Any, ...]:
	store = app.session_store
	cls = store.__class__
	if cls.__name__ == "CookieSessionStore":
		return (
			cls.__module__,
			cls.__name__,
			getattr(store, "salt", None),
			getattr(store, "digestmod", None),
			getattr(store, "max_cookie_bytes", None),
		)
	return (cls.__module__, cls.__name__)


def _qualname(obj: Any) -> str:
	cls = obj.__class__
	return f"{cls.__module__}.{cls.__name__}"


def hot_reload_enabled() -> bool:
	value = os.environ.get(ENV_PULSE_HOT_RELOAD)
	if value is None:
		return env.pulse_env == "dev"
	return value not in {"0", "false", "False"}


def hot_reload_dirs() -> list[Path]:
	raw = os.environ.get(ENV_PULSE_HOT_RELOAD_DIRS, "")
	if not raw:
		return []
	return [Path(p) for p in raw.split(os.pathsep) if p]


def hot_reload_excludes() -> list[str]:
	raw = os.environ.get(ENV_PULSE_HOT_RELOAD_EXCLUDES, "")
	if not raw:
		return []
	return [p for p in raw.split(os.pathsep) if p]


def hot_reload_trigger() -> Path | None:
	raw = os.environ.get(ENV_PULSE_HOT_RELOAD_TRIGGER)
	if not raw:
		return None
	return Path(raw)


def build_hot_reload_manager(app: Any) -> HotReloadManager | None:
	if env.pulse_env != "dev":
		return None
	if not hot_reload_enabled():
		return None
	watch_roots = _compute_watch_roots(app)
	excludes = _compute_excludes(app)
	trigger = hot_reload_trigger()
	manager = HotReloadManager(
		app=app,
		watch_roots=watch_roots,
		exclude_globs=excludes,
		trigger_path=trigger,
	)
	return manager


def _compute_watch_roots(app: Any) -> list[Path]:
	roots: set[Path] = set()
	app_dir = env.pulse_app_dir
	if app_dir:
		try:
			roots.add(Path(app_dir).resolve())
		except Exception:
			roots.add(Path(app_dir))

	cwd = Path.cwd()
	for module in sys.modules.values():
		file_attr = getattr(module, "__file__", None)
		if not file_attr:
			continue
		path = Path(file_attr)
		if path.suffix == ".pyc":
			path = path.with_suffix(".py")
		try:
			resolved = path.resolve()
		except Exception:
			continue
		if _is_site_package(resolved):
			continue
		try:
			resolved.relative_to(cwd)
		except ValueError:
			continue
		roots.add(resolved.parent)

	for extra in hot_reload_dirs():
		try:
			roots.add(extra.resolve())
		except Exception:
			continue

	return sorted({root for root in roots if root.exists()})


def _compute_excludes(app: Any) -> list[str]:
	defaults = [
		"**/__pycache__/**",
		"**/.git/**",
		"**/.venv/**",
		"**/node_modules/**",
		"**/.pulse/**",
	]
	web_root = app.codegen.cfg.web_root
	pulse_dir = app.codegen.cfg.pulse_dir
	pulse_path = (web_root / "app" / pulse_dir).as_posix()
	defaults.append(f"{pulse_path}/**")
	defaults.extend(hot_reload_excludes())
	return defaults


__all__ = [
	"AppSignature",
	"HotReloadManager",
	"HotReloadPlan",
	"ModuleGraph",
	"ModuleIndex",
	"ModuleInfo",
	"build_hot_reload_manager",
	"compare_app_signatures",
	"hot_reload_enabled",
]
