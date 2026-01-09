import { createContext, type ReactNode, useContext } from "react";

/**
 * Location object representing the current URL state.
 */
export interface Location {
	pathname: string;
	search: string;
	hash: string;
	state: unknown;
}

/**
 * Params extracted from the current route pattern.
 * Values can be:
 * - string: for regular dynamic params (:id)
 * - undefined: for optional params (:id?) that weren't provided
 * - string[]: for catch-all (*)
 */
export type Params = Record<string, string | undefined | string[]>;

/**
 * Navigation options for the navigate function.
 */
export interface NavigateOptions {
	replace?: boolean;
	state?: unknown;
}

/**
 * Navigate function signature.
 * Accepts either a path string or a number (for history navigation like -1).
 */
export type NavigateFn = {
	(to: string, options?: NavigateOptions): void;
	(delta: number): void;
};

/**
 * Context value provided by PulseRouterProvider.
 */
export interface PulseRouterContextValue {
	location: Location;
	params: Params;
	navigate: NavigateFn;
}

export const PulseRouterContext = createContext<PulseRouterContextValue | null>(null);

/**
 * Props for PulseRouterProvider.
 */
export interface PulseRouterProviderProps {
	children: ReactNode;
	location: Location;
	params: Params;
	navigate: NavigateFn;
}

/**
 * Provider component that wraps children with router context.
 * Typically injected by Python into the VDOM at route boundaries.
 */
export function PulseRouterProvider({
	children,
	location,
	params,
	navigate,
}: PulseRouterProviderProps) {
	return (
		<PulseRouterContext.Provider value={{ location, params, navigate }}>
			{children}
		</PulseRouterContext.Provider>
	);
}

/**
 * Internal hook to access the router context.
 * Throws if used outside a PulseRouterProvider.
 */
export function usePulseRouterContext(): PulseRouterContextValue {
	const ctx = useContext(PulseRouterContext);
	if (!ctx) {
		throw new Error("useLocation/useParams/useNavigate must be used within a PulseRouterProvider");
	}
	return ctx;
}

/**
 * Hook to access the current location.
 * Returns { pathname, search, hash, state } from the nearest PulseRouterContext.
 * Throws if used outside a PulseRouterProvider.
 */
export function useLocation(): Location {
	return usePulseRouterContext().location;
}

/**
 * Hook to access route params from the nearest PulseRouterContext.
 * Returns scoped params - only params extracted at the current route level.
 * Parent route params are accessed via Pulse Context (server state).
 * Throws if used outside a PulseRouterProvider.
 */
export function useParams(): Params {
	return usePulseRouterContext().params;
}
