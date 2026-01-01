"""Tests for bump_version.py"""

import json
from pathlib import Path

import pytest

from scripts.bump_version import (
	bump_alpha,
	bump_beta,
	bump_major,
	bump_minor,
	bump_patch,
	bump_rc,
	convert_pep440_to_semver,
	get_version_from_package_json,
	get_version_from_pyproject,
	update_package_json_version,
	update_pyproject_version,
)


class TestBumpPatch:
	def test_simple_version(self):
		assert bump_patch("0.1.44") == "0.1.45"

	def test_zero_patch(self):
		assert bump_patch("1.0.0") == "1.0.1"

	def test_large_numbers(self):
		assert bump_patch("10.20.99") == "10.20.100"

	def test_strips_alpha_suffix(self):
		assert bump_patch("0.1.44a1") == "0.1.45"

	def test_strips_beta_suffix(self):
		assert bump_patch("0.1.44b2") == "0.1.45"

	def test_strips_rc_suffix(self):
		assert bump_patch("0.1.44rc1") == "0.1.45"

	def test_invalid_version(self):
		with pytest.raises(ValueError, match="Invalid version format"):
			bump_patch("invalid")


class TestBumpMinor:
	def test_simple_version(self):
		assert bump_minor("0.1.44") == "0.2.0"

	def test_resets_patch(self):
		assert bump_minor("1.5.99") == "1.6.0"

	def test_zero_minor(self):
		assert bump_minor("2.0.5") == "2.1.0"

	def test_strips_prerelease(self):
		assert bump_minor("0.1.44a1") == "0.2.0"

	def test_invalid_version(self):
		with pytest.raises(ValueError, match="Invalid version format"):
			bump_minor("bad")


class TestBumpMajor:
	def test_simple_version(self):
		assert bump_major("0.1.44") == "1.0.0"

	def test_resets_minor_and_patch(self):
		assert bump_major("1.5.99") == "2.0.0"

	def test_strips_prerelease(self):
		assert bump_major("0.1.44rc1") == "1.0.0"

	def test_invalid_version(self):
		with pytest.raises(ValueError, match="Invalid version format"):
			bump_major("x.y.z")


class TestBumpAlpha:
	def test_from_stable_bumps_patch_and_adds_a1(self):
		assert bump_alpha("0.1.44") == "0.1.45a1"

	def test_increments_existing_alpha(self):
		assert bump_alpha("0.1.45a1") == "0.1.45a2"
		assert bump_alpha("0.1.45a2") == "0.1.45a3"
		assert bump_alpha("0.1.45a9") == "0.1.45a10"

	def test_from_beta_starts_new_alpha(self):
		# From beta, it extracts base and starts at a1
		assert bump_alpha("0.1.45b1") == "0.1.46a1"

	def test_from_rc_starts_new_alpha(self):
		assert bump_alpha("0.1.45rc1") == "0.1.46a1"

	def test_invalid_version(self):
		with pytest.raises(ValueError, match="Invalid version format"):
			bump_alpha("not-a-version")


class TestBumpBeta:
	def test_from_alpha_starts_b1(self):
		assert bump_beta("0.1.45a1") == "0.1.45b1"
		assert bump_beta("0.1.45a5") == "0.1.45b1"

	def test_increments_existing_beta(self):
		assert bump_beta("0.1.45b1") == "0.1.45b2"
		assert bump_beta("0.1.45b2") == "0.1.45b3"

	def test_from_stable_starts_b1(self):
		assert bump_beta("0.1.45") == "0.1.45b1"

	def test_from_rc_starts_b1_same_base(self):
		assert bump_beta("0.1.45rc1") == "0.1.45b1"

	def test_invalid_version(self):
		with pytest.raises(ValueError, match="Invalid version format"):
			bump_beta("bad-version")


class TestBumpRc:
	def test_from_beta_starts_rc1(self):
		assert bump_rc("0.1.45b1") == "0.1.45rc1"
		assert bump_rc("0.1.45b3") == "0.1.45rc1"

	def test_increments_existing_rc(self):
		assert bump_rc("0.1.45rc1") == "0.1.45rc2"
		assert bump_rc("0.1.45rc2") == "0.1.45rc3"

	def test_from_alpha_starts_rc1(self):
		assert bump_rc("0.1.45a1") == "0.1.45rc1"

	def test_from_stable_starts_rc1(self):
		assert bump_rc("0.1.45") == "0.1.45rc1"

	def test_invalid_version(self):
		with pytest.raises(ValueError, match="Invalid version format"):
			bump_rc("nope")


