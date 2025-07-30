"""
Reactive state system for Pulse UI.

This module provides the base State class and reactive property system
that enables automatic re-rendering when state changes.
"""

from typing import Any, Dict, Set, Optional, Callable, TypeVar
import weakref
from dataclasses import dataclass, field
from abc import ABC, ABCMeta

# Global context for tracking state access during rendering
_current_context: Optional['RenderContext'] = None

T = TypeVar('T')


class StateProperty:
    """
    Descriptor that creates reactive properties on State classes.
    Tracks when properties are accessed and triggers updates when set.
    """
    
    def __init__(self, name: str, default_value: Any = None):
        self.name = name
        self.default_value = default_value
        self.private_name = f"_state_{name}"
    
    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
            
        # Track that this property was accessed during rendering
        if _current_context is not None:
            _current_context.track_state_access(obj, self.name)
        
        # Return the current value or default
        return getattr(obj, self.private_name, self.default_value)
    
    def __set__(self, obj: Any, value: Any) -> None:
        # Get the old value
        old_value = getattr(obj, self.private_name, self.default_value)
        
        # Only trigger updates if the value actually changed
        if old_value != value:
            # Set the new value
            setattr(obj, self.private_name, value)
            
            # Trigger reactive updates
            obj._notify_listeners(self.name, old_value, value)


class StateMeta(ABCMeta):
    """
    Metaclass that automatically converts annotated attributes into reactive properties.
    """
    
    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        # Get type annotations
        annotations = namespace.get('__annotations__', {})
        
        # Convert annotated attributes to reactive properties
        for attr_name, attr_type in annotations.items():
            if not attr_name.startswith('_'):
                # Check if there's a default value
                default_value = namespace.get(attr_name, None)
                
                # Create a StateProperty descriptor
                namespace[attr_name] = StateProperty(attr_name, default_value)
        
        return super().__new__(mcs, name, bases, namespace)


class State(ABC, metaclass=StateMeta):
    """
    Base class for reactive state objects.
    
    Define state properties using type annotations:
    
    ```python
    class CounterState(ps.State):
        count: int = 0
        name: str = "Counter"
    ```
    
    Properties will automatically trigger re-renders when changed.
    """
    
    def __init__(self):
        # Track listeners for this state instance
        self._listeners: Dict[str, Set[Callable]] = {}
        
        # Track which active routes depend on this state
        self._route_listeners: Set['ActiveRoute'] = set()
    
    def _notify_listeners(self, property_name: str, old_value: Any, new_value: Any):
        """Notify all listeners that a property has changed."""
        
        # Notify property-specific listeners
        if property_name in self._listeners:
            for listener in self._listeners[property_name].copy():
                try:
                    listener(property_name, old_value, new_value)
                except Exception as e:
                    print(f"Error in state listener: {e}")
        
        # Notify all active routes that depend on this state
        for route in self._route_listeners.copy():
            try:
                route._trigger_rerender()
            except Exception as e:
                print(f"Error triggering route rerender: {e}")
    
    def _add_route_listener(self, route: 'ActiveRoute'):
        """Add an active route as a listener for this state."""
        self._route_listeners.add(route)
    
    def _remove_route_listener(self, route: 'ActiveRoute'):
        """Remove an active route listener."""
        self._route_listeners.discard(route)


@dataclass
class RenderContext:
    """
    Context object that tracks state access during route rendering.
    """
    
    # Map of state instances to the properties accessed
    accessed_states: Dict[State, Set[str]] = field(default_factory=dict)
    
    # The route being rendered (if any)
    active_route: Optional['ActiveRoute'] = None
    
    def track_state_access(self, state: State, property_name: str):
        """Track that a state property was accessed during rendering."""
        if state not in self.accessed_states:
            self.accessed_states[state] = set()
        
        self.accessed_states[state].add(property_name)
        
        # Register the active route as a listener for this state
        if self.active_route:
            state._add_route_listener(self.active_route)


def set_render_context(context: Optional[RenderContext]):
    """Set the global render context for tracking state access."""
    global _current_context
    _current_context = context


def get_render_context() -> Optional[RenderContext]:
    """Get the current render context."""
    return _current_context