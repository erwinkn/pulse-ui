import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Props for the DefaultErrorFallback component.
 */
export interface DefaultErrorFallbackProps {
	error: Error;
	reset: () => void;
}

/**
 * Default fallback UI for ErrorBoundary.
 * Shows error message, stack trace (dev mode only), and a retry button.
 * Minimal styling that works without any CSS framework.
 */
export function DefaultErrorFallback({ error, reset }: DefaultErrorFallbackProps): ReactNode {
	const isDev = process.env.NODE_ENV !== "production";

	return (
		<div
			style={{
				padding: "20px",
				border: "1px solid #e53e3e",
				borderRadius: "8px",
				backgroundColor: "#fff5f5",
				color: "#c53030",
				fontFamily: "system-ui, sans-serif",
			}}
		>
			<h2 style={{ margin: "0 0 10px 0", fontSize: "18px" }}>Something went wrong</h2>
			<p style={{ margin: "0 0 15px 0", fontSize: "14px" }}>{error.message}</p>
			{isDev && error.stack && (
				<pre
					style={{
						margin: "0 0 15px 0",
						padding: "10px",
						backgroundColor: "#fed7d7",
						borderRadius: "4px",
						fontSize: "12px",
						overflow: "auto",
						whiteSpace: "pre-wrap",
						wordBreak: "break-word",
					}}
				>
					{error.stack}
				</pre>
			)}
			<button
				type="button"
				onClick={reset}
				style={{
					padding: "8px 16px",
					backgroundColor: "#c53030",
					color: "white",
					border: "none",
					borderRadius: "4px",
					cursor: "pointer",
					fontSize: "14px",
				}}
			>
				Retry
			</button>
		</div>
	);
}

/**
 * Props for the ErrorBoundary component.
 */
export interface ErrorBoundaryProps {
	children: ReactNode;
	/**
	 * Custom fallback render function. Receives the error and a reset function.
	 * If not provided, a default fallback UI is used.
	 */
	fallback?: (error: Error, reset: () => void) => ReactNode;
}

/**
 * State for the ErrorBoundary component.
 */
interface ErrorBoundaryState {
	error: Error | null;
}

/**
 * React ErrorBoundary component that catches JavaScript errors in its child tree.
 * Renders a fallback UI when an error is caught instead of crashing the whole app.
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary fallback={(error, reset) => <div>{error.message} <button onClick={reset}>Retry</button></div>}>
 *   <MyComponent />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
	constructor(props: ErrorBoundaryProps) {
		super(props);
		this.state = { error: null };
	}

	static getDerivedStateFromError(error: Error): ErrorBoundaryState {
		return { error };
	}

	override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
		// Log error to console in development
		console.error("ErrorBoundary caught an error:", error, errorInfo);
	}

	/**
	 * Reset the error state, allowing children to be re-rendered.
	 */
	reset = (): void => {
		this.setState({ error: null });
	};

	override render(): ReactNode {
		const { error } = this.state;
		const { children, fallback } = this.props;

		if (error) {
			// If custom fallback is provided, use it
			if (fallback) {
				return fallback(error, this.reset);
			}

			// Use default fallback component
			return <DefaultErrorFallback error={error} reset={this.reset} />;
		}

		return children;
	}
}
