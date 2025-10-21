from __future__ import annotations

import pytest
from pulse.cli.packages import (
	is_alias_source,
	is_relative_source,
	is_url_or_absolute,
	parse_install_spec,
	resolve_versions,
	spec_satisfies,
)


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
