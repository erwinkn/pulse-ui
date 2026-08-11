from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from functools import wraps
from types import TracebackType
from typing import Any, Literal, Self, override

from pulse.env import env


class Resource(ABC):
	"""A value with deterministic, single-owner cleanup."""

	__disposed__: bool = False
	_resource_owner: ResourceScope | None = None

	@abstractmethod
	def dispose(self) -> None: ...

	def _capture(self) -> None:
		scope = ResourceScope.current()
		if scope is not None:
			scope.own(self)

	def __init_subclass__(cls, **kwargs: Any):
		super().__init_subclass__(**kwargs)
		if "dispose" not in cls.__dict__:
			return
		original_dispose = cls.dispose

		@wraps(original_dispose)
		def wrapped_dispose(self: Self, *args: Any, **kwargs: Any):
			if self.__disposed__:
				if env.pulse_env == "dev":
					cls_name = type(self).__name__
					raise RuntimeError(
						f"{self} (type={cls_name}) was disposed twice. This is likely a bug."
					)
				return
			owner = self._resource_owner
			if owner is not None:
				owner.release(self)
			self.__disposed__ = True
			return original_dispose(self, *args, **kwargs)

		cls.dispose = wrapped_dispose


_CURRENT_RESOURCE_SCOPE: ContextVar[ResourceScope | None] = ContextVar(
	"pulse_resource_scope", default=None
)


class ResourceScope(Resource):
	"""Owns resources created during one lexical lifetime."""

	_entered: bool
	_capturing: bool

	def __init__(self, label: str | None = None) -> None:
		self.label: str | None = label
		self._resources: list[Resource] = []
		self._token: Token[ResourceScope | None] | None = None
		self._entered = False
		self._capturing = False
		self._parent: ResourceScope | None = ResourceScope.current()

	@override
	def __repr__(self) -> str:
		if self.label is None:
			return f"<ResourceScope at {hex(id(self))}>"
		return f"<ResourceScope '{self.label}'>"

	def own(self, resource: Resource) -> None:
		if self.__disposed__:
			raise RuntimeError(f"Cannot add a resource to a disposed {self!r}")
		if resource is self:
			raise RuntimeError("ResourceScope cannot own itself")
		if resource.__disposed__:
			raise RuntimeError("Cannot own a disposed resource")
		owner = resource._resource_owner
		if owner is self:
			return
		if owner is not None:
			owner.release(resource)
		resource._resource_owner = self
		if not any(owned is resource for owned in self._resources):
			self._resources.append(resource)

	def adopt(self, resource: Resource) -> bool:
		"""Claim the resource unless an unrelated scope owns it.

		Owns the resource if it is unowned, or if its current owner lexically
		encloses this scope (a handoff from the creating context). Returns
		False when the resource belongs to an unrelated owner.
		"""
		owner = resource._resource_owner
		if owner is not None and not self.within(owner):
			return False
		self.own(resource)
		return True

	def owns(self, resource: Resource) -> bool:
		return resource._resource_owner is self

	def within(self, other: ResourceScope) -> bool:
		"""True if `other` is this scope or one of its lexical ancestors."""
		scope: ResourceScope | None = self
		while scope is not None:
			if scope is other:
				return True
			scope = scope._parent
		return False

	def release(self, resource: Resource) -> None:
		self._resources = [owned for owned in self._resources if owned is not resource]
		if resource._resource_owner is self:
			resource._resource_owner = None

	@classmethod
	def current(cls) -> ResourceScope | None:
		scope = _CURRENT_RESOURCE_SCOPE.get()
		if scope is None or not scope._capturing:
			return None
		return scope

	def __enter__(self) -> ResourceScope:
		if self._entered:
			raise RuntimeError(f"{self!r} cannot be entered more than once")
		if self.__disposed__:
			raise RuntimeError(f"Cannot enter a disposed {self!r}")
		self._entered = True
		self._capturing = True
		self._token = _CURRENT_RESOURCE_SCOPE.set(self)
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		exc_tb: TracebackType | None,
	) -> Literal[False]:
		assert self._token is not None
		_CURRENT_RESOURCE_SCOPE.reset(self._token)
		self._token = None
		self._capturing = False
		if exc_value is not None:
			try:
				self.dispose()
			except BaseException as cleanup_error:
				raise BaseExceptionGroup(
					"ResourceScope cleanup failed", [exc_value, cleanup_error]
				) from None
		return False

	@override
	def dispose(self) -> None:
		if self._capturing:
			raise RuntimeError(f"Cannot dispose {self!r} while it is capturing")
		resources = self._resources
		self._resources = []
		errors: list[BaseException] = []
		for resource in reversed(resources):
			if resource.__disposed__:
				continue
			try:
				resource.dispose()
			except BaseException as error:
				errors.append(error)
		if len(errors) == 1:
			raise errors[0]
		if errors:
			raise BaseExceptionGroup("ResourceScope cleanup failed", errors)


