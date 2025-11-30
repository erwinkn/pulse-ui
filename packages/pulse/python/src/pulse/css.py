import hashlib
import inspect
from collections.abc import Iterable, Iterator, MutableMapping, Sequence
from pathlib import Path
from typing import override

from pulse.codegen.imports import Import

_CSS_MODULES: MutableMapping[Path, "CssModule"] = {}
_CSS_IMPORTS: dict[str, "CssImport"] = {}


def _caller_file() -> Path:
	frame = inspect.currentframe()
	try:
		if frame is None or frame.f_back is None:
			raise RuntimeError("Cannot determine caller frame for ps.css()")
		caller = frame.f_back
		# Walk past helper wrappers (ps.css may be imported under different name)
		while caller and caller.f_code.co_filename == __file__:
			caller = caller.f_back
		if caller is None:
			raise RuntimeError("Cannot determine caller for ps.css()")
		return Path(caller.f_code.co_filename).resolve()
	finally:
		del frame


def css_module(path: str | Path, *, relative: bool = False) -> "CssModule":
	source = Path(path)
	caller = _caller_file()
	if relative:
		source = caller.parent / source
	source = source.resolve()
	if not source.exists():
		raise FileNotFoundError(f"CSS module '{source}' not found")
	module = _CSS_MODULES.get(source)
	if not module:
		module = CssModule.create(source)
		_CSS_MODULES[source] = module
	return module


def css(
	path: str | Path, *, relative: bool = False, before: Sequence[str] = ()
) -> "CssImport":
	if relative:
		caller = _caller_file()
		path = (caller.parent / Path(path)).resolve()
		if not path.exists():
			raise FileNotFoundError(
				f"CSS import '{path}' not found relative to {caller.parent}"
			)

	key = str(path)
	existing = _CSS_IMPORTS.get(key)
	if existing:
		return existing
	imp = CssImport(path, before=before)
	_CSS_IMPORTS[key] = imp
	return imp


def registered_css_modules() -> list["CssModule"]:
	return list(_CSS_MODULES.values())


def registered_css_imports() -> list["CssImport"]:
	return list(_CSS_IMPORTS.values())


class CssModule(Import):
	"""A CSS module that provides scoped class names via attribute access.

	Inherits from Import to participate in the unified import system.
	Use .foo or ["foo"] to get CssReference objects for class names.
	"""

	id: str

	def __init__(self, source_path: Path, register: bool = True) -> None:
		self.id = _module_id(source_path)
		# CSS modules are default imports
		super().__init__(
			name=self.id,
			src=str(source_path),
			kind="default",
			register=register,
		)

	@property
	def source_path(self) -> Path:
		return Path(self.src).resolve()

	@staticmethod
	def create(path: Path) -> "CssModule":
		return CssModule(path)

	def __getattr__(self, key: str) -> "CssReference":
		# Avoid infinite recursion for dunder attrs and known instance attrs
		if key.startswith("_") or key in (
			"name",
			"src",
			"kind",
			"before",
			"prop",
			"alias",
			"source_path",
			"id",
		):
			raise AttributeError(key)
		return CssReference(self, key)

	def __getitem__(self, key: str) -> "CssReference":
		return CssReference(self, key)

	def iter(self, names: Iterable[str]) -> Iterator["CssReference"]:
		for name in names:
			yield CssReference(self, name)

	@override
	def __repr__(self) -> str:
		return f"CssModule(id={self.id!r}, source_path={self.source_path!r})"

	@override
	def __eq__(self, other: object) -> bool:
		if not isinstance(other, CssModule):
			return NotImplemented
		return self.source_path == other.source_path

	@override
	def __hash__(self) -> int:
		return hash(self.source_path)


class CssReference:
	"""A reference to a class name in a CSS module."""

	module: CssModule
	name: str

	def __init__(self, module: CssModule, name: str) -> None:
		if not name:
			raise ValueError("CSS class name cannot be empty")
		self.module = module
		self.name = name

	def __bool__(self) -> bool:
		raise TypeError("CssReference objects cannot be coerced to bool")

	def __int__(self) -> int:
		raise TypeError("CssReference objects cannot be converted to int")

	def __float__(self) -> float:
		raise TypeError("CssReference objects cannot be converted to float")

	@override
	def __str__(self) -> str:
		raise TypeError("CssReference objects cannot be converted to str")

	@override
	def __repr__(self) -> str:
		return f"CssReference(module={self.module.id!r}, name={self.name!r})"


def _module_id(path: Path) -> str:
	data = str(path).encode("utf-8")
	digest = hashlib.sha1(data).hexdigest()
	return f"css_{digest[:12]}"


class CssImport(Import):
	"""A side-effect CSS import (e.g., for global styles).

	Inherits from Import to participate in the unified import system.
	"""

	source_path: Path | None
	id: str

	def __init__(
		self,
		src: str | Path,
		*,
		before: Sequence[str] = (),
		register: bool = True,
	) -> None:
		# Auto-detect if src is a file path
		source_path = None
		if isinstance(src, Path):
			resolved = src.resolve()
			if resolved.exists() and resolved.is_file():
				source_path = resolved
		else:
			# Try to resolve as absolute path
			try:
				resolved = Path(src).resolve()
				if resolved.exists() and resolved.is_file():
					source_path = resolved
			except (OSError, ValueError):
				# Not a valid path, treat as specifier
				pass

		self.source_path = source_path
		self.id = _import_id(str(src))

		# CSS imports are side-effect imports
		super().__init__(
			name="",
			src=str(src),
			kind="side_effect",
			before=before,
			register=register,
		)

	@override
	def __repr__(self) -> str:
		if self.source_path:
			return f"CssImport(src={self.src!r}, source_path={self.source_path!r})"
		return f"CssImport(src={self.src!r})"

	@override
	def __eq__(self, other: object) -> bool:
		if not isinstance(other, CssImport):
			return NotImplemented
		return self.id == other.id

	@override
	def __hash__(self) -> int:
		return hash(self.id)


def _import_id(value: str) -> str:
	data = value.encode("utf-8")
	digest = hashlib.sha1(data).hexdigest()
	return f"css_import_{digest[:12]}"


__all__ = [
	"CssModule",
	"CssReference",
	"CssImport",
	"css",
	"css_module",
	"registered_css_modules",
	"registered_css_imports",
]
