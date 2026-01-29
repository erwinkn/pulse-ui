import os
import sys
from importlib import util as importlib_util
from pathlib import Path
from types import ModuleType

import pulse as ps
from pulse.cli.cmd import (
	_configure_hot_reload_env,  # pyright: ignore[reportPrivateUsage]
	build_uvicorn_command,
)
from pulse.cli.helpers import load_app_from_target
from pulse.cli.models import AppLoadResult
from pulse.component import COMPONENT_BY_ID
from pulse.env import (
	ENV_PULSE_HOT_RELOAD,
	ENV_PULSE_HOT_RELOAD_DIRS,
	ENV_PULSE_HOT_RELOAD_EXCLUDES,
	ENV_PULSE_HOT_RELOAD_TRIGGER,
	env,
)
from pulse.hot_reload import AppSignature, ModuleIndex, compare_app_signatures
from pulse.hot_reload.context import hot_reload_context
from pulse.renderer import RenderTree
from pulse.transpiler.nodes import PulseNode


def test_hot_reload_env_sets_trigger(tmp_path: Path):
	app_file = tmp_path / "app.py"
	app_file.write_text("from pulse import App\napp = App()\n")
	app_ctx = load_app_from_target(str(app_file))
	web_root = tmp_path / "web"
	web_root.mkdir()

	original = {
		ENV_PULSE_HOT_RELOAD: os.environ.get(ENV_PULSE_HOT_RELOAD),
		ENV_PULSE_HOT_RELOAD_DIRS: os.environ.get(ENV_PULSE_HOT_RELOAD_DIRS),
		ENV_PULSE_HOT_RELOAD_EXCLUDES: os.environ.get(ENV_PULSE_HOT_RELOAD_EXCLUDES),
		ENV_PULSE_HOT_RELOAD_TRIGGER: os.environ.get(ENV_PULSE_HOT_RELOAD_TRIGGER),
	}

	try:
		trigger = _configure_hot_reload_env(
			app_ctx=app_ctx,
			web_root=web_root,
			hot_reload=True,
			hot_reload_dirs=["extra"],
			hot_reload_excludes=["**/ignore/**"],
		)
		assert trigger is not None
		assert trigger == web_root / ".pulse" / "hot-reload.trigger"
		assert trigger.exists()
		assert env.pulse_hot_reload is True
		assert env.pulse_hot_reload_dirs == ["extra"]
		assert env.pulse_hot_reload_excludes == ["**/ignore/**"]
		gitignore = web_root / ".gitignore"
		assert gitignore.exists()
		assert ".pulse/" in gitignore.read_text()
	finally:
		for key, value in original.items():
			if value is None:
				os.environ.pop(key, None)
			else:
				os.environ[key] = value
		sys.modules.pop(app_ctx.module_name, None)


def test_build_uvicorn_command_hot_reload(tmp_path: Path):
	app = ps.App()
	app_ctx = AppLoadResult(
		target="dummy",
		mode="module",
		app=app,
		module_name="dummy",
		app_var="app",
		app_file=None,
		app_dir=tmp_path,
		server_cwd=tmp_path,
	)
	trigger = tmp_path / ".pulse" / "hot-reload.trigger"

	spec = build_uvicorn_command(
		app_ctx=app_ctx,
		address="localhost",
		port=8000,
		reload_enabled=True,
		hot_reload_enabled=True,
		hot_reload_trigger=trigger,
		extra_args=[],
		dev_secret=None,
		server_only=False,
		web_root=tmp_path,
	)

	args = spec.args
	assert "--reload" in args
	assert "--reload-include" in args
	idx = args.index("--reload-include")
	assert args[idx + 1] == trigger.name
	assert "--reload-exclude" in args
	assert "*.py" in args
	assert "--reload-dir" in args
	assert str(trigger.parent) in args


def test_module_index_excludes_site_packages(tmp_path: Path):
	local_dir = tmp_path / "local"
	site_dir = tmp_path / "site-packages"
	local_dir.mkdir()
	site_dir.mkdir()

	local_file = local_dir / "mod_local.py"
	site_file = site_dir / "mod_site.py"
	local_file.write_text("x = 1\n")
	site_file.write_text("y = 2\n")

	def load_module(name: str, path: Path) -> ModuleType:
		spec = importlib_util.spec_from_file_location(name, path)
		assert spec is not None
		module = importlib_util.module_from_spec(spec)
		assert spec and spec.loader
		sys.modules[name] = module
		spec.loader.exec_module(module)
		return module

	try:
		load_module("mod_local", local_file)
		load_module("mod_site", site_file)
		index = ModuleIndex.from_sys_modules([tmp_path])
		assert "mod_local" in index.by_name
		assert "mod_site" not in index.by_name
		assert index.by_name["mod_local"].reloadable is True
	finally:
		sys.modules.pop("mod_local", None)
		sys.modules.pop("mod_site", None)