# Attribute names used by the ownership machinery itself. Layers that
# intercept attribute writes and apply ownership rules to Resource values
# (e.g. State.__setattr__) must exempt these names, or they will adopt the
# machinery's own bookkeeping objects.
OWNERSHIP_INTERNAL_ATTRS: frozenset[str] = frozenset(
	{"_resource_owner", "_resource_scope"}
)


class ResourceOwner(Resource):
	"""A Resource that owns other resources through a single ResourceScope.

	This is a thin facade over ResourceScope: it contains no ownership logic
	of its own. It exists to keep the interface of owner classes (states,
	hook states, stores) narrow — subclasses expose only ``resources``,
	``on_dispose()``, and a final ``dispose()`` — and to keep the scope's
	mutable internals off the owner instance, outside any attribute-write
	interception the owner performs.

	The scope is created and attached by the framework or the subclass
	constructor (``self._resource_scope = ResourceScope(...)``), not here:
	subclasses cannot always rely on their ``__init__`` running.
	"""

	_resource_scope: ResourceScope | None = None

	def __init_subclass__(cls, **kwargs: Any) -> None:
		if "dispose" in cls.__dict__:
			raise TypeError(
				f"{cls.__name__} must not override dispose(); "
				+ "override on_dispose() instead"
			)
		super().__init_subclass__(**kwargs)

	@property
	def resources(self) -> ResourceScope:
		"""The scope that owns this object's resources."""
		scope = self._resource_scope
		if scope is None:
			raise RuntimeError(f"{type(self).__name__} has no ResourceScope attached")
		return scope

	def on_dispose(self) -> None:
		"""Override for cleanup that runs before owned resources are disposed."""
		...

	@override
	def dispose(self) -> None:
		"""Run on_dispose(), then dispose the owned ResourceScope.

		Cannot be overridden; override on_dispose() instead.
		"""
		errors: list[BaseException] = []
		try:
			self.on_dispose()
		except BaseException as error:
			errors.append(error)
		scope = self._resource_scope
		if scope is not None and not scope.__disposed__:
			try:
				scope.dispose()
			except BaseException as error:
				errors.append(error)
		if len(errors) == 1:
			raise errors[0]
		if errors:
			raise BaseExceptionGroup(f"{type(self).__name__} cleanup failed", errors)


def current_resource_scope() -> ResourceScope | None:
	return ResourceScope.current()


@contextmanager
def suspend_resource_scope() -> Iterator[None]:
	token = _CURRENT_RESOURCE_SCOPE.set(None)
	try:
		yield
	finally:
		_CURRENT_RESOURCE_SCOPE.reset(token)


__all__ = [
	"OWNERSHIP_INTERNAL_ATTRS",
	"Resource",
	"ResourceOwner",
	"ResourceScope",
	"current_resource_scope",
	"suspend_resource_scope",
]
