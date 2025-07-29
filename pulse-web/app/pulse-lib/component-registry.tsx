import React, { createContext, useContext } from 'react';
import type { ReactNode, ComponentType } from 'react';

// Type for the component registry - maps string keys to React components
export type ComponentRegistry = Record<string, ComponentType<any>>;

// Context for providing the component registry
const ComponentRegistryContext = createContext<ComponentRegistry | null>(null);

export interface ComponentRegistryProviderProps {
  registry: ComponentRegistry;
  children: ReactNode;
}

export function ComponentRegistryProvider({ registry, children }: ComponentRegistryProviderProps) {
  return (
    <ComponentRegistryContext.Provider value={registry}>
      {children}
    </ComponentRegistryContext.Provider>
  );
}

export function useComponentRegistry(): ComponentRegistry {
  const registry = useContext(ComponentRegistryContext);
  if (!registry) {
    throw new Error('useComponentRegistry must be used within a ComponentRegistryProvider');
  }
  return registry;
}

export function useComponent(componentKey: string): ComponentType<any> {
  const registry = useComponentRegistry();
  const Component = registry[componentKey];
  
  if (!Component) {
    throw new Error(`Component with key '${componentKey}' not found in registry. Available components: ${Object.keys(registry).join(', ')}`);
  }
  
  return Component;
}