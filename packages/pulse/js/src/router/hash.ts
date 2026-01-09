import { useEffect, useRef } from "react";
import { useLocation } from "./context";

/**
 * Scroll to an element by its id with smooth scrolling.
 * Does nothing if the element doesn't exist.
 */
export function scrollToHash(hash: string): void {
	// Remove leading # if present
	const id = hash.startsWith("#") ? hash.slice(1) : hash;

	// Empty hash - nothing to scroll to
	if (!id) {
		return;
	}

	const element = document.getElementById(id);
	if (element) {
		element.scrollIntoView({ behavior: "smooth" });
	}
}

/**
 * Hook that scrolls to the element matching the current location hash.
 * Works on:
 * - Initial page load (if URL has a hash)
 * - Client navigation (when hash changes)
 *
 * Must be used within a PulseRouterProvider.
 */
export function useHashScroll(): void {
	const { hash } = useLocation();
	const prevHashRef = useRef<string>("");

	useEffect(() => {
		// Skip if hash hasn't changed
		if (hash === prevHashRef.current) {
			return;
		}
		prevHashRef.current = hash;

		// Scroll to element if hash exists
		if (hash) {
			// Small delay to ensure DOM is ready after navigation
			requestAnimationFrame(() => {
				scrollToHash(hash);
			});
		}
	}, [hash]);
}
