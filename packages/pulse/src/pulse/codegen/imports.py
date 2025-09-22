from dataclasses import dataclass, field
from operator import concat
from typing import Iterable, Optional, Protocol

from pulse.codegen.utils import NameRegistry


class Imported:
    name: str
    src: str
    is_default: bool
    prop: Optional[str]

    def __init__(
        self, name: str, src: str, is_default: bool = False, prop: Optional[str] = None
    ) -> None:
        self.name = name
        self.src = src
        self.is_default = is_default
        self.prop = prop

    @property
    def expr(self):
        if self.prop:
            return f"{self.name}.{self.prop}"
        return self.name


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
