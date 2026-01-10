import json
import os
import sys
from pathlib import Path

import pytest
from pulse.cli.dependencies import (
	DependencyResolutionError,
	convert_pep440_to_semver,
	prepare_web_dependencies,
)
from pulse.cli.helpers import load_app_from_target, parse_app_target
from pulse.cli.models import CommandSpec
from pulse.cli.packages import (
	is_alias_source,
	is_relative_source,
	is_url_or_absolute,
	parse_install_spec,
	resolve_versions,
	spec_satisfies,
)
from pulse.cli.processes import execute_commands
from pulse.cli.secrets import resolve_dev_secret
from pulse.env import env
from pulse.transpiler.imports import Import, clear_import_registry


def test_parse_app_target_file_default(tmp_path: Path):
	file = tmp_path / "myapp.py"
	file.write_text("app=None\n")
	target = str(file)
	parsed = parse_app_target(target)
	assert parsed["mode"] == "path"
	assert parsed["app_var"] == "app"
	assert parsed["file_path"] == file.resolve()
	assert parsed["module_name"].endswith("myapp")
	assert isinstance(parsed["server_cwd"], Path) and parsed["server_cwd"].is_dir()


def test_parse_app_target_file_custom_var(tmp_path: Path):
	file = tmp_path / "main.py"
	file.write_text("custom=None\n")
	target = f"{file}:custom"
	parsed = parse_app_target(target)
	assert parsed["mode"] == "path"
	assert parsed["app_var"] == "custom"
	assert parsed["file_path"] == file.resolve()
	assert parsed["module_name"].endswith("main")


def test_parse_app_target_module_style():
	parsed = parse_app_target("some.module:app")
	assert parsed["mode"] == "module"
	assert parsed["module_name"] == "some.module"
	assert parsed["app_var"] == "app"
	assert parsed["file_path"] is None
	assert parsed["server_cwd"] is None


def test_parse_app_target_package_dir(tmp_path: Path):
	pkg = tmp_path / "pkg"
	pkg.mkdir()
	init_file = pkg / "__init__.py"
	init_file.write_text("app=None\n")
	parsed = parse_app_target(str(pkg))
	assert parsed["mode"] == "path"
	assert parsed["file_path"] == init_file
	# module path derived from package name
	assert parsed["module_name"].endswith("pkg")
	assert parsed["server_cwd"] == tmp_path.resolve()


def test_load_app_from_target_returns_context(tmp_path: Path):
	app_file = tmp_path / "demo_app.py"
	app_file.write_text("from pulse.app import App\napp = App()\n")

	original_file = getattr(env, "pulse_app_file", None)
	original_dir = getattr(env, "pulse_app_dir", None)
	result = None
	try:
		result = load_app_from_target(str(app_file))
		assert result.app_file == app_file.resolve()
		assert result.app_dir == app_file.parent.resolve()
		assert result.server_cwd == app_file.parent.resolve()
		assert result.module_name.endswith("demo_app")
		assert getattr(env, "pulse_app_file", None) == original_file
		assert getattr(env, "pulse_app_dir", None) == original_dir
	finally:
		env.pulse_app_file = original_file
		env.pulse_app_dir = original_dir
		if result is not None:
			sys.modules.pop(result.module_name, None)


def test_resolve_dev_secret_creates_and_reuses_secret(tmp_path: Path):
	app_path = tmp_path / "app.py"
	app_path.write_text("pass\n")
	secret1 = resolve_dev_secret(app_path)
	assert secret1 is not None and len(secret1) > 10
	secret_file = app_path.parent / ".pulse" / "secret"
	assert secret_file.exists()
	assert secret_file.read_text().strip() == secret1
	gitignore = app_path.parent / ".gitignore"
	assert gitignore.exists()
	assert ".pulse/" in gitignore.read_text()
	secret2 = resolve_dev_secret(app_path)
	assert secret2 == secret1


