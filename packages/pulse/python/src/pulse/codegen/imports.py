from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, override

from pulse.codegen.utils import NameRegistry

# Global registry for all Import objects
IMPORT_REGISTRY: set["Import"] = set()


class Import:
	"""Universal import descriptor. Registers itself on creation."""

	name: str
	src: str
	kind: Literal["default", "named", "type", "side_effect"]
	before: tuple[str, ...]
	# For runtime expression computation
	prop: str | None
	alias: str | None

	def __init__(
		self,
		name: str,
		src: str,
		kind: Literal["default", "named", "type", "side_effect"] = "named",
		before: Sequence[str] = (),
		*,
		prop: str | None = None,
		alias: str | None = None,
		register: bool = True,
	) -> None:
		self.name = name
		self.src = src
		self.kind = kind
		self.before = tuple(before)
		self.prop = prop
		self.alias = alias
		if register:
			IMPORT_REGISTRY.add(self)

	@classmethod
	def default(
		cls,
		name: str,
		src: str,
		*,
		prop: str | None = None,
		register: bool = True,
	) -> "Import":
		return cls(name, src, "default", prop=prop, register=register)

	@classmethod
	def named(
		cls,
		name: str,
		src: str,
		*,
		prop: str | None = None,
		register: bool = True,
	) -> "Import":
		return cls(name, src, "named", prop=prop, register=register)

	@classmethod
	def type_(
		cls,
		name: str,
		src: str,
		*,
		register: bool = True,
	) -> "Import":
		return cls(name, src, "type", register=register)

	@classmethod
	def css(
		cls,
		src: str,
		before: Sequence[str] = (),
		*,
		register: bool = True,
	) -> "Import":
		return cls("", src, "side_effect", before, register=register)

	@property
	def is_default(self) -> bool:
		return self.kind == "default"

	@property
	def expr(self) -> str:
		"""Runtime expression for this import."""
		if self.prop:
			return f"{self.alias or self.name}.{self.prop}"
		return self.alias or self.name

	@override
	def __eq__(self, other: object) -> bool:
		if not isinstance(other, Import):
			return NotImplemented
		return (self.name, self.src, self.kind) == (other.name, other.src, other.kind)

	@override
	def __hash__(self) -> int:
		return hash((self.name, self.src, self.kind))

	@override
	def __repr__(self) -> str:
		parts = [f"name={self.name!r}", f"src={self.src!r}"]
		if self.kind != "named":
			parts.append(f"kind={self.kind!r}")
		if self.prop:
			parts.append(f"prop={self.prop!r}")
		return f"Import({', '.join(parts)})"


def registered_imports() -> list[Import]:
	"""Get all registered imports."""
	return list(IMPORT_REGISTRY)


def clear_import_registry() -> None:
	"""Clear the import registry."""
	IMPORT_REGISTRY.clear()


@dataclass(slots=True)
class ImportMember:
	name: str
	alias: str | None = None

	@property
	def identifier(self) -> str:
		return self.alias or self.name


@dataclass
class ImportStatement:
	"""Merged import line for codegen output."""

	src: str
	default_import: str | None = None
	values: list[ImportMember] = field(default_factory=list)
	types: list[ImportMember] = field(default_factory=list)
	side_effect: bool = False
	before: list[str] = field(default_factory=list)


class Imports:
	"""Collects imports, handles aliasing/dedup, generates statements."""

	_names: NameRegistry
	_by_src: dict[str, ImportStatement]
	_seen: dict[tuple[str, str, str], str]

	def __init__(
		self,
		reserved: Iterable[str] = (),
		*,
		names: NameRegistry | None = None,
	) -> None:
		self._names = names or NameRegistry(set(reserved))
		self._by_src = {}
		self._seen = {}  # (src, name, kind) -> identifier

	def add(self, imp: Import) -> str:
		"""Add import, returns identifier to use (handles aliasing)."""
		key = (imp.src, imp.name, imp.kind)
		if key in self._seen:
			return self._seen[key]

		stmt = self._by_src.setdefault(imp.src, ImportStatement(imp.src))

		for b in imp.before:
			if b not in stmt.before:
				stmt.before.append(b)

		if imp.kind == "side_effect":
			stmt.side_effect = True
			return ""

		if imp.kind == "default":
			if stmt.default_import:
				return stmt.default_import
			ident = self._names.register(imp.name)
			stmt.default_import = ident
			self._seen[key] = ident
			return ident

		# named or type
		ident = self._names.register(imp.name)
		member = ImportMember(imp.name, ident if ident != imp.name else None)
		(stmt.types if imp.kind == "type" else stmt.values).append(member)
		self._seen[key] = ident
		return ident

	def import_(
		self, src: str, name: str, is_type: bool = False, is_default: bool = False
	) -> str:
		"""Convenience method matching old API."""
		if is_default:
			return self.add(Import.default(name, src, register=False))
		if is_type:
			return self.add(Import.type_(name, src, register=False))
		return self.add(Import(name, src, register=False))

	def add_statement(self, stmt: ImportStatement) -> None:
		"""Merge an ImportStatement into the current Imports registry."""
		existing = self._by_src.get(stmt.src)
		if not existing:
			# Normalize names through registry
			if stmt.default_import:
				stmt.default_import = self._names.register(stmt.default_import)
			for imp in [*stmt.values, *stmt.types]:
				name = self._names.register(imp.name)
				if name != imp.name:
					imp.alias = name
				key = (stmt.src, imp.name, "type" if imp in stmt.types else "named")
				self._seen[key] = name
			self._by_src[stmt.src] = stmt
			return

		# Merge into existing statement
		if stmt.default_import and not existing.default_import:
			existing.default_import = self._names.register(stmt.default_import)

		def _merge_list(
			dst: list[ImportMember], src_list: list[ImportMember], kind: str
		):
			for imp in src_list:
				key = (stmt.src, imp.name, kind)
				if key in self._seen:
					continue
				unique = self._names.register(imp.name)
				if unique != imp.name:
					imp.alias = unique
				self._seen[key] = imp.alias or imp.name
				dst.append(imp)

		_merge_list(existing.values, stmt.values, "named")
		_merge_list(existing.types, stmt.types, "type")
		existing.side_effect = existing.side_effect or stmt.side_effect

		# Merge ordering constraints
		if stmt.before:
			seen = set(existing.before)
			for s in stmt.before:
				if s not in seen:
					existing.before.append(s)
					seen.add(s)

	def statements(self) -> list[ImportStatement]:
		"""Return statements in topologically sorted order."""
		keys = list(self._by_src.keys())
		index = {k: i for i, k in enumerate(keys)}
		indegree: dict[str, int] = {k: 0 for k in keys}
		adj: dict[str, list[str]] = {k: [] for k in keys}

		for u, stmt in self._by_src.items():
			for v in stmt.before:
				if v in adj:
					adj[u].append(v)
					indegree[v] += 1

		# Kahn's algorithm
		queue = [k for k, d in indegree.items() if d == 0]
		queue.sort(key=lambda k: index[k])
		ordered: list[str] = []

		while queue:
			u = queue.pop(0)
			ordered.append(u)
			for v in adj[u]:
				indegree[v] -= 1
				if indegree[v] == 0:
					queue.append(v)
					queue.sort(key=lambda k: index[k])

		# Cycle detected; fall back to insertion order
		if len(ordered) != len(keys):
			ordered = keys

		return [self._by_src[k] for k in ordered]

	# Backwards compat alias
	def ordered_sources(self) -> list[ImportStatement]:
		return self.statements()
