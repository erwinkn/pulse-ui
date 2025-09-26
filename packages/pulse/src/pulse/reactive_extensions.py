from __future__ import (
    annotations,
)  # required to use dataclasses._DataclassT in this file
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import MISSING as _DC_MISSING
from dataclasses import dataclass as _dc_dataclass
from dataclasses import fields as _dc_fields
from dataclasses import is_dataclass
from dataclasses import InitVar as _DC_InitVar
from dataclasses import FrozenInstanceError as _DC_FrozenInstanceError
from typing import Any as _Any, Optional
from typing import Callable, Generic, TypeVar, overload, cast
import weakref

from pulse import Untrack
from pulse.reactive import Computed, Signal

T1 = TypeVar("T1")
T2 = TypeVar("T2")


_MISSING = object()


class ReactiveDict(dict[T1, T2]):
    """A dict-like container with per-key reactivity.

    - Reading a key registers a dependency on that key's Signal
    - Writing a key updates only that key's Signal
    - Deleting a key removes the key from the mapping but preserves the Signal object
      (writes `None` to it) for existing subscribers
    - Iteration, membership checks, and len are reactive to structural changes
    """

    __slots__ = ("_signals", "_structure")

    def __init__(self, initial: Mapping[T1, T2] | None = None) -> None:
        super().__init__()
        self._signals: dict[T1, Signal[_Any]] = {}
        self._structure: Signal[int] = Signal(0)
        if initial:
            for k, v in initial.items():
                v = reactive(v)
                super().__setitem__(k, v)
                self._signals[k] = Signal(v)

    # ---- helpers ----
    def _bump_structure(self) -> None:
        self._structure.write(self._structure.read() + 1)

    # --- Mapping protocol ---
    def __getitem__(self, key: T1) -> T2:
        if key not in self._signals:
            # Lazily create missing key with sentinel so it can be reactive
            self._signals[key] = Signal(_MISSING)
        val = self._signals[key].read()
        # Preserve dict.__getitem__ typing by casting. Semantics: return None
        # only if the stored value is explicitly None; otherwise unwrap sentinel.
        return cast(T2, None) if val is _MISSING else cast(T2, val)

    def __setitem__(self, key: T1, value: T2) -> None:
        self.set(key, value)

    def __delitem__(self, key: T1) -> None:
        # Remove from mapping but preserve signal object for subscribers
        if key not in self._signals:
            self._signals[key] = Signal(_MISSING)
        else:
            self._signals[key].write(_MISSING)
        if super().__contains__(key):
            super().__delitem__(key)
            self._bump_structure()

    @overload
    def get(self, key: T1, default: T2) -> T2: ...
    @overload
    def get(self, key: T1, default: None = None) -> Optional[T2]: ...
    def get(self, key: T1, default: Optional[T2] = None) -> Optional[T2]:  # type: ignore[override]
        # Ensure a per-key signal exists so get() can subscribe even when absent
        sig = self._signals.get(key)
        if sig is None:
            sig = cast(Signal[T2], Signal(_MISSING))
            self._signals[key] = sig
        val = sig.read()
        return default if val is _MISSING else val

    def __iter__(self) -> Iterator[T1]:
        # Reactive to structural changes
        _ = self._structure.read()
        return super().__iter__()

    def __len__(self) -> int:
        _ = self._structure.read()
        return super().__len__()

    def __contains__(self, key: T1) -> bool:  # type: ignore[override]
        # Subscribe to the per-key value signal so presence checks are reactive
        sig = self._signals.get(key)
        if sig is None:
            sig = Signal(_MISSING)
            self._signals[key] = sig
        _ = sig.read()
        return dict.__contains__(self, key)

    # --- Mutation helpers ---
    def set(self, key: T1, value: T2) -> None:
        value = reactive(value)
        was_present = super().__contains__(key)
        sig = self._signals.get(key)
        if sig is None:
            self._signals[key] = Signal(value)
        else:
            sig.write(value)
        super().__setitem__(key, value)
        if not was_present:
            self._bump_structure()

    def update(  # type: ignore[override]
        self,
        other: Mapping[T1, T2] | Iterable[tuple[T1, T2]] | None = None,
        /,
        **kwargs: T2,
    ) -> None:
        # Match dict.update semantics
        if other is not None:
            if isinstance(other, Mapping):
                other = cast(Mapping[T1, T2], other)
                for k, v in other.items():
                    self.set(k, v)
            else:
                for k, v in other:
                    self.set(k, v)
        if kwargs:
            for k, v in kwargs.items():
                self.set(cast(T1, k), v)

    def delete(self, key: T1) -> None:
        if key in self._signals:
            # Preserve signal and mark as not present; do not raise
            self._signals[key].write(_MISSING)
            if super().__contains__(key):
                super().__delitem__(key)
                self._bump_structure()

    # ---- standard dict methods ----
    def keys(self):  # type: ignore[override]
        _ = self._structure.read()
        return super().keys()

    def items(self):  # type: ignore[override]
        # Return an iterable view that subscribes to per-key signals during iteration
        class _ReactiveDictItemsView:
            __slots__ = ("_host",)

            def __init__(self, host: "ReactiveDict[T1, T2]") -> None:
                self._host = host

            def __iter__(self):
                _ = self._host._structure.read()
                for k in dict.__iter__(self._host):
                    yield (k, self._host[k])

            def __len__(self) -> int:
                _ = self._host._structure.read()
                return dict.__len__(self._host)

        return _ReactiveDictItemsView(self)

    def values(self):  # type: ignore[override]
        # Return an iterable view that subscribes to per-key signals during iteration
        class _ReactiveDictValuesView:
            __slots__ = ("_host",)

            def __init__(self, host: "ReactiveDict[T1, T2]") -> None:
                self._host = host

            def __iter__(self):
                _ = self._host._structure.read()
                for k in dict.__iter__(self._host):
                    yield self._host[k]

            def __len__(self) -> int:
                _ = self._host._structure.read()
                return dict.__len__(self._host)

        return _ReactiveDictValuesView(self)

    def pop(self, key: T1, default: _Any = _MISSING):  # type: ignore[override]
        if super().__contains__(key):
            val = dict.__getitem__(self, key)
            self.__delitem__(key)
            return val
        if default is _MISSING:
            raise KeyError(key)
        return default

    def popitem(self):  # type: ignore[override]
        if not super().__len__():
            raise KeyError("popitem(): dictionary is empty")
        k, v = super().popitem()
        # Preserve and update reactive metadata
        sig = self._signals.get(k)
        if sig is None:
            self._signals[k] = Signal(_MISSING)
        else:
            sig.write(_MISSING)
        self._bump_structure()
        return k, v

    def setdefault(self, key: T1, default: T2 | None = None) -> T2:  # type: ignore[override]
        if super().__contains__(key):
            # Return current value without structural change
            if key not in self._signals:
                self._signals[key] = Signal(_MISSING)
            return self._signals[key].read()
        # Insert default
        self.set(key, default)  # type: ignore[arg-type]
        # Read structure after write to suppress immediate rerun of the current
        # effect (if this is used in an effect) caused by the structural bump
        # performed in set().
        _ = self._structure.read()
        sig = self._signals.get(key)
        if sig is None:
            sig = cast(Signal[T2], Signal(_MISSING))
            self._signals[key] = sig
        return sig.read()

    def clear(self) -> None:  # type: ignore[override]
        if not super().__len__():
            return
        for k in list(super().keys()):
            # Use our deletion to keep signals/presence updated
            self.__delitem__(k)
        # bump already done per key; nothing else needed

    def copy(self):  # type: ignore[override]
        # Shallow copy preserving current values
        return ReactiveDict({k: dict.__getitem__(self, k) for k in super().__iter__()})

    @classmethod
    def fromkeys(cls, iterable: Iterable[T1], value: _Any = None):  # type: ignore[override]
        rd: ReactiveDict[T1, _Any] = cls()
        for k in iterable:
            rd.set(k, value)
        return rd

    # PEP 584 dict union operators
    def __ior__(self, other):  # type: ignore[override]
        self.update(other)
        return self

    def __or__(self, other):  # type: ignore[override]
        result = ReactiveDict(self)
        result.update(other)
        return result

    def __ror__(self, other):  # type: ignore[override]
        result = ReactiveDict(other)
        result.update(self)
        return result

    def unwrap(self) -> dict[T1, _Any]:
        """Return a plain dict while subscribing to contained signals."""
        _ = self._structure.read()
        result: dict[T1, _Any] = {}
        for key in dict.__iter__(self):
            result[key] = unwrap(self[key])
        return result


