# ============================================================================
# React Component Integration
# ============================================================================


from contextvars import ContextVar
from typing import Literal, Optional

from pulse.vdom import Node, NodeChild, _extract_callbacks_from_props


class ReactComponent:
    """
    A React component that can be used within the UI tree.
    Returns a function that creates mount point UITreeNode instances.

    Args:
        tag: Name of the component (or "default" for default export)
        import_path: Module path to import the component from
        alias: Optional alias for the component in the registry
        is_default: True if this is a default export, else named export

    Returns:
        A function that creates Node instances with mount point tags
    """

    def __init__(
        self,
        tag: str | Literal["default"],
        import_path: str,
        alias: str | None = None,
        is_default=False,
        default_props: Optional[dict] = None 
    ):
        self.tag = tag
        self.key = alias or tag
        self.import_path = import_path
        self.alias = alias
        self.default_props = default_props
        self.is_default = is_default
        if is_default and alias:
            raise ValueError(
                "A default import cannot have an alias (it uses the tag as the name)."
            )

        COMPONENT_REGISTRY.get().add(self)

    def __call__(self, *children: NodeChild, **props) -> Node:
        if self.default_props:
            props = props | self.default_props
        props, callbacks = _extract_callbacks_from_props(props)
        return Node(
            tag=f"$${self.key}",
            props=props,
            callbacks=callbacks,
            children=list(children) if children else [],
        )


class ComponentRegistry:
    """A registry for React components that can be used as a context manager."""

    def __init__(self):
        self._components: dict[str, ReactComponent] = {}
        self._token = None

    def add(self, component: ReactComponent):
        """Adds a component to the registry."""
        if component.key in self._components:
            raise ValueError(f"Duplicate component key {component.key}")
        self._components[component.key] = component

    def clear(self):
        self._components.clear()

    def remove(self, key: str):
        """Removes a component from the registry by its key."""
        if key in self._components:
            del self._components[key]

    def get(self, key: str):
        """Gets a component from the registry by its key."""
        return self._components.get(key)

    def items(self):
        """Returns a copy of the components as a dictionary."""
        return self._components.copy()

    def list(self):
        return list(self._components.values())

    def __enter__(self) -> "ComponentRegistry":
        self._token = COMPONENT_REGISTRY.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            COMPONENT_REGISTRY.reset(self._token)
            self._token = None


COMPONENT_REGISTRY: ContextVar[ComponentRegistry] = ContextVar(
    "component_registry", default=ComponentRegistry()
)


def registered_react_components():
    """Get all registered React components."""
    return COMPONENT_REGISTRY.get().list()
