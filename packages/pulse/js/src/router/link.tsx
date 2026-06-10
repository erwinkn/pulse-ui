import type { AnchorHTMLAttributes, MouseEvent } from "react";
import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "./router";

export type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
	to: string;
	/**
	 * Prefetch strategy:
	 * - "intent" (default): prefetch on hover/focus
	 * - "viewport": prefetch when the link scrolls into view
	 * - "render": prefetch as soon as the link renders
	 * - "none": never prefetch
	 */
	prefetch?: "none" | "intent" | "render" | "viewport";
	/** Skip client routing and let the browser load the document. */
	reloadDocument?: boolean;
	replace?: boolean;
};

export function Link({
	to,
	prefetch = "intent",
	reloadDocument,
	replace,
	onClick,
	onMouseEnter,
	onFocus,
	...rest
}: LinkProps) {
	const { navigate, prefetch: prefetchRoute } = useRouter();
	const ref = useRef<HTMLAnchorElement | null>(null);

	useEffect(() => {
		if (prefetch === "render") {
			prefetchRoute(to);
		}
	}, [prefetch, prefetchRoute, to]);

	useEffect(() => {
		if (prefetch !== "viewport") {
			return;
		}
		const el = ref.current;
		if (!el || !("IntersectionObserver" in window)) {
			return;
		}
		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting) {
						prefetchRoute(to);
						observer.disconnect();
						break;
					}
				}
			},
			{ rootMargin: "50px" },
		);
		observer.observe(el);
		return () => observer.disconnect();
	}, [prefetch, prefetchRoute, to]);

	const handleClick = useCallback(
		(event: MouseEvent<HTMLAnchorElement>) => {
			onClick?.(event);
			if (
				event.defaultPrevented ||
				event.button !== 0 ||
				event.metaKey ||
				event.altKey ||
				event.ctrlKey ||
				event.shiftKey
			) {
				return;
			}
			if (reloadDocument) {
				return;
			}
			event.preventDefault();
			navigate(to, { replace });
		},
		[navigate, onClick, reloadDocument, replace, to],
	);

	const handleMouseEnter = useCallback(
		(event: MouseEvent<HTMLAnchorElement>) => {
			onMouseEnter?.(event);
			if (prefetch === "intent") {
				prefetchRoute(to);
			}
		},
		[onMouseEnter, prefetch, prefetchRoute, to],
	);

	const handleFocus = useCallback(
		(event: React.FocusEvent<HTMLAnchorElement>) => {
			onFocus?.(event);
			if (prefetch === "intent") {
				prefetchRoute(to);
			}
		},
		[onFocus, prefetch, prefetchRoute, to],
	);

	return (
		<a
			{...rest}
			ref={ref}
			href={to}
			onClick={handleClick}
			onMouseEnter={handleMouseEnter}
			onFocus={handleFocus}
		/>
	);
}