def test_app_signature_diff_flags_route_change():
	app_a = ps.App(routes=[ps.Route("/", ps.component(lambda: ps.div("a")))])
	app_b = ps.App(routes=[ps.Route("/next", ps.component(lambda: ps.div("b")))])
	current = AppSignature.from_app(app_a)
	new = AppSignature.from_app(app_b)
	client, process, _ = compare_app_signatures(current, new)
	assert client is True
	assert process is False


def test_renderer_fast_refresh_reuses_hooks():
	def render():
		return ps.div("hello")

	first = PulseNode(fn=render, component_id="test:Comp", signature_hash="sig-a")
	tree = RenderTree(first)
	tree.render()
	assert isinstance(tree.element, PulseNode)
	prev_hooks = tree.element.hooks

	with hot_reload_context(True):
		updated = PulseNode(fn=render, component_id="test:Comp", signature_hash="sig-a")
		tree.rerender(updated)

	assert tree.element.hooks is prev_hooks


def test_renderer_fast_refresh_remounts_on_signature_change():
	def render():
		return ps.div("hello")

	first = PulseNode(fn=render, component_id="test:Comp", signature_hash="sig-a")
	tree = RenderTree(first)
	tree.render()
	assert isinstance(tree.element, PulseNode)
	prev_hooks = tree.element.hooks

	with hot_reload_context(True):
		updated = PulseNode(fn=render, component_id="test:Comp", signature_hash="sig-b")
		tree.rerender(updated)

	assert tree.element.hooks is not prev_hooks
	assert prev_hooks.namespaces == {}


def test_component_refresh_reuses_instance():
	@ps.component
	def Demo():
		return ps.div("a")

	first = Demo
	component_id = first.component_id
	old_raw = first.raw_fn
	old_fn = first.fn

	def DemoNext():
		return ps.div("b")

	DemoNext.__name__ = "Demo"
	DemoNext.__qualname__ = first.raw_fn.__qualname__
	DemoNext.__module__ = first.raw_fn.__module__
	Demo = ps.component(DemoNext)

	second = Demo
	try:
		assert first is second
		assert first.raw_fn is not old_raw
		assert first.fn is not old_fn
	finally:
		COMPONENT_BY_ID.pop(component_id, None)


def test_hot_reload_preserves_init_and_state():
	init_values: list[dict[str, int]] = []
	state_values: list["CounterState"] = []

	class CounterState(ps.State):
		value: int

		def __init__(self) -> None:
			self.value = 0

	@ps.component
	def Demo():  # pyright: ignore[reportRedeclaration]
		with ps.init():
			init_value = {"count": 0}
		state = ps.state(CounterState)
		init_values.append(init_value)
		state_values.append(state)
		return ps.div(f"{init_value['count']}:{state.value}")

	tree = RenderTree(Demo())
	tree.render()

	init_val = init_values[-1]
	state_val = state_values[-1]
	init_val["count"] = 3
	state_val.value = 7

	@ps.component
	def Demo():
		with ps.init():
			init_value = {"count": 0}
		state = ps.state(CounterState)
		init_values.append(init_value)
		state_values.append(state)
		return ps.div("changed")

	with hot_reload_context(True):
		tree.rerender(Demo())

	assert init_values[-1] is init_val
	assert init_val["count"] == 3
	assert state_values[-1] is state_val
	assert state_val.value == 7


def test_reload_preserves_init_without_hot_reload_context():
	init_values: list[dict[str, int]] = []

	@ps.component
	def Demo():  # pyright: ignore[reportRedeclaration]
		with ps.init():
			init_value = {"count": 0}
		init_values.append(init_value)
		return ps.div(str(init_value["count"]))

	tree = RenderTree(Demo())
	tree.render()

	init_val = init_values[-1]
	init_val["count"] = 9

	@ps.component
	def Demo():
		with ps.init():
			init_value = {"count": 0}
		init_values.append(init_value)
		return ps.div("changed")

	tree.rerender(Demo())

	assert init_values[-1] is init_val
	assert init_val["count"] == 9


def test_prerender_preserves_init_on_refresh():
	init_values: list[dict[str, int]] = []

	@ps.component
	def Demo():  # pyright: ignore[reportRedeclaration]
		with ps.init():
			init_value = {"count": 0}
		init_values.append(init_value)
		return ps.div(str(init_value["count"]))

	tree = RenderTree(Demo())
	tree.render()

	init_val = init_values[-1]
	init_val["count"] = 2

	@ps.component
	def Demo():
		with ps.init():
			init_value = {"count": 0}
		init_values.append(init_value)
		return ps.div("changed")

	tree.render(Demo())

	assert init_values[-1] is init_val
	assert init_val["count"] == 2
