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

/**
 * Resolves a relative path against a base path.
 * Handles: "../sibling", "./child", "child", absolute paths
 */
function resolvePath(to: string, basePath: string): string {
	// Absolute paths are returned as-is
	if (to.startsWith("/")) {
		return to;
	}

	// Split base path into segments, removing empty strings
	const baseSegments = basePath.split("/").filter(Boolean);

	// Handle "./" prefix - relative to current directory
	if (to.startsWith("./")) {
		to = to.slice(2);
	}

	// Split the target path
	const toSegments = to.split("/").filter(Boolean);

	// Start from base segments
	const resultSegments = [...baseSegments];

	for (const segment of toSegments) {
		if (segment === "..") {
			// Go up one level
			resultSegments.pop();
		} else if (segment !== ".") {
			// Add the segment (ignore ".")
			resultSegments.push(segment);
		}
	}

	return `/${resultSegments.join("/")}`;
}

/**
 * Hook to get the navigate function.
 * Returns a function that handles both absolute and relative paths.
 * - `navigate('/path')` - absolute navigation
 * - `navigate('/path', { replace: true })` - replace history
 * - `navigate('/path', { state: {...} })` - with state
 * - `navigate('../sibling')` - relative path resolution
 * - `navigate(-1)` - go back in history
 * Throws if used outside a PulseRouterProvider.
 */
export function useNavigate(): NavigateFn {
	const { navigate, location } = usePulseRouterContext();

	// Create a wrapped navigate function that resolves relative paths
	const wrappedNavigate: NavigateFn = ((toOrDelta: string | number, options?: NavigateOptions) => {
		// History navigation (number) - pass through directly
		if (typeof toOrDelta === "number") {
			navigate(toOrDelta);
			return;
		}

		// Path navigation - resolve relative paths first
		const resolvedPath = resolvePath(toOrDelta, location.pathname);
		navigate(resolvedPath, options);
	}) as NavigateFn;

	return wrappedNavigate;
}