class TestConvertPep440ToSemver:
	def test_stable_version_unchanged(self):
		assert convert_pep440_to_semver("0.1.45") == "0.1.45"
		assert convert_pep440_to_semver("1.0.0") == "1.0.0"
		assert convert_pep440_to_semver("10.20.30") == "10.20.30"

	def test_alpha_conversion(self):
		assert convert_pep440_to_semver("0.1.45a1") == "0.1.45-alpha.1"
		assert convert_pep440_to_semver("0.1.45a10") == "0.1.45-alpha.10"

	def test_beta_conversion(self):
		assert convert_pep440_to_semver("0.1.45b1") == "0.1.45-beta.1"
		assert convert_pep440_to_semver("0.1.45b5") == "0.1.45-beta.5"

	def test_rc_conversion(self):
		assert convert_pep440_to_semver("0.1.45rc1") == "0.1.45-rc.1"
		assert convert_pep440_to_semver("0.1.45rc3") == "0.1.45-rc.3"

	def test_dev_conversion(self):
		assert convert_pep440_to_semver("0.1.45dev1") == "0.1.45-dev.1"

	def test_dot_dev_conversion(self):
		assert convert_pep440_to_semver("0.1.45.dev1") == "0.1.45-dev.1"

	def test_c_maps_to_rc(self):
		# PEP 440 allows 'c' as alias for 'rc'
		assert convert_pep440_to_semver("0.1.45c1") == "0.1.45-rc.1"


class TestVersionWorkflow:
	"""Test complete version workflows."""

	def test_alpha_to_stable_workflow(self):
		# Start with stable
		v = "0.1.44"

		# First alpha
		v = bump_alpha(v)
		assert v == "0.1.45a1"

		# More alphas
		v = bump_alpha(v)
		assert v == "0.1.45a2"

		# Move to beta
		v = bump_beta(v)
		assert v == "0.1.45b1"

		# More betas
		v = bump_beta(v)
		assert v == "0.1.45b2"

		# Move to RC
		v = bump_rc(v)
		assert v == "0.1.45rc1"

		# More RCs
		v = bump_rc(v)
		assert v == "0.1.45rc2"

		# Release stable
		v = bump_patch(v)
		assert v == "0.1.46"

	def test_semver_sync_through_workflow(self):
		versions = [
			("0.1.44", "0.1.44"),
			("0.1.45a1", "0.1.45-alpha.1"),
			("0.1.45a2", "0.1.45-alpha.2"),
			("0.1.45b1", "0.1.45-beta.1"),
			("0.1.45rc1", "0.1.45-rc.1"),
			("0.1.45", "0.1.45"),
		]
		for python_v, expected_js in versions:
			assert convert_pep440_to_semver(python_v) == expected_js


class TestFileOperations:
	def test_get_version_from_pyproject(self, tmp_path: Path):
		pyproject = tmp_path / "pyproject.toml"
		pyproject.write_text('[project]\nname = "test"\nversion = "1.2.3"\n')

		assert get_version_from_pyproject(pyproject) == "1.2.3"

	def test_get_version_from_package_json(self, tmp_path: Path):
		package_json = tmp_path / "package.json"
		package_json.write_text('{"name": "test", "version": "1.2.3"}')

		assert get_version_from_package_json(package_json) == "1.2.3"

	def test_update_pyproject_version(self, tmp_path: Path):
		pyproject = tmp_path / "pyproject.toml"
		pyproject.write_text('[project]\nname = "test"\nversion = "1.2.3"\n')

		update_pyproject_version(pyproject, "2.0.0")

		content = pyproject.read_text()
		assert 'version = "2.0.0"' in content

	def test_update_pyproject_preserves_other_content(self, tmp_path: Path):
		original = (
			'[project]\nname = "test"\nversion = "1.2.3"\ndescription = "A test"\n'
		)
		pyproject = tmp_path / "pyproject.toml"
		pyproject.write_text(original)

		update_pyproject_version(pyproject, "2.0.0")

		content = pyproject.read_text()
		assert 'name = "test"' in content
		assert 'description = "A test"' in content

	def test_update_package_json_version(self, tmp_path: Path):
		package_json = tmp_path / "package.json"
		package_json.write_text('{\n\t"name": "test",\n\t"version": "1.2.3"\n}\n')

		update_package_json_version(package_json, "2.0.0")

		data = json.loads(package_json.read_text())
		assert data["version"] == "2.0.0"
		assert data["name"] == "test"

	def test_update_package_json_preserves_formatting(self, tmp_path: Path):
		package_json = tmp_path / "package.json"
		package_json.write_text('{\n\t"name": "test",\n\t"version": "1.2.3"\n}\n')

		update_package_json_version(package_json, "2.0.0")

		content = package_json.read_text()
		# Should use tab indentation
		assert '\t"name"' in content