class ReactiveList(list[T1]):
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
                v = reactive(item)
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
                wrapped = [reactive(v) for v in replacement_seq]
                super().__setitem__(idx, wrapped)
                for i, v in zip(target_indices, wrapped):
                    self._signals[i].write(v)
                return

            super().__setitem__(idx, replacement_seq)
            self._signals = [Signal(reactive(v)) for v in super().__iter__()]
            self._bump_structure()
            return
        # normal index
        v = reactive(value)
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
        v = reactive(value)
        super().append(v)
        self._signals.append(Signal(v))
        self._bump_structure()

    def extend(self, values: Iterable[_Any]) -> None:  # type: ignore[override]
        any_added = False
        for v in values:
            vv = reactive(v)
            super().append(vv)
            self._signals.append(Signal(vv))
            any_added = True
        if any_added:
            self._bump_structure()

    def insert(self, index: int, value: _Any) -> None:  # type: ignore[override]
        v = reactive(value)
        super().insert(index, v)
        self._signals.insert(index, Signal(v))
        self._bump_structure()

    def pop(self, index: int = -1):  # type: ignore[override]
        val = super().pop(index)
        del self._signals[index]
        self._bump_structure()
        return val

    def unwrap(self) -> list[_Any]:
        """Return a plain list while subscribing to element signals."""
        _ = self.version
        return [unwrap(self[i]) for i in range(len(self._signals))]

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

        def key_for_index(i: int):
            v = current[i]
            return key(v) if callable(key) else v

        idxs.sort(key=key_for_index, reverse=reverse)  # type: ignore
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


