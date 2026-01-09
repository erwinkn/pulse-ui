import { useEffect } from "react";
import { routeLoaders } from "../routes";

/** Tracks prefetched routes to avoid duplicate calls */
const prefetchedRoutes = new Set<string>();

/**
 * Prefetch a route's chunk without awaiting.
 * Triggers dynamic import in background to warm the cache.
 * @param pattern - The route pattern (e.g., "/", "/dashboard")
 */
export function prefetchRoute(pattern: string): void {
	if (prefetchedRoutes.has(pattern)) {
		return;
	}

	const loader = routeLoaders[pattern];
	if (!loader) {
		return;
	}

	prefetchedRoutes.add(pattern);
	loader();
}

/**
 * Create hover event handlers that prefetch a route.
 * @param pattern - The route pattern to prefetch on hover
 * @returns Object with onMouseEnter handler
 */
export function createHoverPrefetch(pattern: string): {
	onMouseEnter: () => void;
} {
	return {
		onMouseEnter: () => prefetchRoute(pattern),
	};
}

/**
 * Hook to prefetch a route when element enters viewport.
 * @param pattern - The route pattern to prefetch
 * @param ref - React ref to the element to observe
 */
export function usePrefetchOnViewport(pattern: string, ref: React.RefObject<Element | null>): void {
	useEffect(() => {
		const element = ref.current;
		if (!element) {
			return;
		}

		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting) {
						prefetchRoute(pattern);
						observer.disconnect();
						break;
					}
				}
			},
			{ rootMargin: "50px" },
		);

		observer.observe(element);

		return () => observer.disconnect();
	}, [pattern, ref]);
}
