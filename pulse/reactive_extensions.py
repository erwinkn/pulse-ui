from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import MISSING as _DC_MISSING
from dataclasses import dataclass as _dc_dataclass
from dataclasses import fields as _dc_fields
from dataclasses import is_dataclass
from typing import Any as _Any
from typing import Callable, Generic, TypeVar, overload, cast

from pulse.reactive import Signal

T = TypeVar("T")


class ReactiveDict(dict[str, _Any]):
    """A dict-like container with per-key reactivity.

    - Reading a key registers a dependency on that key's Signal
    - Writing a key updates only that key's Signal
    - Deleting a key writes `None` to its Signal (preserving subscriptions)
    - Iteration and len are NOT reactive; use explicit key reads inside render
    """

    __slots__ = ("_signals",)

    def __init__(self, initial: Mapping[str, _Any] | None = None) -> None:
        super().__init__()
        self._signals: dict[str, Signal[_Any]] = {}
        if initial:
            for k, v in initial.items():
                v = wrap_collections(v)
                super().__setitem__(k, v)
                self._signals[k] = Signal(v)

    # --- Mapping protocol ---
    def __getitem__(self, key: str) -> _Any:
        if key not in self._signals:
            # Lazily create missing key with None so it can be reactive
            self._signals[key] = Signal(None)
        return self._signals[key].read()

    def __setitem__(self, key: str, value: _Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        # Preserve signal and subscribers; write None and keep key with None value
        if key not in self._signals:
            self._signals[key] = Signal(None)
        else:
            self._signals[key].write(None)
        super().__setitem__(key, None)

    def get(self, key: str, default: _Any = None) -> _Any:
        if key not in self._signals:
            return default
        return self._signals[key].read()

    def __iter__(self) -> Iterator[str]:
        # Not reactive; snapshot of keys at iteration time
        return super().__iter__()

    def __len__(self) -> int:
        return super().__len__()

    def __contains__(self, key: object) -> bool:
        return super().__contains__(key)

    # --- Mutation helpers ---
    def set(self, key: str, value: _Any) -> None:
        value = wrap_collections(value)
        sig = self._signals.get(key)
        if sig is None:
            self._signals[key] = Signal(value)
        else:
            sig.write(value)
        super().__setitem__(key, value)

    def update(self, values: Mapping[str, _Any]) -> None:  # type: ignore[override]
        for k, v in values.items():
            self.set(k, v)

    def delete(self, key: str) -> None:
        if key in self._signals:
            # Preserve signal object for existing subscribers; set to None
            self._signals[key].write(None)


class ReactiveList(list[_Any]):
    """A list with item-level reactivity where possible and structural change signaling.

    Semantics:
    - Index reads depend on that index's Signal
    - Setting an index writes to that index's Signal
    - Structural operations (append/insert/pop/remove/clear/extend/sort/reverse/slice assigns)
      trigger a structural version Signal so consumers can listen for changes that affect layout
    - Iteration and len are NOT reactive; prefer explicit index reads inside render/effects
    """

    __slots__ = ("_signals", "_structure")

    def __init__(self, initial: Iterable[_Any] | None = None) -> None:
        super().__init__()
        self._signals: list[Signal[_Any]] = []
        self._structure: Signal[int] = Signal(0)
        if initial:
            for item in initial:
                v = wrap_collections(item)
                self._signals.append(Signal(v))
                super().append(v)

    # ---- helpers ----
    def _bump_structure(self):
        self._structure.write(self._structure.read() + 1)

    @property
    def version(self) -> int:
        """Reactive counter that increments on any structural change."""
        return self._structure.read()

    def __getitem__(self, idx):  # type: ignore[override]
        if isinstance(idx, slice):
            # Return a plain list of values (non-reactive slice)
            start, stop, step = idx.indices(len(self))
            return [self._signals[i].read() for i in range(start, stop, step)]
        return self._signals[idx].read()

    def __setitem__(self, idx, value):  # type: ignore[override]
        if isinstance(idx, slice):
            replacement_seq = list(value)
            start, stop, step = idx.indices(len(self))
            target_indices = list(range(start, stop, step))

            if len(replacement_seq) == len(target_indices):
                wrapped = [wrap_collections(v) for v in replacement_seq]
                super().__setitem__(idx, wrapped)
                for i, v in zip(target_indices, wrapped):
                    self._signals[i].write(v)
                return

            super().__setitem__(idx, replacement_seq)
            self._signals = [Signal(wrap_collections(v)) for v in super().__iter__()]
            self._bump_structure()
            return
        # normal index
        v = wrap_collections(value)
        super().__setitem__(idx, v)
        self._signals[idx].write(v)

    def __delitem__(self, idx):  # type: ignore[override]
        if isinstance(idx, slice):
            super().__delitem__(idx)
            self._signals = [Signal(v) for v in super().__iter__()]
            self._bump_structure()
            return
        super().__delitem__(idx)
        del self._signals[idx]
        self._bump_structure()

    # ---- structural operations ----
    def append(self, value: _Any) -> None:  # type: ignore[override]
        v = wrap_collections(value)
        super().append(v)
        self._signals.append(Signal(v))
        self._bump_structure()

    def extend(self, values: Iterable[_Any]) -> None:  # type: ignore[override]
        any_added = False
        for v in values:
            vv = wrap_collections(v)
            super().append(vv)
            self._signals.append(Signal(vv))
            any_added = True
        if any_added:
            self._bump_structure()

    def insert(self, index: int, value: _Any) -> None:
        v = wrap_collections(value)
        super().insert(index, v)
        self._signals.insert(index, Signal(v))
        self._bump_structure()

    def pop(self, index: int = -1):  # type: ignore[override]
        val = super().pop(index)
        del self._signals[index]
        self._bump_structure()
        return val

    def remove(self, value: _Any) -> None:  # type: ignore[override]
        idx = super().index(value)
        self.pop(idx)

    def clear(self) -> None:  # type: ignore[override]
        super().clear()
        self._signals.clear()
        self._bump_structure()

    def reverse(self) -> None:  # type: ignore[override]
        super().reverse()
        self._signals.reverse()
        self._bump_structure()

    def sort(self, *args, **kwargs) -> None:  # type: ignore[override]
        # To preserve per-index subscriptions, we have to reorder signals to match new order
        # We'll compute the permutation by sorting indices based on current values
        current = list(super().__iter__())
        idxs = list(range(len(current)))
        # Create a key that uses the same key as provided to sort, but applied to value
        key = kwargs.get("key")
        reverse = kwargs.get("reverse", False)

        def key_for_index(i):
            v = current[i]
            return key(v) if callable(key) else v

        idxs.sort(key=key_for_index, reverse=reverse)
        # Apply sort to underlying list
        super().sort(*args, **kwargs)
        # Reorder signals to match
        self._signals = [self._signals[i] for i in idxs]
        self._bump_structure()

    # Make len() and iteration reactive to structural changes
    def __len__(self) -> int:
        _ = self._structure.read()
        return super().__len__()

    def __iter__(self):
        _ = self._structure.read()
        return super().__iter__()


class ReactiveSet(set[_Any]):
    """A set with per-element membership reactivity.

    - `x in s` reads a membership Signal for element `x`
    - Mutations update membership Signals for affected elements
    - Iteration and len are NOT reactive
    """

    __slots__ = ("_signals",)

    def __init__(self, initial: Iterable[_Any] | None = None) -> None:
        super().__init__()
        self._signals: dict[_Any, Signal[bool]] = {}
        if initial:
            for v in initial:
                vv = wrap_collections(v)
                super().add(vv)
                self._signals[vv] = Signal(True)

    def __contains__(self, element: object) -> bool:  # type: ignore[override]
        sig = self._signals.get(element)  # type: ignore[index]
        if sig is None:
            present = set.__contains__(self, element)
            self._signals[element] = Signal(bool(present))  # type: ignore[index]
            sig = self._signals[element]  # type: ignore[index]
        return bool(sig.read())

    def membership(self, element: _Any) -> bool:
        """Reactive check for membership of a value.

        Equivalent to `x in s` but explicitly documents reactivity.
        """
        return self.__contains__(element)

    # mutations
    def add(self, element: _Any) -> None:  # type: ignore[override]
        element = wrap_collections(element)
        super().add(element)
        sig = self._signals.get(element)
        if sig is None:
            self._signals[element] = Signal(True)
        else:
            sig.write(True)

    def discard(self, element: _Any) -> None:  # type: ignore[override]
        element = wrap_collections(element)
        if element in self:
            super().discard(element)
            sig = self._signals.get(element)
            if sig is None:
                self._signals[element] = Signal(False)
            else:
                sig.write(False)

    def remove(self, element: _Any) -> None:  # type: ignore[override]
        if element not in self:
            raise KeyError(element)
        self.discard(element)

    def clear(self) -> None:  # type: ignore[override]
        for v in list(self):
            self.discard(v)

    def update(self, *others: Iterable[_Any]) -> None:  # type: ignore[override]
        for it in others:
            for v in it:
                self.add(v)

    def difference_update(self, *others: Iterable[_Any]) -> None:  # type: ignore[override]
        to_remove = set()
        for it in others:
            for v in it:
                if v in self:
                    to_remove.add(v)
        for v in to_remove:
            self.discard(v)


# ---- Reactive dataclass support ----


_MISSING = object()


class ReactiveProperty(Generic[T]):
    """Unified reactive descriptor used for State fields and dataclass fields."""

    def __init__(self, name: str | None = None, default: _Any = _MISSING):
        self.name: str | None = name
        self.private_name: str | None = None
        self.owner_name: str | None = None
        self.default = (
            wrap_collections(default) if default is not _MISSING else _MISSING
        )

    def __set_name__(self, owner, name):
        self.name = self.name or name
        self.private_name = f"__signal_{self.name}"
        self.owner_name = getattr(owner, "__name__", owner.__class__.__name__)

    def _get_signal(self, obj) -> Signal:
        priv = cast(str, self.private_name)
        sig = getattr(obj, priv, None)
        if sig is None:
            init_value = None if self.default is _MISSING else self.default
            sig = Signal(init_value, name=f"{self.owner_name}.{self.name}")
            setattr(obj, priv, sig)
        return sig

    def __get__(self, obj, objtype=None) -> T:
        if obj is None:
            return self  # type: ignore
        # If there is no signal yet and there was no default, mirror normal attribute error
        priv = cast(str, self.private_name)
        sig = getattr(obj, priv, None)
        if sig is None and self.default is _MISSING:
            owner = self.owner_name or obj.__class__.__name__
            raise AttributeError(
                f"Reactive property '{owner}.{self.name}' accessed before initialization"
            )
        return self._get_signal(obj).read()

    def __set__(self, obj, value: T) -> None:
        sig = self._get_signal(obj)
        value = wrap_collections(value)
        sig.write(value)

    # Helper for State.properties() discovery
    def get_signal(self, obj) -> Signal:
        return self._get_signal(obj)


@overload
def reactive_dataclass(cls: type[T], /, **dataclass_kwargs) -> type[T]: ...
@overload
def reactive_dataclass(**dataclass_kwargs) -> Callable[[type[T]], type[T]]: ...


def reactive_dataclass(
    cls: type[T] | None = None, /, **dataclass_kwargs
) -> Callable[[type[T]], type[T]] | type[T]:
    """Decorator to make a dataclass' fields reactive.

    Usage:
        @reactive_dataclass
        @dataclass
        class Model: ...

    Or simply:
        @reactive_dataclass
        class Model: ...   # will be dataclass()-ed with defaults
    """

    def _wrap(cls_param: type[T]) -> type[T]:
        # ensure it's a dataclass
        klass = cls_param
        if not is_dataclass(klass):
            klass = _dc_dataclass(klass, **dataclass_kwargs)

        # Replace fields with ReactiveProperty descriptors
        for f in _dc_fields(klass):  # type: ignore[arg-type]
            # Skip ClassVars or InitVars implicitly as dataclasses excludes them from fields()
            default_val = f.default if f.default is not _DC_MISSING else _MISSING
            rp = ReactiveProperty(f.name, default_val)
            setattr(klass, f.name, rp)
            # When assigning descriptors post-class-creation, __set_name__ is not called automatically
            rp.__set_name__(klass, f.name)

        return klass

    if cls is None:
        return _wrap
    return _wrap(cls)


# ---- Auto-wrapping helpers ----


def wrap_collections(value: _Any) -> _Any:
    """Wrap built-in collections in their reactive counterparts if not already reactive.

    - dict -> ReactiveDict
    - list -> ReactiveList
    - set -> ReactiveSet
    Leaves other values untouched.
    """
    if isinstance(value, ReactiveDict | ReactiveList | ReactiveSet):
        return value
    if isinstance(value, dict):
        return ReactiveDict(value)
    if isinstance(value, list):
        return ReactiveList(value)
    if isinstance(value, set):
        return ReactiveSet(value)
    return value