class ReactiveSet(set[T1]):
    """A set with per-element membership reactivity.

    - `x in s` reads a membership Signal for element `x`
    - Mutations update membership Signals for affected elements
    - Iteration and len are NOT reactive
    """

    __slots__ = ("_signals",)

    def __init__(self, initial: Iterable[T1] | None = None) -> None:
        super().__init__()
        self._signals: dict[T1, Signal[bool]] = {}
        if initial:
            for v in initial:
                vv = reactive(v)
                super().add(vv)
                self._signals[vv] = Signal(True)

    def __contains__(self, element: T1) -> bool:  # type: ignore[override]
        sig = self._signals.get(element)
        if sig is None:
            present = set.__contains__(self, element)
            self._signals[element] = Signal(bool(present))
            sig = self._signals[element]
        return bool(sig.read())

    def membership(self, element: T1) -> bool:
        """Reactive check for membership of a value.

        Equivalent to `x in s` but explicitly documents reactivity.
        """
        return self.__contains__(element)

    # mutations
    def add(self, element: T1) -> None:
        element = reactive(element)
        super().add(element)
        sig = self._signals.get(element)
        if sig is None:
            self._signals[element] = Signal(True)
        else:
            sig.write(True)

    def discard(self, element: T1) -> None:
        element = reactive(element)
        if element in self:
            super().discard(element)
            sig = self._signals.get(element)
            if sig is None:
                self._signals[element] = Signal(False)
            else:
                sig.write(False)

    def remove(self, element: T1) -> None:
        if element not in self:
            raise KeyError(element)
        self.discard(element)

    def clear(self) -> None:
        for v in list(self):
            self.discard(v)

    def update(self, *others: Iterable[T1]) -> None:
        for it in others:
            for v in it:
                self.add(v)

    def difference_update(self, *others: Iterable[T1]) -> None:
        to_remove = set()
        for it in others:
            for v in it:
                if v in self:
                    to_remove.add(v)
        for v in to_remove:
            self.discard(v)

    def unwrap(self) -> set[_Any]:
        """Return a plain set while subscribing to membership signals."""
        result: set[_Any] = set()
        for value in set.__iter__(self):
            _ = self.membership(value)
            result.add(unwrap(value))
        return result