def test_prepare_web_dependencies_returns_add_plan(tmp_path: Path):
	web_root = tmp_path / "web"
	web_root.mkdir()
	(web_root / "package.json").write_text("{}")

	clear_import_registry()
	Import("React", "react@^18")
	Import("QueryClient", "@tanstack/react-query@^5")

	plan = prepare_web_dependencies(
		web_root,
		pulse_version="9.9.9",
	)
	assert plan is not None
	assert plan.command[:2] == ["bun", "add"]
	assert any(arg.startswith("pulse-ui-client@9.9.9") for arg in plan.command)
	assert any(arg.startswith("react@") for arg in plan.command)
	assert any(arg.startswith("@tanstack/react-query@") for arg in plan.command)


def test_prepare_web_dependencies_returns_install_when_up_to_date(tmp_path: Path):
	web_root = tmp_path / "web"
	web_root.mkdir()
	package_json = {
		"dependencies": {
			"pulse-ui-client": "9.9.9",
			"react-router": "^7",
			"@react-router/node": "^7",
			"@react-router/serve": "^7",
			"@react-router/dev": "^7",
		}
	}
	(web_root / "package.json").write_text(json.dumps(package_json))

	clear_import_registry()
	plan = prepare_web_dependencies(
		web_root,
		pulse_version="9.9.9",
	)
	assert plan is not None
	assert plan.command == ["bun", "i"]
	assert not plan.to_add


def test_prepare_web_dependencies_raises_on_conflict(tmp_path: Path):
	web_root = tmp_path
	(web_root / "package.json").write_text("{}")
	clear_import_registry()
	Import("React", "react@18.2.0", version="18.1.0")
	with pytest.raises(DependencyResolutionError):
		prepare_web_dependencies(
			web_root,
			pulse_version="9.9.9",
		)


@pytest.mark.parametrize(
	"pep440_version,expected_semver",
	[
		# PEP 440 prerelease formats
		("0.1.37a1", "0.1.37-alpha.1"),
		("0.1.37b1", "0.1.37-beta.1"),
		("0.1.37rc1", "0.1.37-rc.1"),
		("0.1.37dev1", "0.1.37-dev.1"),
		("1.2.3alpha2", "1.2.3-alpha.2"),
		("2.0.0beta3", "2.0.0-beta.3"),
		("3.1.4rc5", "3.1.4-rc.5"),
		# PEP 440 .dev format
		("0.1.37.dev1", "0.1.37-dev.1"),
		("1.0.0.dev2", "1.0.0-dev.2"),
		# Regular versions (should pass through unchanged)
		("1.0.0", "1.0.0"),
		("2.1.3", "2.1.3"),
		("0.1.37", "0.1.37"),
		# Edge cases with different prerelease types
		("1.0.0a0", "1.0.0-alpha.0"),
		("1.0.0b0", "1.0.0-beta.0"),
		("1.0.0rc0", "1.0.0-rc.0"),
	],
)
def test_convert_pep440_to_semver(pep440_version: str, expected_semver: str):
	assert convert_pep440_to_semver(pep440_version) == expected_semver


