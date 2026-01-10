import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NavigationError, NavigationErrorProvider, useNavigationError } from "./navigation-error";

let setErrorExternal: ((error: any) => void) | null = null;

const TestComponent = () => {
	const { error, retry } = useNavigationError();

	return (
		<div>
			{error && (
				<div>
					<p>Error: {error.message}</p>
					<p>Path: {error.pathname}</p>
					<button type="button" onClick={() => retry(error.pathname)}>
						Retry from component
					</button>
				</div>
			)}
			<button
				type="button"
				onClick={() => {
					if (setErrorExternal) {
						setErrorExternal({
							pathname: "/test",
							message: "Test error",
							timestamp: Date.now(),
						});
					}
				}}
			>
				Trigger Error
			</button>
		</div>
	);
};

// Note: This is a test helper that may not be directly used in current tests
// but keeps the component structure for reference
const _ProviderWrapper = () => {
	const [_error, setError] = React.useState<any>(null);

	React.useEffect(() => {
		setErrorExternal = setError;
	}, []);

	return (
		<NavigationErrorProvider>
			<TestComponent />
			<NavigationError />
		</NavigationErrorProvider>
	);
};

describe("NavigationError component", () => {
	beforeEach(() => {
		setErrorExternal = null;
	});

	afterEach(() => {
		cleanup();
	});

	it("renders null when no error", () => {
		const { container } = render(
			<NavigationErrorProvider>
				<NavigationError />
			</NavigationErrorProvider>,
		);
		expect(container.firstChild).toBe(null);
	});

	it("provides useNavigationError hook", () => {
		const TestHookComponent = () => {
			const { error, retry, clear } = useNavigationError();
			return (
				<div>
					{error && <p>Error present</p>}
					<button type="button" onClick={() => clear()}>
						Clear
					</button>
					<button type="button" onClick={() => retry("/path")}>
						Retry
					</button>
				</div>
			);
		};

		render(
			<NavigationErrorProvider>
				<TestHookComponent />
			</NavigationErrorProvider>,
		);

		const clearBtn = screen.getByText("Clear");
		const retryBtn = screen.getByText("Retry");

		expect(clearBtn).toBeTruthy();
		expect(retryBtn).toBeTruthy();
	});

	it("throws error when useNavigationError used outside provider", () => {
		const ThrowingComponent = () => {
			const ctx = useNavigationError();
			return <div>{ctx.error ? "Error" : "No error"}</div>;
		};

		try {
			render(<ThrowingComponent />);
			expect(true).toBeFalse();
		} catch (e) {
			expect((e as Error).message).toContain("must be used within a NavigationErrorProvider");
		}
	});
});

describe("NavigationErrorProvider", () => {
	afterEach(() => {
		cleanup();
	});

	it("provides context to children", () => {
		const TestComponent = () => {
			const ctx = useNavigationError();
			return <div>{ctx.error ? "Has error" : "No error"}</div>;
		};

		render(
			<NavigationErrorProvider>
				<TestComponent />
			</NavigationErrorProvider>,
		);

		expect(screen.getByText("No error")).toBeTruthy();
	});

	it("handles clear function", () => {
		const TestComponent = () => {
			const { error, clear } = useNavigationError();
			return (
				<div>
					{error && <p>Error: {error.message}</p>}
					<button type="button" onClick={clear}>
						Clear
					</button>
				</div>
			);
		};

		render(
			<NavigationErrorProvider>
				<TestComponent />
			</NavigationErrorProvider>,
		);

		const clearBtn = screen.getByText("Clear");
		fireEvent.click(clearBtn);
		expect(screen.queryByText(/Error:/)).toBe(null);
	});
});

// Import React for the test
import React from "react";
