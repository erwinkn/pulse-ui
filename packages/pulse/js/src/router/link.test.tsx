import { afterEach, beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { NavigateFn } from "./context";
import { PulseRouterProvider } from "./context";
import { isExternalUrl, Link } from "./link";

// Mock IntersectionObserver
type MockIntersectionObserverCallback = (entries: IntersectionObserverEntry[]) => void;

class MockIntersectionObserver {
	static instances: MockIntersectionObserver[] = [];
	callback: MockIntersectionObserverCallback;
	observedElements: Element[] = [];

	constructor(callback: MockIntersectionObserverCallback) {
		this.callback = callback;
		MockIntersectionObserver.instances.push(this);
	}

	observe(element: Element) {
		this.observedElements.push(element);
	}

	unobserve(element: Element) {
		this.observedElements = this.observedElements.filter((el) => el !== element);
	}

	disconnect() {
		this.observedElements = [];
	}

	// Simulate element entering viewport
	simulateIntersection(isIntersecting: boolean) {
		for (const element of this.observedElements) {
			this.callback([{ isIntersecting, target: element } as IntersectionObserverEntry]);
		}
	}

	static reset() {
		MockIntersectionObserver.instances = [];
	}
}

describe("isExternalUrl", () => {
	it("returns false for relative paths", () => {
		expect(isExternalUrl("/about")).toBe(false);
		expect(isExternalUrl("/users/123")).toBe(false);
		expect(isExternalUrl("about")).toBe(false);
		expect(isExternalUrl("./about")).toBe(false);
		expect(isExternalUrl("../about")).toBe(false);
	});

	it("returns true for http:// URLs", () => {
		expect(isExternalUrl("http://example.com")).toBe(true);
		expect(isExternalUrl("http://example.com/path")).toBe(true);
	});

	it("returns true for https:// URLs to different origins", () => {
		expect(isExternalUrl("https://example.com")).toBe(true);
		expect(isExternalUrl("https://google.com/search")).toBe(true);
	});

	it("returns false for same origin URLs", () => {
		// happy-dom sets window.location.origin dynamically
		const origin = window.location.origin;
		expect(isExternalUrl(origin)).toBe(false);
		expect(isExternalUrl(`${origin}/path`)).toBe(false);
	});

	it("returns true for malformed URLs", () => {
		// Malformed URLs are treated as external for safety
		expect(isExternalUrl("https://")).toBe(true);
	});
});

describe("Link", () => {
	function createWrapper(navigate: NavigateFn) {
		return function Wrapper({ children }: { children: ReactNode }) {
			return (
				<PulseRouterProvider
					location={{ pathname: "/", search: "", hash: "", state: null }}
					params={{}}
					navigate={navigate}
				>
					{children}
				</PulseRouterProvider>
			);
		};
	}

	describe("internal links", () => {
		it("intercepts clicks and calls navigate", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">Test Link</Link>, { wrapper: createWrapper(mockNavigate) });

			fireEvent.click(screen.getByRole("link"));

			expect(mockNavigate).toHaveBeenCalledWith("/about", {
				replace: undefined,
				state: undefined,
			});
		});

		it("renders with correct href", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">Test Link</Link>, { wrapper: createWrapper(mockNavigate) });

			const link = screen.getByRole("link");
			expect(link.getAttribute("href")).toBe("/about");
		});

		it("passes additional props to anchor", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" className="nav-link" data-testid="my-link">
					Test Link
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			const link = screen.getByRole("link");
			expect(link.getAttribute("class")).toBe("nav-link");
			expect(link.getAttribute("data-testid")).toBe("my-link");
		});
	});

	describe("external links", () => {
		it("does not intercept clicks for https:// URLs", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="https://example.com">Test Link</Link>, {
				wrapper: createWrapper(mockNavigate),
			});

			fireEvent.click(screen.getByRole("link"));

			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("does not intercept clicks for http:// URLs", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="http://example.com">Test Link</Link>, {
				wrapper: createWrapper(mockNavigate),
			});

			fireEvent.click(screen.getByRole("link"));

			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("renders with correct href", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="https://example.com">Test Link</Link>, {
				wrapper: createWrapper(mockNavigate),
			});

			const link = screen.getByRole("link");
			expect(link.getAttribute("href")).toBe("https://example.com");
		});

		it("still calls custom onClick for external links", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			const customOnClick = mock(() => {});
			render(
				<Link href="https://example.com" onClick={customOnClick}>
					External
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			fireEvent.click(screen.getByRole("link"));

			expect(customOnClick).toHaveBeenCalled();
			expect(mockNavigate).not.toHaveBeenCalled();
		});
	});

	describe("viewport prefetch", () => {
		let originalIntersectionObserver: typeof IntersectionObserver;
		let consoleLogSpy: ReturnType<typeof spyOn>;

		beforeEach(() => {
			// Clean up any previous renders first
			cleanup();
			MockIntersectionObserver.reset();
			originalIntersectionObserver = globalThis.IntersectionObserver;
			globalThis.IntersectionObserver =
				MockIntersectionObserver as unknown as typeof IntersectionObserver;
			consoleLogSpy = spyOn(console, "log").mockImplementation(() => {});
		});

		afterEach(() => {
			globalThis.IntersectionObserver = originalIntersectionObserver;
			consoleLogSpy.mockRestore();
			cleanup();
		});

		it("sets up IntersectionObserver for internal links", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			expect(MockIntersectionObserver.instances.length).toBe(1);
			expect(MockIntersectionObserver.instances[0].observedElements.length).toBe(1);
		});

		it("fires prefetch event when link enters viewport", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			const observer = MockIntersectionObserver.instances[0];
			observer.simulateIntersection(true);

			expect(consoleLogSpy).toHaveBeenCalledWith("[prefetch] /about");
		});

		it("fires prefetch event only once", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			const observer = MockIntersectionObserver.instances[0];
			observer.simulateIntersection(true);
			observer.simulateIntersection(true);
			observer.simulateIntersection(true);

			expect(consoleLogSpy).toHaveBeenCalledTimes(1);
		});

		it("does not fire prefetch when not intersecting", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			const observer = MockIntersectionObserver.instances[0];
			observer.simulateIntersection(false);

			expect(consoleLogSpy).not.toHaveBeenCalled();
		});

		it("does not set up observer when prefetch={false}", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" prefetch={false}>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			expect(MockIntersectionObserver.instances.length).toBe(0);
		});

		it("does not set up observer for external links", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			// Use a different domain that's definitely external (not same as window.location.origin)
			render(<Link href="https://google.com">External</Link>, {
				wrapper: createWrapper(mockNavigate),
			});

			expect(MockIntersectionObserver.instances.length).toBe(0);
		});

		it("disconnects observer on unmount", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			const { unmount } = render(<Link href="/about">About</Link>, {
				wrapper: createWrapper(mockNavigate),
			});

			const observer = MockIntersectionObserver.instances[0];
			expect(observer.observedElements.length).toBe(1);

			unmount();

			expect(observer.observedElements.length).toBe(0);
		});
	});
});