# ---- Reactive dataclass support ----


_MISSING = object()


# Fallback storage for signal instances on objects that cannot hold attributes
# (e.g., slotted dataclasses). Keys are object ids; entries are cleaned up via
# a weakref finalizer when possible. This avoids requiring objects to be hashable.
_INSTANCE_SIGNAL_STORE_BY_ID: dict[int, dict[str, Signal]] = {}
_INSTANCE_STORE_WEAKREFS: dict[int, weakref.ref] = {}

# Cache mapping original dataclass type -> generated reactive dataclass subclass
_REACTIVE_DATACLASS_CACHE: dict[type, type] = {}

# Track objects currently initializing via dataclass __init__ or reactive upgrade
_INITIALIZING_OBJECT_IDS: set[int] = set()


def _copy_dataclass_params(parent: type) -> dict[str, _Any]:
    params = getattr(parent, "__dataclass_params__", None)
    if params is None:
        return {}
    copied: dict[str, _Any] = {}
    for key in (
        "init",
        "repr",
        "eq",
        "order",
        "unsafe_hash",
        "frozen",
        "match_args",
        "kw_only",
        "slots",
        "weakref_slot",
    ):
        if hasattr(params, key):
            copied[key] = getattr(params, key)
    return copied


def _get_reactive_dataclass_class(parent: type) -> type:
    # Already reactive?
    if getattr(parent, "__is_reactive_dataclass__", False):
        return parent
    cached = _REACTIVE_DATACLASS_CACHE.get(parent)
    if cached is not None:
        return cached
    if not is_dataclass(parent):
        raise TypeError("_get_reactive_dataclass_class expects a dataclass type")

    subclass_name = f"Reactive{parent.__name__}"
    subclass = type(
        subclass_name,
        (parent,),
        {
            "__module__": parent.__module__,
            "__doc__": getattr(parent, "__doc__", None),
        },
    )

    # Mirror parent dataclass parameters when generating dataclass on subclass
    dc_kwargs = _copy_dataclass_params(parent)
    reactive_subclass = reactive_dataclass(subclass, **dc_kwargs)  # type: ignore[arg-type]
    setattr(reactive_subclass, "__is_reactive_dataclass__", True)
    setattr(reactive_subclass, "__reactive_base__", parent)

    # Hide InitVar attributes on instances by shadowing with a descriptor that raises
    class _HiddenInitVar:
        def __get__(self, obj, objtype=None):
            raise AttributeError

    parent_annotations = getattr(parent, "__annotations__", {}) or {}
    for _name, _anno in parent_annotations.items():
        # Detect dataclasses.InitVar annotations (e.g., InitVar[int])
        try:
            if isinstance(_anno, _DC_InitVar):
                setattr(reactive_subclass, _name, _HiddenInitVar())
        except Exception:
            pass

    # Wrap __init__ to allow field assignment during construction even if frozen
    original_init = getattr(reactive_subclass, "__init__", None)
    if callable(original_init):

        def _wrapped_init(self, *args, **kwargs):
            _INITIALIZING_OBJECT_IDS.add(id(self))
            try:
                return original_init(self, *args, **kwargs)
            finally:
                _INITIALIZING_OBJECT_IDS.discard(id(self))

        setattr(reactive_subclass, "__init__", _wrapped_init)

    _REACTIVE_DATACLASS_CACHE[parent] = reactive_subclass
    return reactive_subclass


