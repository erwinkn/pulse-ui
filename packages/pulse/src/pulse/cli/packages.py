from __future__ import annotations

# Helpers for parsing JavaScript package specifiers used by Pulse's CLI.
#
# Goals:
# - Extract a canonical npm/bun package name from import sources used in React components
#   (reject relative paths; allow aliases like "@/" and "~/"; ignore URLs/absolute paths).
# - Parse dependency specs that may include an optional version (e.g., "pkg@^2", "@scope/name@1").

from typing import Optional, Tuple
import json
from pathlib import Path


def is_relative_source(src: str) -> bool:
    return src.startswith("./") or src.startswith("../")


def is_alias_source(src: str) -> bool:
    return src.startswith("@/") or src.startswith("~/")


def is_url_or_absolute(src: str) -> bool:
    return (
        src.startswith("http://") or src.startswith("https://") or src.startswith("/")
    )


def parse_dependency_spec(spec: str) -> Tuple[str, Optional[str]]:
    """Parse a dependency spec into (name, version) where version may be None.

    Accepts:
      - "some-pkg"
      - "some-pkg@^1.2.3"
      - "@scope/name"
      - "@scope/name@2"

    Ignores any subpath suffix (e.g., "pkg/sub/path"). For scoped packages with versions,
    splits on the last '@' to avoid confusing the scope '@'.
    """

    if spec.startswith("@"):
        # Scoped: @scope/name[@version][/subpath]
        s = spec[1:]
        i = s.find("/")
        if i == -1:
            return "@" + s, None
        scope = s[:i]
        rest = s[i + 1 :]
        # head may be 'name' or 'name@version'
        j = rest.find("/")
        head = rest if j == -1 else rest[:j]
        if "@" in head:
            name_part, ver = head.split("@", 1)
        else:
            name_part, ver = head, None
        return f"@{scope}/{name_part}", (ver or None)

    # Unscoped: name[@version][/subpath]
    head = spec.split("/", 1)[0]
    if "@" in head:
        name, ver = head.split("@", 1)
        return name, (ver or None)
    return head, None


def parse_install_spec(src_or_spec: str) -> Optional[str]:
    """Unified parser that:
    - Rejects relative paths by raising ValueError.
    - Returns None for alias ("@/", "~/"), URLs, and absolute paths.
    - Returns a normalized install spec: "name" or "name@version".
    - Accepts sources or dependency specs, and strips subpaths.
    """

    if is_relative_source(src_or_spec):
        raise ValueError(
            f"React component import source '{src_or_spec}' must not be relative (./ or ../). Use a package, '@/...' or '~/...' alias instead."
        )
    if is_alias_source(src_or_spec) or is_url_or_absolute(src_or_spec):
        return None
    name, ver = parse_dependency_spec(src_or_spec)
    return f"{name}@{ver}" if ver else name


# ---------------------------- Version resolution ----------------------------


class VersionConflict(Exception):
    pass


def pick_more_specific(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Pick the more specific semver constraint between two strings.

    Heuristic only (no full semver solver):
      - Exact versions (e.g., "1.2.3") outrank range prefixes ("^", "~", ">=", "<=", ">", "<").
      - Between ranges, prefer the one with a longer string (assume more specific).
      - If one is None, return the other.
      - If equal, return either.
    """

    if not a:
        return b
    if not b:
        return a

    # Exact version detection: purely digits and dots
    def is_exact(v: str) -> bool:
        return bool(v) and all(part.isdigit() for part in v.split("."))

    a_exact = is_exact(a)
    b_exact = is_exact(b)
    if a_exact and b_exact:
        return a if a == b else None  # same exact or conflict
    if a_exact:
        return a
    if b_exact:
        return b
    # Prefer longer constraint as proxy for specificity
    return a if len(a) >= len(b) else b


def resolve_versions(
    constraints: dict[str, list[Optional[str]]],
) -> dict[str, Optional[str]]:
    """Resolve version constraints per package.

    Input: { name: [ver1, ver2, None, ...] }
    Output: { name: resolved_version_or_None }
    Raises VersionConflict if constraints are incompatible under our heuristic.
    """
    resolved: dict[str, Optional[str]] = {}
    for name, vers in constraints.items():
        cur: Optional[str] = None
        for v in vers:
            cur = pick_more_specific(cur, v)
            if cur is None and v is not None:
                # irreconcilable (two different exact versions)
                raise VersionConflict(f"Conflicting versions for {name}: {vers}")
        resolved[name] = cur
    return resolved


# ----------------------------- package.json utils ----------------------------


def load_package_json(web_root: Path) -> dict:
    pkg_path = web_root / "package.json"
    try:
        data = json.loads(pkg_path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def get_pkg_spec(pkg_json: dict, name: str) -> Optional[str]:
    for field in ("dependencies", "devDependencies"):
        section = pkg_json.get(field)
        if isinstance(section, dict) and name in section:
            spec = section.get(name)
            if isinstance(spec, str):
                return spec.strip()
    return None


def is_workspace_spec(spec: str) -> bool:
    return spec.strip().startswith("workspace:")


def _split_constraint(spec: str) -> tuple[str, Optional[str]]:
    s = spec.strip()
    if not s:
        return "unknown", None
    if s[0] in ("^", "~"):
        return (s[0], s[1:])
    # exact version like 1 or 1.2 or 1.2.3
    if all(part.isdigit() for part in s.split(".")):
        return ("=", s)
    return "unknown", s


def _parse_major_minor(ver: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not ver:
        return None, None
    try:
        parts = ver.split(".")
        major = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else None
        minor = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
        return major, minor
    except Exception:
        return None, None


def spec_satisfies(required: Optional[str], existing: Optional[str]) -> bool:
    if required is None:
        return True
    if not existing:
        return False
    if is_workspace_spec(existing):
        return True
    rk, rv = _split_constraint(required)
    ek, ev = _split_constraint(existing)
    rmaj, rmin = _parse_major_minor(rv)
    emaj, emin = _parse_major_minor(ev)

    # Exact required
    if rk == "=":
        if ek == "=" and rv == ev:
            return True
        # Accept common ranges that include the exact version
        if ek == "^" and emaj is not None and rmaj is not None and emaj == rmaj:
            return True
        if (
            ek == "~"
            and emaj is not None
            and emin is not None
            and rmaj is not None
            and rmin is not None
            and emaj == rmaj
            and emin == rmin
        ):
            return True
        return False

    # Caret required: same major acceptable
    if rk == "^" and rmaj is not None:
        if ek == "=" and emaj == rmaj:
            return True
        if ek == "^" and emaj == rmaj:
            return True
        if ek == "~" and emaj == rmaj:
            return True
        return False

    # Tilde required: same major+minor acceptable
    if rk == "~" and rmaj is not None and rmin is not None:
        if ek == "=" and emaj == rmaj and emin == rmin:
            return True
        if ek == "~" and emaj == rmaj and emin == rmin:
            return True
        return False

    # Unknown required; fallback to equality
    return required == existing
