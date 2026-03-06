from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WHEEL_FILES = {
	"pulse_aws/__init__.py",
	"pulse_aws/baseline.py",
	"pulse_aws/cdk/__init__.py",
	"pulse_aws/cdk/app.py",
	"pulse_aws/cdk/baseline.py",
	"pulse_aws/cdk/cdk.json",
	"pulse_aws/cdk/helpers.py",
	"pulse_aws/reaper_lambda.py",
}
FORBIDDEN_ARTIFACT_MARKERS = (".DS_Store", "cdk.context.json", "cdk.out/")


def test_build_artifacts_include_runtime_cdk_files(tmp_path):
	uv_bin = shutil.which("uv")
	if uv_bin is None:
		pytest.skip("uv is not available")

	subprocess.run(
		[uv_bin, "build", str(PACKAGE_ROOT), "--out-dir", str(tmp_path)],
		check=True,
		cwd=REPO_ROOT,
	)

	wheel = next(tmp_path.glob("pulse_aws-*.whl"))
	sdist = next(tmp_path.glob("pulse_aws-*.tar.gz"))

	with zipfile.ZipFile(wheel) as wheel_file:
		wheel_names = set(wheel_file.namelist())
	assert REQUIRED_WHEEL_FILES <= wheel_names
	assert not any(
		marker in name for marker in FORBIDDEN_ARTIFACT_MARKERS for name in wheel_names
	)

	with tarfile.open(sdist) as sdist_file:
		sdist_names = {member.name for member in sdist_file.getmembers()}
	for required_file in REQUIRED_WHEEL_FILES:
		assert any(name.endswith(f"src/{required_file}") for name in sdist_names), (
			required_file
		)
	assert not any(
		marker in name for marker in FORBIDDEN_ARTIFACT_MARKERS for name in sdist_names
	)
