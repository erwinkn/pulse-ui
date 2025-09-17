from pathlib import Path


from pulse.cli.helpers import parse_app_target


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
