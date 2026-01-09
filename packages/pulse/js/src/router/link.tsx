import {
	type AnchorHTMLAttributes,
	type MouseEvent,
	type ReactNode,
	useEffect,
	useRef,
} from "react";
import { useNavigate } from "./context";

/**
 * Check if a URL is external (different origin or absolute URL).
 */
export function isExternalUrl(href: string): boolean {
	// Absolute URLs starting with http:// or https://
	if (href.startsWith("http://") || href.startsWith("https://")) {
		try {
			const url = new URL(href);
			return url.origin !== window.location.origin;
		} catch {
			// Invalid URL, treat as external to be safe
			return true;
		}
	}
	return false;
}

/**
 * Props for Link component.
 * Extends standard anchor attributes but requires href.
 */
export interface LinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
	href: string;
	children?: ReactNode;
	replace?: boolean;
	state?: unknown;
	/** Enable viewport prefetch. Defaults to true. Set to false to disable. */
	prefetch?: boolean;
}

/**
 * Navigation link component that integrates with PulseRouter.
 * Renders an anchor tag but intercepts clicks to use client-side navigation.
 * External links (different origin) are rendered without interception.
 */
export function Link({
	href,
	children,
	replace,
	state,
	onClick,
	prefetch = true,
	...rest
}: LinkProps) {
	const navigate = useNavigate();
	const isExternal = isExternalUrl(href);
	const anchorRef = useRef<HTMLAnchorElement>(null);
	const prefetchedRef = useRef(false);

	// Set up IntersectionObserver for viewport prefetch
	useEffect(() => {
		// Skip if external, prefetch disabled, or already prefetched
		if (isExternal || !prefetch || prefetchedRef.current) {
			return;
		}

		const element = anchorRef.current;
		if (!element) {
			return;
		}

		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting && !prefetchedRef.current) {
						prefetchedRef.current = true;
						console.log(`[prefetch] ${href}`);
						observer.disconnect();
					}
				}
			},
			{ rootMargin: "0px" },
		);

		observer.observe(element);

		return () => {
			observer.disconnect();
		};
	}, [href, isExternal, prefetch]);

	function handleClick(e: MouseEvent<HTMLAnchorElement>) {
		// Call any existing onClick handler first
		onClick?.(e);

		// Don't intercept if already prevented
		if (e.defaultPrevented) {
			return;
		}

		// Don't intercept modified clicks (new tab, etc.)
		if (e.metaKey || e.altKey || e.ctrlKey || e.shiftKey) {
			return;
		}

		// Prevent default anchor behavior
		e.preventDefault();

		// Navigate using router
		navigate(href, { replace, state });
	}

	// External links render without click interception or prefetch
	if (isExternal) {
		return (
			<a href={href} onClick={onClick} {...rest}>
				{children}
			</a>
		);
	}

	return (
		<a ref={anchorRef} href={href} onClick={handleClick} {...rest}>
			{children}
		</a>
	);
}
