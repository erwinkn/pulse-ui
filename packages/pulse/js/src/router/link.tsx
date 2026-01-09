import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from "react";
import { useNavigate } from "./context";

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
 */
export function Link({ href, children, replace, state, onClick, ...rest }: LinkProps) {
	const navigate = useNavigate();

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

	return (
		<a href={href} onClick={handleClick} {...rest}>
			{children}
		</a>
	);
}
