import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";

/**
 * Navigation progress context value.
 */
export interface NavigationProgressContextValue {
	/** Whether navigation is currently in progress */
	isNavigating: boolean;
	/** Start the navigation progress indicator */
	startNavigation: () => void;
	/** Complete the navigation progress indicator */
	completeNavigation: () => void;
}

const NavigationProgressContext = createContext<NavigationProgressContextValue | null>(null);

/**
 * Hook to access the navigation progress context.
 * Returns null if used outside NavigationProgressProvider.
 */
export function useNavigationProgress(): NavigationProgressContextValue | null {
	return useContext(NavigationProgressContext);
}

/**
 * Props for NavigationProgressProvider.
 */
export interface NavigationProgressProviderProps {
	children: ReactNode;
}

/**
 * Provider component that manages navigation progress state.
 * Wrap your app with this to enable the progress indicator.
 */
export function NavigationProgressProvider({ children }: NavigationProgressProviderProps) {
	const [isNavigating, setIsNavigating] = useState(false);

	function startNavigation() {
		setIsNavigating(true);
	}

	function completeNavigation() {
		setIsNavigating(false);
	}

	return (
		<NavigationProgressContext.Provider
			value={{ isNavigating, startNavigation, completeNavigation }}
		>
			{children}
		</NavigationProgressContext.Provider>
	);
}

/**
 * Props for NavigationProgress component.
 */
export interface NavigationProgressProps {
	/** Color of the progress bar. Defaults to #0070f3 (blue). */
	color?: string;
	/** Height of the progress bar in pixels. Defaults to 3. */
	height?: number;
}

/**
 * Navigation progress indicator component.
 * Renders a thin bar at the top of the viewport that animates during navigation.
 *
 * Must be used within a NavigationProgressProvider.
 * If used outside, renders nothing.
 */
export function NavigationProgress({ color = "#0070f3", height = 3 }: NavigationProgressProps) {
	const progressCtx = useNavigationProgress();
	const isNavigating = progressCtx?.isNavigating ?? false;
	const [progress, setProgress] = useState(0);
	const [visible, setVisible] = useState(false);
	const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
	const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

	useEffect(() => {
		// Cleanup function for intervals and timeouts
		const clearTimers = () => {
			if (intervalRef.current) {
				clearInterval(intervalRef.current);
				intervalRef.current = null;
			}
			if (timeoutRef.current) {
				clearTimeout(timeoutRef.current);
				timeoutRef.current = null;
			}
		};

		if (isNavigating) {
			// Start the progress animation
			clearTimers();
			setProgress(0);
			setVisible(true);

			// Animate from 0% to ~90% over time
			// Uses exponential slowdown to create natural loading feel
			intervalRef.current = setInterval(() => {
				setProgress((prev) => {
					if (prev >= 90) {
						return prev; // Cap at 90%
					}
					// Slow down as we approach 90%
					const increment = (90 - prev) * 0.1;
					return Math.min(90, prev + Math.max(0.5, increment));
				});
			}, 100);
		} else if (visible) {
			// Complete the animation
			clearTimers();
			setProgress(100);

			// Hide after animation completes
			timeoutRef.current = setTimeout(() => {
				setVisible(false);
				setProgress(0);
			}, 200);
		}

		return clearTimers;
	}, [isNavigating, visible]);

	// Don't render if no context or not visible
	if (!progressCtx || !visible) {
		return null;
	}

	return (
		<div
			style={{
				position: "fixed",
				top: 0,
				left: 0,
				right: 0,
				height: `${height}px`,
				zIndex: 9999,
				pointerEvents: "none",
			}}
		>
			<div
				style={{
					height: "100%",
					width: `${progress}%`,
					backgroundColor: color,
					transition: progress === 100 ? "width 200ms ease-out" : "width 100ms ease-out",
				}}
			/>
		</div>
	);
}
