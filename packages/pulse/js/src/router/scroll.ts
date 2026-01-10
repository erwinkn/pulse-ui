import { useEffect, useRef } from "react";
import { useLocation } from "./context";

/**
 * Store scroll positions keyed by pathname.
 */
const scrollPositions = new Map<string, { x: number; y: number }>();

/**
 * Store the most recent navigation's preventScrollReset flag.
 */
let lastPreventScrollReset = false;

/**
 * Save the current scroll position for the given pathname.
 */
export function saveScrollPosition(pathname: string): void {
	scrollPositions.set(pathname, {
		x: window.scrollX,
		y: window.scrollY,
	});
}

/**
 * Restore the scroll position for the given pathname.
 * If no saved position exists, scrolls to the top.
 */
export function restoreScrollPosition(pathname: string, preventReset?: boolean): void {
	if (preventReset) {
		// Don't reset scroll - browser handles it naturally
		return;
	}

	const savedPosition = scrollPositions.get(pathname);
	if (savedPosition) {
		window.scrollTo(savedPosition.x, savedPosition.y);
	} else {
		// No saved position - scroll to top
		window.scrollTo(0, 0);
	}
}

/**
 * Store the preventScrollReset flag for the current navigation.
 * Called by the navigate function to communicate its intent to the hook.
 */
export function setScrollResetPrevention(prevent: boolean): void {
	lastPreventScrollReset = prevent;
}

/**
 * Hook that manages scroll position restoration on navigation.
 * - On navigation to a new page, saves current scroll position
 * - After navigation completes, restores scroll position for new page
 * - Respects preventScrollReset option passed to navigate()
 *
 * This is typically called at the root of your app to manage scroll
 * restoration globally, but can be used per-route if needed.
 *
 * Must be used within a PulseRouterProvider.
 *
 * Example:
 * ```tsx
 * function App() {
 *   useScrollRestoration();
 *   return <Routes />;
 * }
 * ```
 */
export function useScrollRestoration(): void {
	const { pathname } = useLocation();
	const prevPathnameRef = useRef<string | null>(null);

	useEffect(() => {
		// On mount, store initial pathname
		if (prevPathnameRef.current === null) {
			prevPathnameRef.current = pathname;
		}
	}, [pathname]);

	useEffect(() => {
		// Pathname changed - this is a navigation
		if (prevPathnameRef.current !== null && pathname !== prevPathnameRef.current) {
			// Save scroll position for the previous page
			saveScrollPosition(prevPathnameRef.current);

			// Update previous pathname
			prevPathnameRef.current = pathname;

			// Schedule scroll restoration after React renders
			// Use requestAnimationFrame to ensure DOM is ready
			requestAnimationFrame(() => {
				restoreScrollPosition(pathname, lastPreventScrollReset);
				// Reset the flag after use
				lastPreventScrollReset = false;
			});
		}
	}, [pathname]);
}
