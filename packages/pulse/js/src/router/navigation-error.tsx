import { createContext, type ReactNode, useCallback, useContext, useState } from "react";

/**
 * Represents a navigation error that occurred during route transition.
 */
export interface NavigationErrorData {
	pathname: string;
	message: string;
	timestamp: number;
}

/**
 * Navigation error context for managing error state across the app.
 */
export interface NavigationErrorContextValue {
	error: NavigationErrorData | null;
	retry: (pathname: string) => void;
	clear: () => void;
}

export const NavigationErrorContext = createContext<NavigationErrorContextValue | null>(null);

/**
 * Props for NavigationErrorProvider.
 */
export interface NavigationErrorProviderProps {
	children: ReactNode;
}

/**
 * Provider component that manages navigation error state.
 * Typically wraps the entire app to catch navigation errors globally.
 */
export function NavigationErrorProvider({ children }: NavigationErrorProviderProps) {
	const [error, setError] = useState<NavigationErrorData | null>(null);

	const clear = useCallback(() => {
		setError(null);
	}, []);

	const retry = useCallback(
		(_pathname: string) => {
			// Retry will be handled by the client navigation logic
			// Just clear the error state and let navigation happen
			clear();
		},
		[clear],
	);

	return (
		<NavigationErrorContext.Provider value={{ error, retry, clear }}>
			{children}
		</NavigationErrorContext.Provider>
	);
}

/**
 * Hook to access navigation error context.
 * Throws if used outside NavigationErrorProvider.
 */
function useNavigationErrorContext(): NavigationErrorContextValue {
	const ctx = useContext(NavigationErrorContext);
	if (!ctx) {
		throw new Error("useNavigationError must be used within a NavigationErrorProvider");
	}
	return ctx;
}

/**
 * Hook to access and manage navigation errors.
 */
export function useNavigationError() {
	return useNavigationErrorContext();
}

/**
 * NavigationError component - displays error UI with retry button.
 * Matches Next.js style error handling.
 */
export function NavigationError() {
	const { error, retry } = useNavigationErrorContext();

	if (!error) {
		return null;
	}

	const handleRetry = () => {
		retry(error.pathname);
	};

	return (
		<div
			style={{
				position: "fixed",
				inset: 0,
				display: "flex",
				alignItems: "center",
				justifyContent: "center",
				backgroundColor: "rgba(0, 0, 0, 0.5)",
				zIndex: 9998,
				backdropFilter: "blur(4px)",
			}}
		>
			<div
				style={{
					backgroundColor: "white",
					borderRadius: "8px",
					padding: "32px",
					boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
					maxWidth: "500px",
					textAlign: "center",
				}}
			>
				<div
					style={{
						width: "48px",
						height: "48px",
						borderRadius: "50%",
						backgroundColor: "#fee2e2",
						display: "flex",
						alignItems: "center",
						justifyContent: "center",
						margin: "0 auto 16px",
						fontSize: "24px",
					}}
				>
					⚠️
				</div>
				<h1
					style={{
						fontSize: "20px",
						fontWeight: "600",
						color: "#1f2937",
						margin: "0 0 8px 0",
					}}
				>
					Navigation Error
				</h1>
				<p
					style={{
						fontSize: "14px",
						color: "#6b7280",
						margin: "0 0 24px 0",
						lineHeight: "1.5",
					}}
				>
					{error.message || "Failed to navigate to the requested page. Please try again."}
				</p>
				<button
					type="button"
					onClick={handleRetry}
					style={{
						backgroundColor: "#3b82f6",
						color: "white",
						border: "none",
						borderRadius: "6px",
						padding: "10px 20px",
						fontSize: "14px",
						fontWeight: "500",
						cursor: "pointer",
						transition: "background-color 150ms ease-in-out",
					}}
					onMouseEnter={(e) => {
						e.currentTarget.style.backgroundColor = "#2563eb";
					}}
					onMouseLeave={(e) => {
						e.currentTarget.style.backgroundColor = "#3b82f6";
					}}
				>
					Retry
				</button>
			</div>
		</div>
	);
}