class ReactiveProperty(Generic[T1]):
    """Unified reactive descriptor used for State fields and dataclass fields."""

    def __init__(self, name: str | None = None, default: Optional[T1] = _MISSING):
        self.name: str | None = name
        self.private_name: str | None = None
        self.owner_name: str | None = None
        self.default = reactive(default) if default is not _MISSING else _MISSING

    def __set_name__(self, owner, name):
        self.name = self.name or name
        self.private_name = f"__signal_{self.name}"
        self.owner_name = getattr(owner, "__name__", owner.__class__.__name__)

    def _get_signal(self, obj) -> Signal[T1]:
        priv = cast(str, self.private_name)
        # Try fast path: attribute on the instance
        try:
            sig = getattr(obj, priv)
        except AttributeError:
            sig = None

        # Fallback store for slotted instances (no __dict__) using id(obj)
        if sig is None:
            per_obj = _INSTANCE_SIGNAL_STORE_BY_ID.get(id(obj))
            if per_obj is not None:
                sig = per_obj.get(priv)

        if sig is None:
            init_value = None if self.default is _MISSING else self.default
            sig = Signal(init_value, name=f"{self.owner_name}.{self.name}")
            # Try to attach to the instance; if that fails (e.g., __slots__), use fallback store
            try:
                setattr(obj, priv, sig)
            except Exception:
                obj_id = id(obj)
                mapping = _INSTANCE_SIGNAL_STORE_BY_ID.get(obj_id)
                if mapping is None:
                    mapping = {}
                    _INSTANCE_SIGNAL_STORE_BY_ID[obj_id] = mapping
                    # Install a weakref to clean up when object is GC'd
                    try:
                        _INSTANCE_STORE_WEAKREFS[obj_id] = weakref.ref(
                            obj,
                            lambda _r, oid=obj_id: (
                                _INSTANCE_SIGNAL_STORE_BY_ID.pop(oid, None),
                                _INSTANCE_STORE_WEAKREFS.pop(oid, None),
                            ),
                        )
                    except TypeError:
                        # Object not weakref-able; best effort leak-free by reusing id slot if recreated
                        pass
                mapping[priv] = sig
        return cast(Signal[T1], sig)

    def __get__(self, obj, objtype=None) -> T1:
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

    def __set__(self, obj, value: T1) -> None:
        sig = self._get_signal(obj)
        value = reactive(value)
        sig.write(value)

    # Helper for State.properties() discovery
    def get_signal(self, obj) -> Signal:
        return self._get_signal(obj)


class DataclassReactiveProperty(ReactiveProperty[T1]):
    """Reactive descriptor for dataclass fields with frozen enforcement."""

    def __init__(self, name: str | None = None, default: Optional[T1] = _MISSING):
        super().__init__(name, default)
        self.owner_cls: type | None = None

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        self.owner_cls = owner

    def __set__(self, obj, value: T1) -> None:  # type: ignore[override]
        # Enforce frozen dataclasses semantics
        owner = self.owner_cls or obj.__class__
        params = getattr(owner, "__dataclass_params__", None)
        if (
            params is not None
            and getattr(params, "frozen", False)
            and id(obj) not in _INITIALIZING_OBJECT_IDS
        ):
            # Match dataclasses' message
            raise _DC_FrozenInstanceError(f"cannot assign to field '{self.name}'")
        super().__set__(obj, value)


@overload
def reactive_dataclass(cls: type, /, **dataclass_kwargs) -> type: ...
@overload
def reactive_dataclass(
    **dataclass_kwargs,
) -> Callable[[type], type]: ...


