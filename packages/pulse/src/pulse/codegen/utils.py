from typing import Iterable, Optional


class NameRegistry:
    def __init__(self, names: Iterable[str] | None = None) -> None:
        self.names: set[str] = set(names or [])

    def register(self, name: str, suffix: Optional[str] = None, allow_rename=True):
        if name not in self.names:
            self.names.add(name)
            return name
        if not allow_rename:
            raise ValueError(f"Duplicate identifier {name}")
        i = 2
        aliased = f"{name}{i}"
        while aliased in self.names:
            i += 1
            aliased = f"{name}{i}"
        self.names.add(aliased)
        return aliased