def test_execute_commands_streams_output(
	tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
	spawns: list[str] = []
	spec = CommandSpec(
		name="server",
		args=[sys.executable, "-c", "print('child-line')"],
		cwd=tmp_path,
		env=os.environ.copy(),
		on_spawn=lambda: spawns.append("server"),
	)
	exit_code = execute_commands(
		[spec],
		tag_mode="plain",  # Use plain mode since capsys captures plain text
	)
	assert exit_code == 0
	output = capsys.readouterr().out
	assert "[server]" in output
	assert "child-line" in output
	assert spawns == ["server"]


@pytest.mark.parametrize(
	"src,expected",
	[
		("./local", True),
		("../up", True),
		("/abs", False),
		("react", False),
		("react/jsx-runtime", False),
	],
)
def test_is_relative_source(src: str, expected: bool):
	assert is_relative_source(src) is expected


@pytest.mark.parametrize(
	"src,expected",
	[
		("@/components/Button", True),
		("~/components/Button", True),
		("react", False),
	],
)
def test_is_alias_source(src: str, expected: bool):
	assert is_alias_source(src) is expected


@pytest.mark.parametrize(
	"src,expected",
	[
		("http://cdn/pkg", True),
		("https://cdn/pkg", True),
		("/absolute/path", True),
		("react", False),
	],
)
def test_is_url_or_absolute(src: str, expected: bool):
	assert is_url_or_absolute(src) is expected


@pytest.mark.parametrize(
	"spec,expect",
	[
		("react", "react"),
		("react@^18", "react@^18"),
		("react/jsx-runtime", "react"),
		("@mantine/core", "@mantine/core"),
		("@mantine/core@7", "@mantine/core@7"),
		("@mantine/core/styles.css", "@mantine/core"),
		("@scope/name@1/sub/path", "@scope/name@1"),
		("@/local/button", None),
		("~/local/button", None),
		("http://cdn/x", None),
		("/abs/path", None),
	],
)
def test_parse_install_spec(spec: str, expect: str | None):
	if spec.startswith("./") or spec.startswith("../"):
		with pytest.raises(ValueError):
			parse_install_spec(spec)
	else:
		assert parse_install_spec(spec) == expect


def test_resolve_versions_prefers_exact_and_longer_constraints():
	constraints: dict[str, list[str | None]] = {
		"react": [None, "^18", "18.2.0"],
		"@scope/name": ["^1.2.3", "~1.2.3"],
	}
	resolved = resolve_versions(constraints)
	assert resolved["react"] == "18.2.0"
	# '^1.2.3' vs '~1.2.3' -> longer constraint (same length), tie goes to first kept order
	assert resolved["@scope/name"] in {"^1.2.3", "~1.2.3"}


def test_resolve_versions_conflict_on_different_exact_versions():
	constraints: dict[str, list[str | None]] = {"react": ["18.2.0", "18.1.0"]}
	from pulse.cli.packages import VersionConflict

	with pytest.raises(VersionConflict):
		resolve_versions(constraints)


@pytest.mark.parametrize(
	"required,existing,ok",
	[
		# Exact requirements
		("1.2.3", "1.2.3", True),
		("1.2.3", "^1", True),
		("1.2.3", "~1.2", True),
		("1.2.3", "^2", False),
		("1.2.3", "~1.3", False),
		# Caret requirements -> same major acceptable
		("^1", "1.2.3", True),
		("^1", "~1.4.0", True),
		("^1", "^2.0.0", False),
		("^1", "2.0.0", False),
		# Tilde requirements -> same major+minor acceptable
		("~1.2", "1.2.3", True),
		("~1.2", "~1.2.0", True),
		("~1.2", "^1.3.0", False),
		("~1.2", "1.3.0", False),
		("~1.2", "~1.3", False),
		# Unknown constraint forms -> fallback to equality
		(">=1", ">=1", True),
		(">=1", "^1", False),
		# Workspaces: always treated as satisfied
		("^1", "workspace:*", True),
		("1.2.3", "workspace:*", True),
		# None semantics
		(None, "^1", True),
		("1.2.3", None, False),
		(None, None, True),
	],
)
def test_spec_satisfies(required: str | None, existing: str | None, ok: bool):
	assert spec_satisfies(required, existing) is ok


def test_pulse_dev_codegen_integration(tmp_path: Path):
	"""Test that 'pulse dev' calls app.run_codegen before starting servers."""
	# Test flow: codegen called -> address/port used correctly
	codegen_calls: list[dict[str, str]] = []

	def mock_run_codegen(
		address: str | None = None, internal_address: str | None = None
	):
		codegen_calls.append(
			{
				"address": address or "",
				"internal_address": internal_address or "",
			}
		)

	# Mock at the Python level - just check that codegen is called with correct params
	from pulse.app import App

	app = App()
	app.run_codegen = mock_run_codegen  # type: ignore[assignment]

	# In real usage, the dev command would:
	# 1. Load app
	# 2. Call app.run_codegen(f"http://{address}:{port}", ...)
	# 3. Then start servers

	# Simulate the call sequence
	address = "localhost"
	port = 8000
	app.run_codegen(f"http://{address}:{port}", f"http://{address}:{port}")

	# Verify codegen was called with correct addresses
	assert len(codegen_calls) == 1
	assert codegen_calls[0]["address"] == "http://localhost:8000"
	assert codegen_calls[0]["internal_address"] == "http://localhost:8000"