def reactive_dataclass(
    cls: type | None = None, /, **dataclass_kwargs
) -> Callable[[type], type] | type:
    """Decorator to make a dataclass' fields reactive.

    Usage:
        @reactive_dataclass
        @dataclass
        class Model: ...

    Or simply:
        @reactive_dataclass
        class Model: ...   # will be dataclass()-ed with defaults
    """

    def _wrap(
        cls_param: type,
    ) -> type:
        # ensure it's a dataclass
        klass = cls_param
        if not is_dataclass(klass):
            klass = _dc_dataclass(klass, **dataclass_kwargs)

        # Replace fields with DataclassReactiveProperty descriptors
        for f in _dc_fields(klass):  # type: ignore[arg-type]
            # Skip ClassVars or InitVars implicitly as dataclasses excludes them from fields()
            default_val = f.default if f.default is not _DC_MISSING else _MISSING
            rp = DataclassReactiveProperty(f.name, default_val)
            setattr(klass, f.name, rp)
            # When assigning descriptors post-class-creation, __set_name__ is not called automatically
            rp.__set_name__(klass, f.name)

        return klass

    if cls is None:
        return _wrap
    return _wrap(cls)


# ---- Auto-wrapping helpers ----


@overload
def reactive(value: dict[T1, T2]) -> ReactiveDict[T1, T2]: ...
@overload
def reactive(value: list[T1]) -> ReactiveList[T1]: ...
@overload
def reactive(value: set[T1]) -> ReactiveSet[T1]: ...
@overload
def reactive(value: T1) -> T1: ...


def reactive(value: _Any) -> _Any:
    """Wrap built-in collections in their reactive counterparts if not already reactive.

    - dict -> ReactiveDict
    - list -> ReactiveList
    - set -> ReactiveSet
    Leaves other values untouched.
    """
    if isinstance(value, ReactiveDict | ReactiveList | ReactiveSet):
        return value
    # Dataclass instance: upgrade to reactive subclass in-place
    if not isinstance(value, type) and is_dataclass(value):
        # Already reactive instance?
        if getattr(type(value), "__is_reactive_dataclass__", False):
            return value
        base_cls = cast(type, type(value))
        reactive_cls = _get_reactive_dataclass_class(base_cls)
        # Capture current field values
        field_values: dict[str, _Any] = {}
        for f in _dc_fields(base_cls):  # type: ignore[arg-type]
            try:
                field_values[f.name] = getattr(value, f.name)
            except Exception:
                field_values[f.name] = None
        # For dict-backed instances, drop raw attrs to avoid stale shadowing
        if hasattr(value, "__dict__") and isinstance(value.__dict__, dict):
            for name in field_values.keys():
                value.__dict__.pop(name, None)
        # Swap class
        value.__class__ = reactive_cls  # type: ignore[assignment]
        # Write back via descriptors (handles frozen via object.__setattr__)
        _INITIALIZING_OBJECT_IDS.add(id(value))
        try:
            for name, v in field_values.items():
                object.__setattr__(value, name, reactive(v))
        finally:
            _INITIALIZING_OBJECT_IDS.discard(id(value))
        return value
    if isinstance(value, dict):
        return ReactiveDict(value)
    if isinstance(value, list):
        return ReactiveList(value)
    if isinstance(value, set):
        return ReactiveSet(value)
    if isinstance(value, type) and is_dataclass(value):
        return _get_reactive_dataclass_class(value)
    return value


def unwrap(value: _Any, untrack: bool = False) -> _Any:
    """Recursively unwrap reactive containers into plain Python values.

    Args:
        value: The value to unwrap
        untrack: Whether to not track dependencies during unwrapping. Defaults to False.
    """

    def _unwrap(v: _Any) -> _Any:
        if isinstance(v, (Signal, Computed)):
            return _unwrap(v.unwrap())
        if isinstance(v, ReactiveDict):
            return v.unwrap()
        if isinstance(v, ReactiveList):
            return v.unwrap()
        if isinstance(v, ReactiveSet):
            return v.unwrap()
        if isinstance(v, Mapping):
            return {k: _unwrap(val) for k, val in v.items()}
        if isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray)):
            if isinstance(v, tuple):
                return tuple(_unwrap(val) for val in v)
            return [_unwrap(val) for val in v]
        if isinstance(v, set):
            return {_unwrap(val) for val in v}
        return v

    if untrack:
        with Untrack():
            return _unwrap(value)
    return _unwrap(value)
