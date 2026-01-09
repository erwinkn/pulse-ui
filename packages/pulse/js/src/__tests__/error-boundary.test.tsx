import { afterEach, beforeEach, describe, expect, it, mock } from "bun:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DefaultErrorFallback, ErrorBoundary } from "../error-boundary";

/**
 * Integration tests for ErrorBoundary component.
 * Verifies error catching, fallback rendering, and recovery behavior.
 */

// Suppress console.error during tests
const originalConsoleError = console.error;
function suppressConsoleError() {
	console.error = mock(() => {});
}
function restoreConsoleError() {
	console.error = originalConsoleError;
}

// Component that throws an error on render
function ThrowingComponent({ error }: { error: Error }): never {
	throw error;
}

// Normal working component
function WorkingComponent({ text = "Working content" }: { text?: string }) {
	return <div data-testid="working">{text}</div>;
}

describe("ErrorBoundary Integration", () => {
	beforeEach(() => {
		cleanup();
	});

	afterEach(() => {
		restoreConsoleError();
	});

	describe("error catching", () => {
		it("catches errors thrown by child components", () => {
			suppressConsoleError();

			render(
				<ErrorBoundary>
					<ThrowingComponent error={new Error("Child threw an error")} />
				</ErrorBoundary>,
			);

			// Error should be caught - fallback UI should be visible
			expect(screen.getByText("Something went wrong")).toBeDefined();
			expect(screen.getByText("Child threw an error")).toBeDefined();
		});

		it("catches errors in nested component hierarchies", () => {
			suppressConsoleError();

			render(
				<ErrorBoundary>
					<div>
						<section>
							<ThrowingComponent error={new Error("Deep nested error")} />
						</section>
					</div>
				</ErrorBoundary>,
			);

			expect(screen.getByText("Something went wrong")).toBeDefined();
			expect(screen.getByText("Deep nested error")).toBeDefined();
		});

		it("does not catch errors when children render successfully", () => {
			render(
				<ErrorBoundary>
					<WorkingComponent />
				</ErrorBoundary>,
			);

			expect(screen.getByTestId("working")).toBeDefined();
			expect(screen.queryByText("Something went wrong")).toBeNull();
		});
	});

	describe("default fallback rendering", () => {
		it("renders default fallback with error message", () => {
			suppressConsoleError();

			render(
				<ErrorBoundary>
					<ThrowingComponent error={new Error("Specific error message")} />
				</ErrorBoundary>,
			);

			expect(screen.getByText("Something went wrong")).toBeDefined();
			expect(screen.getByText("Specific error message")).toBeDefined();
		});

		it("renders retry button in default fallback", () => {
			suppressConsoleError();

			render(
				<ErrorBoundary>
					<ThrowingComponent error={new Error("Test error")} />
				</ErrorBoundary>,
			);

			const retryButton = screen.getByRole("button", { name: "Retry" });
			expect(retryButton).toBeDefined();
		});

		it("shows stack trace in dev mode", () => {
			suppressConsoleError();

			const error = new Error("Dev mode error");
			error.stack = "Error: Dev mode error\n    at SomeComponent (file.tsx:42:10)";

			render(
				<ErrorBoundary>
					<ThrowingComponent error={error} />
				</ErrorBoundary>,
			);

			// Stack trace should be visible in dev mode (NODE_ENV !== 'production')
			expect(screen.getByText(/at SomeComponent/)).toBeDefined();
		});
	});

	describe("custom fallback", () => {
		it("renders custom fallback when provided", () => {
			suppressConsoleError();

			const customFallback = (error: Error, _reset: () => void) => (
				<div data-testid="custom-fallback">
					<h1>Custom Error UI</h1>
					<p>Error: {error.message}</p>
				</div>
			);

			render(
				<ErrorBoundary fallback={customFallback}>
					<ThrowingComponent error={new Error("Custom handled error")} />
				</ErrorBoundary>,
			);

			expect(screen.getByTestId("custom-fallback")).toBeDefined();
			expect(screen.getByText("Custom Error UI")).toBeDefined();
			expect(screen.getByText("Error: Custom handled error")).toBeDefined();
			// Default fallback should NOT be rendered
			expect(screen.queryByText("Something went wrong")).toBeNull();
		});

		it("passes error object to custom fallback", () => {
			suppressConsoleError();

			const errorMessage = "Error with specific details";
			const capturedError = { current: null as Error | null };

			const customFallback = (error: Error, _reset: () => void) => {
				capturedError.current = error;
				return <div>Captured</div>;
			};

			render(
				<ErrorBoundary fallback={customFallback}>
					<ThrowingComponent error={new Error(errorMessage)} />
				</ErrorBoundary>,
			);

			expect(capturedError.current).not.toBeNull();
			expect(capturedError.current?.message).toBe(errorMessage);
		});

		it("passes working reset function to custom fallback", () => {
			suppressConsoleError();

			let shouldThrow = true;

			function ConditionalThrower() {
				if (shouldThrow) {
					throw new Error("Resettable error");
				}
				return <div data-testid="recovered">Recovered via custom reset</div>;
			}

			const customFallback = (_error: Error, reset: () => void) => (
				<div data-testid="custom-fallback">
					<button type="button" onClick={reset} data-testid="custom-reset">
						Reset Error State
					</button>
				</div>
			);

			render(
				<ErrorBoundary fallback={customFallback}>
					<ConditionalThrower />
				</ErrorBoundary>,
			);

			expect(screen.getByTestId("custom-fallback")).toBeDefined();

			// Fix the condition before resetting
			shouldThrow = false;

			// Click reset to clear error state
			fireEvent.click(screen.getByTestId("custom-reset"));

			// After reset, children should render
			expect(screen.getByTestId("recovered")).toBeDefined();
		});
	});

	describe("reset behavior", () => {
		it("clears error state when reset is called", () => {
			suppressConsoleError();

			let shouldThrow = true;

			function ConditionalThrower() {
				if (shouldThrow) {
					throw new Error("Clearable error");
				}
				return <div data-testid="recovered">Cleared and recovered</div>;
			}

			render(
				<ErrorBoundary>
					<ConditionalThrower />
				</ErrorBoundary>,
			);

			// Verify error is caught
			expect(screen.getByText("Something went wrong")).toBeDefined();
			expect(screen.getByText("Clearable error")).toBeDefined();

			// Fix the error condition before clicking reset
			shouldThrow = false;

			// Click the retry button
			fireEvent.click(screen.getByRole("button", { name: "Retry" }));

			// Children should now render
			expect(screen.getByTestId("recovered")).toBeDefined();
			expect(screen.queryByText("Something went wrong")).toBeNull();
		});

		it("re-renders children after reset", () => {
			suppressConsoleError();

			let shouldThrow = true;

			function ConditionalThrower() {
				if (shouldThrow) {
					throw new Error("Will be fixed");
				}
				return <div>Successfully recovered</div>;
			}

			render(
				<ErrorBoundary>
					<ConditionalThrower />
				</ErrorBoundary>,
			);

			// Error state
			expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();

			// Fix and reset
			shouldThrow = false;
			fireEvent.click(screen.getByRole("button", { name: "Retry" }));

			// Verify children re-rendered
			expect(screen.getByText("Successfully recovered")).toBeDefined();
		});

		it("catches new errors after reset if child still throws", () => {
			suppressConsoleError();

			render(
				<ErrorBoundary>
					<ThrowingComponent error={new Error("Persistent error")} />
				</ErrorBoundary>,
			);

			// First error caught
			expect(screen.getByText("Persistent error")).toBeDefined();

			// Reset - but child will still throw
			fireEvent.click(screen.getByRole("button", { name: "Retry" }));

			// Error should be caught again
			expect(screen.getByText("Persistent error")).toBeDefined();
		});
	});

	describe("multiple error boundaries", () => {
		it("only catches errors in its own subtree", () => {
			suppressConsoleError();

			render(
				<div>
					<ErrorBoundary>
						<ThrowingComponent error={new Error("Error in boundary 1")} />
					</ErrorBoundary>
					<ErrorBoundary>
						<WorkingComponent text="Unaffected content" />
					</ErrorBoundary>
				</div>,
			);

			// First boundary caught its error
			expect(screen.getByText("Error in boundary 1")).toBeDefined();
			// Second boundary still works
			expect(screen.getByText("Unaffected content")).toBeDefined();
		});

		it("nested boundaries catch errors at closest level", () => {
			suppressConsoleError();

			render(
				<ErrorBoundary fallback={(error, _reset) => <div>Outer: {error.message}</div>}>
					<div>
						<ErrorBoundary fallback={(error, _reset) => <div>Inner: {error.message}</div>}>
							<ThrowingComponent error={new Error("Nested error")} />
						</ErrorBoundary>
					</div>
				</ErrorBoundary>,
			);

			// Inner boundary should catch
			expect(screen.getByText("Inner: Nested error")).toBeDefined();
			// Outer boundary should not have caught
			expect(screen.queryByText("Outer: Nested error")).toBeNull();
		});
	});
});

describe("DefaultErrorFallback Integration", () => {
	it("can be used standalone with error and reset props", () => {
		const error = new Error("Standalone fallback error");
		const resetMock = mock(() => {});

		render(<DefaultErrorFallback error={error} reset={resetMock} />);

		expect(screen.getByText("Something went wrong")).toBeDefined();
		expect(screen.getByText("Standalone fallback error")).toBeDefined();

		fireEvent.click(screen.getByRole("button", { name: "Retry" }));
		expect(resetMock).toHaveBeenCalledTimes(1);
	});
});
