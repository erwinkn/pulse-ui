from dataclasses import dataclass, field
from operator import concat
from typing import Iterable, Optional, Protocol

from pulse.codegen.utils import NameRegistry


class Imported:
    name: str
    src: str
    alias: str | None
    is_default: bool
    prop: Optional[str]

    def __init__(
        self,
        name: str,
        src: str,
        is_default: bool = False,
        prop: Optional[str] = None,
        alias: str | None = None,
    ) -> None:
        self.name = name
        self.src = src
        self.is_default = is_default
        self.prop = prop
        self.alias = alias

    @property
    def expr(self):
        if self.prop:
            return f"{self.alias or self.name}.{self.prop}"
        return self.alias or self.name


@dataclass
class ImportMember:
    name: str
    alias: str | None = None

    @property
    def identifier(self):
        return self.alias or self.name


@dataclass
class ImportStatement:
    src: str
    values: list[ImportMember] = field(default_factory=list)
    types: list[ImportMember] = field(default_factory=list)
    default_import: str | None = None
    # When True, emit a side-effect import: `import "<src>";`
    # Can be combined with named/default imports; side-effect line is emitted
    # only when there are no named/default/type imports for the source.
    side_effect: bool = False
    # Optional ordering constraint: ensure this statement is emitted before
    # any import statements whose `src` matches one of these values.
    # Example: ImportStatement(src="@mantine/core/styles.css", side_effect=True,
    #                          before=["@mantine/dates/styles.css"]) ensures
    # core styles are imported before dates styles.
    before: list[str] = field(default_factory=list)


class Imports:
    def __init__(
        self,
        imports: Iterable[ImportStatement | Imported],
        names: Optional[NameRegistry] = None,
    ) -> None:
        self.names = names or NameRegistry()
        # Map (src, name) -> identifier (either name or alias)
        self._import_map: dict[tuple[str, str], str] = {}
        self.sources: dict[str, ImportStatement] = {}
        for stmt in imports:
            if not isinstance(stmt, ImportStatement):
                continue

            if stmt.default_import:
                stmt.default_import = self.names.register(stmt.default_import)

            for imp in concat(stmt.values, stmt.types):
                name = self.names.register(imp.name)
                if name != imp.name:
                    imp.alias = name
                self._import_map[(stmt.src, imp.name)] = name

            self.sources[stmt.src] = stmt

    def import_(self, src: str, name: str, is_type=False, is_default=False) -> str:
        stmt = self.sources.get(src)
        if not stmt:
            stmt = ImportStatement(src)
            self.sources[src] = stmt

        if is_default:
            if stmt.default_import:
                return stmt.default_import
            stmt.default_import = self.names.register(name)
            return stmt.default_import

        else:
            if (src, name) in self._import_map:
                return self._import_map[(src, name)]

            unique_name = self.names.register(name)
            alias = unique_name if unique_name != name else None
            imp = ImportMember(name, alias)
            if is_type:
                stmt.types.append(imp)
            else:
                stmt.values.append(imp)
            # Remember mapping so future imports of the same (src, name) reuse identifier
            self._import_map[(src, name)] = imp.identifier
            return imp.identifier

    def add_statement(self, stmt: ImportStatement) -> None:
        """Merge an ImportStatement into the current Imports registry.

        Ensures consistent aliasing via NameRegistry and de-duplicates
        previously imported names from the same source.
        """
        existing = self.sources.get(stmt.src)
        if not existing:
            # Normalize names through registry to avoid later conflicts
            if stmt.default_import:
                stmt.default_import = self.names.register(stmt.default_import)
            for imp in concat(stmt.values, stmt.types):
                name = self.names.register(imp.name)
                if name != imp.name:
                    imp.alias = name
                self._import_map[(stmt.src, imp.name)] = name
            self.sources[stmt.src] = stmt
            return

        # Merge into existing statement for the same src
        if stmt.default_import and not existing.default_import:
            existing.default_import = self.names.register(stmt.default_import)

        # Merge named imports
        def _merge_list(
            dst: list[ImportMember], src_list: list[ImportMember], is_type: bool = False
        ):
            for imp in src_list:
                key = (stmt.src, imp.name)
                if key in self._import_map:
                    continue
                unique = self.names.register(imp.name)
                if unique != imp.name:
                    imp.alias = unique
                self._import_map[key] = imp.alias or imp.name
                dst.append(imp)

        _merge_list(existing.values, stmt.values, is_type=False)
        _merge_list(existing.types, stmt.types, is_type=True)
        existing.side_effect = existing.side_effect or stmt.side_effect
        # Merge ordering constraints
        if stmt.before:
            # Preserve order, avoid duplicates
            seen = set(existing.before)
            for s in stmt.before:
                if s not in seen:
                    existing.before.append(s)
                    seen.add(s)

    def ordered_sources(self) -> list[ImportStatement]:
        """Return sources ordered to satisfy `before` constraints.

        Uses a stable topological sort (Kahn's algorithm) where insertion order
        is preserved among nodes with equal dependency rank. Falls back to
        insertion order if cycles are detected.
        """
        # Build graph: edge u->v means u must come before v
        keys = list(self.sources.keys())
        index = {k: i for i, k in enumerate(keys)}  # for stability
        indegree: dict[str, int] = {k: 0 for k in keys}
        adj: dict[str, list[str]] = {k: [] for k in keys}
        for u, stmt in self.sources.items():
            for v in stmt.before:
                if v in adj:  # only consider edges to imports present
                    adj[u].append(v)
                    indegree[v] += 1

        # Kahn's algorithm
        queue = [k for k, d in indegree.items() if d == 0]
        # Stable ordering of initial nodes
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

        # If not all nodes processed, cycle detected; fall back to insertion order
        if len(ordered) != len(keys):
            ordered = keys
        return [self.sources[k] for k in ordered]
