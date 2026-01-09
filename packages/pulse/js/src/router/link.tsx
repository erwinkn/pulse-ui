import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from "react";
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
}

/**
 * Navigation link component that integrates with PulseRouter.
 * Renders an anchor tag but intercepts clicks to use client-side navigation.
 * External links (different origin) are rendered without interception.
 */
export function Link({ href, children, replace, state, onClick, ...rest }: LinkProps) {
	const navigate = useNavigate();
	const isExternal = isExternalUrl(href);

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

	// External links render without click interception
	if (isExternal) {
		return (
			<a href={href} onClick={onClick} {...rest}>
				{children}
			</a>
		);
	}

	return (
		<a href={href} onClick={handleClick} {...rest}>
			{children}
		</a>
	);
}
