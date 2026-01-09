import { describe, expect, it, mock } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";
import { DefaultErrorFallback, ErrorBoundary } from "./error-boundary";

// Suppress console.error from ErrorBoundary during tests
const originalConsoleError = console.error;
function suppressConsoleError() {
	console.error = mock(() => {});
}
function restoreConsoleError() {
	console.error = originalConsoleError;
}

// Component that throws an error
function ThrowingComponent({ error }: { error: Error }): never {
	throw error;
}

// Component that works normally
function WorkingComponent() {
	return <div>Working content</div>;
}

describe("ErrorBoundary", () => {
	describe("default fallback", () => {
		it("renders children when no error occurs", () => {
			render(
				<ErrorBoundary>
					<WorkingComponent />
				</ErrorBoundary>,
			);

			expect(screen.getByText("Working content")).toBeDefined();
		});

		it("renders default fallback when error occurs", () => {
			suppressConsoleError();
			try {
				render(
					<ErrorBoundary>
						<ThrowingComponent error={new Error("Test error message")} />
					</ErrorBoundary>,
				);

				expect(screen.getByText("Something went wrong")).toBeDefined();
				expect(screen.getByText("Test error message")).toBeDefined();
				expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
			} finally {
				restoreConsoleError();
			}
		});

		it("resets error state when reset button is clicked", () => {
			suppressConsoleError();
			try {
				let shouldThrow = true;
				function ConditionalThrower() {
					if (shouldThrow) {
						throw new Error("Test error");
					}
					return <div>Recovered</div>;
				}

				render(
					<ErrorBoundary>
						<ConditionalThrower />
					</ErrorBoundary>,
				);

				expect(screen.getByText("Something went wrong")).toBeDefined();

				// Fix the error condition before clicking reset
				shouldThrow = false;
				fireEvent.click(screen.getByRole("button", { name: "Retry" }));

				expect(screen.getByText("Recovered")).toBeDefined();
			} finally {
				restoreConsoleError();
			}
		});
	});

	describe("custom fallback", () => {
		it("renders custom fallback when provided", () => {
			suppressConsoleError();
			try {
				const customFallback = (error: Error, reset: () => void) => (
					<div>
						<span>Custom error: {error.message}</span>
						<button type="button" onClick={reset}>
							Custom Reset
						</button>
					</div>
				);

				render(
					<ErrorBoundary fallback={customFallback}>
						<ThrowingComponent error={new Error("Custom test error")} />
					</ErrorBoundary>,
				);

				expect(screen.getByText("Custom error: Custom test error")).toBeDefined();
				expect(screen.getByRole("button", { name: "Custom Reset" })).toBeDefined();
				// Default fallback should not be present
				expect(screen.queryByText("Something went wrong")).toBeNull();
			} finally {
				restoreConsoleError();
			}
		});

		it("passes error object to custom fallback", () => {
			suppressConsoleError();
			try {
				const testError = new Error("Error with details");
				const customFallback = mock((error: Error, _reset: () => void) => (
					<div>Got error: {error.message}</div>
				));

				render(
					<ErrorBoundary fallback={customFallback}>
						<ThrowingComponent error={testError} />
					</ErrorBoundary>,
				);

				expect(customFallback).toHaveBeenCalled();
				const [receivedError] = customFallback.mock.calls[0];
				expect(receivedError.message).toBe("Error with details");
			} finally {
				restoreConsoleError();
			}
		});

		it("passes working reset function to custom fallback", () => {
			suppressConsoleError();
			try {
				let shouldThrow = true;
				function ConditionalThrower() {
					if (shouldThrow) {
						throw new Error("Test error");
					}
					return <div>Custom Recovered</div>;
				}

				const customFallback = (_error: Error, reset: () => void) => (
					<div>
						<span>Error caught</span>
						<button type="button" onClick={reset}>
							Custom Retry
						</button>
					</div>
				);

				render(
					<ErrorBoundary fallback={customFallback}>
						<ConditionalThrower />
					</ErrorBoundary>,
				);

				expect(screen.getByText("Error caught")).toBeDefined();

				// Fix the error condition before clicking reset
				shouldThrow = false;
				fireEvent.click(screen.getByRole("button", { name: "Custom Retry" }));

				expect(screen.getByText("Custom Recovered")).toBeDefined();
			} finally {
				restoreConsoleError();
			}
		});

		it("does not use custom fallback for non-error state", () => {
			const customFallback = mock((_error: Error, _reset: () => void) => (
				<div>Should not appear</div>
			));

			render(
				<ErrorBoundary fallback={customFallback}>
					<WorkingComponent />
				</ErrorBoundary>,
			);

			expect(screen.getByText("Working content")).toBeDefined();
			expect(customFallback).not.toHaveBeenCalled();
		});
	});
});

describe("DefaultErrorFallback", () => {
	it("renders error message", () => {
		const error = new Error("Detailed error message");
		const reset = mock(() => {});

		render(<DefaultErrorFallback error={error} reset={reset} />);

		expect(screen.getByText("Something went wrong")).toBeDefined();
		expect(screen.getByText("Detailed error message")).toBeDefined();
	});

	it("renders retry button that calls reset", () => {
		const error = new Error("Test error");
		const reset = mock(() => {});

		render(<DefaultErrorFallback error={error} reset={reset} />);

		const button = screen.getByRole("button", { name: "Retry" });
		expect(button).toBeDefined();

		fireEvent.click(button);
		expect(reset).toHaveBeenCalledTimes(1);
	});

	it("shows stack trace in development mode", () => {
		const originalNodeEnv = process.env.NODE_ENV;
		process.env.NODE_ENV = "development";

		try {
			const error = new Error("Test error");
			error.stack = "Error: Test error\n    at TestComponent (test.tsx:10:5)";
			const reset = mock(() => {});

			render(<DefaultErrorFallback error={error} reset={reset} />);

			expect(screen.getByText(/at TestComponent/)).toBeDefined();
		} finally {
			process.env.NODE_ENV = originalNodeEnv;
		}
	});
});
