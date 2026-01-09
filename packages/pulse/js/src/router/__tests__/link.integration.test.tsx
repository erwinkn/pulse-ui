import { afterEach, beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { type NavigateFn, PulseRouterProvider } from "../context";
import { Link } from "../link";
import { NavigationProgress, NavigationProgressProvider, useNavigationProgress } from "../progress";

/**
 * Integration tests for Link component and NavigationProgress.
 * Tests all prop combinations and progress indicator behavior.
 */

// Mock IntersectionObserver for prefetch tests
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

	simulateIntersection(isIntersecting: boolean) {
		for (const element of this.observedElements) {
			this.callback([{ isIntersecting, target: element } as IntersectionObserverEntry]);
		}
	}

	static reset() {
		MockIntersectionObserver.instances = [];
	}
}

describe("Link integration", () => {
	let originalIntersectionObserver: typeof IntersectionObserver;
	let consoleLogSpy: ReturnType<typeof spyOn>;

	beforeEach(() => {
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

	function createWrapper(navigate: NavigateFn) {
		return function Wrapper({ children }: { children: ReactNode }) {
			return (
				<PulseRouterProvider
					location={{ pathname: "/current", search: "", hash: "", state: null }}
					params={{}}
					navigate={navigate}
				>
					{children}
				</PulseRouterProvider>
			);
		};
	}

	describe("Link with all prop combinations", () => {
		it("renders basic link with href", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			const link = screen.getByRole("link");
			expect(link).toBeTruthy();
			expect(link.getAttribute("href")).toBe("/about");
			expect(link.textContent).toBe("About");
		});

		it("renders link with replace option", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" replace>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			fireEvent.click(screen.getByRole("link"));

			expect(mockNavigate).toHaveBeenCalledWith("/about", {
				replace: true,
				state: undefined,
			});
		});

		it("renders link with state option", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" state={{ from: "/home" }}>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			fireEvent.click(screen.getByRole("link"));

			expect(mockNavigate).toHaveBeenCalledWith("/about", {
				replace: undefined,
				state: { from: "/home" },
			});
		});

		it("renders link with both replace and state", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" replace state={{ modal: true }}>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			fireEvent.click(screen.getByRole("link"));

			expect(mockNavigate).toHaveBeenCalledWith("/about", {
				replace: true,
				state: { modal: true },
			});
		});

		it("renders link with prefetch={true} (default)", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			// Should set up IntersectionObserver
			expect(MockIntersectionObserver.instances.length).toBe(1);

			// Simulate entering viewport
			MockIntersectionObserver.instances[0].simulateIntersection(true);
			expect(consoleLogSpy).toHaveBeenCalledWith("[prefetch] /about");
		});

		it("renders link with prefetch={false}", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" prefetch={false}>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			// Should NOT set up IntersectionObserver
			expect(MockIntersectionObserver.instances.length).toBe(0);

			// Should prefetch on hover instead
			fireEvent.mouseEnter(screen.getByRole("link"));
			expect(consoleLogSpy).toHaveBeenCalledWith("[prefetch] /about");
		});

		it("renders link with custom className", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" className="nav-link active">
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			expect(screen.getByRole("link").getAttribute("class")).toBe("nav-link active");
		});

		it("renders link with custom data attributes", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" data-testid="about" data-section="nav">
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			const link = screen.getByRole("link");
			expect(link.getAttribute("data-testid")).toBe("about");
			expect(link.getAttribute("data-section")).toBe("nav");
		});

		it("renders link with aria attributes", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" aria-label="Navigate to About page" aria-current="page">
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			const link = screen.getByRole("link");
			expect(link.getAttribute("aria-label")).toBe("Navigate to About page");
			expect(link.getAttribute("aria-current")).toBe("page");
		});

		it("renders link with title attribute", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/about" title="Learn more about us">
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			expect(screen.getByRole("link").getAttribute("title")).toBe("Learn more about us");
		});

		it("renders link with target and rel for new window", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<Link href="/docs" target="_blank" rel="noopener noreferrer">
					Docs
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			const link = screen.getByRole("link");
			expect(link.getAttribute("target")).toBe("_blank");
			expect(link.getAttribute("rel")).toBe("noopener noreferrer");
		});

		it("handles custom onClick alongside navigation", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			const customOnClick = mock(() => {});
			render(
				<Link href="/about" onClick={customOnClick}>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			fireEvent.click(screen.getByRole("link"));

			expect(customOnClick).toHaveBeenCalled();
			expect(mockNavigate).toHaveBeenCalled();
		});

		it("handles custom onMouseEnter alongside prefetch", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			const customOnMouseEnter = mock(() => {});
			render(
				<Link href="/about" prefetch={false} onMouseEnter={customOnMouseEnter}>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			fireEvent.mouseEnter(screen.getByRole("link"));

			expect(customOnMouseEnter).toHaveBeenCalled();
			expect(consoleLogSpy).toHaveBeenCalledWith("[prefetch] /about");
		});

		it("respects preventDefault in custom onClick", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			const customOnClick = mock((e: React.MouseEvent) => e.preventDefault());
			render(
				<Link href="/about" onClick={customOnClick}>
					About
				</Link>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			fireEvent.click(screen.getByRole("link"));

			expect(customOnClick).toHaveBeenCalled();
			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("does not intercept modified clicks (metaKey)", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			fireEvent.click(screen.getByRole("link"), { metaKey: true });

			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("does not intercept modified clicks (ctrlKey)", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			fireEvent.click(screen.getByRole("link"), { ctrlKey: true });

			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("does not intercept modified clicks (shiftKey)", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			fireEvent.click(screen.getByRole("link"), { shiftKey: true });

			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("does not intercept modified clicks (altKey)", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="/about">About</Link>, { wrapper: createWrapper(mockNavigate) });

			fireEvent.click(screen.getByRole("link"), { altKey: true });

			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("renders external link without navigation interception", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="https://google.com">Google</Link>, {
				wrapper: createWrapper(mockNavigate),
			});

			const link = screen.getByRole("link");
			expect(link.getAttribute("href")).toBe("https://google.com");

			fireEvent.click(link);

			expect(mockNavigate).not.toHaveBeenCalled();
		});

		it("renders external link without prefetch behavior", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(<Link href="https://google.com">Google</Link>, {
				wrapper: createWrapper(mockNavigate),
			});

			// External links should not trigger prefetch even on hover
			fireEvent.mouseEnter(screen.getByRole("link"));
			expect(consoleLogSpy).not.toHaveBeenCalled();
		});
	});

	describe("multiple Links on same page", () => {
		it("each link has independent prefetch state", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<>
					<Link href="/about">About</Link>
					<Link href="/contact">Contact</Link>
					<Link href="/blog">Blog</Link>
				</>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			// Each link should have its own observer
			expect(MockIntersectionObserver.instances.length).toBe(3);

			// Trigger prefetch on first link only
			MockIntersectionObserver.instances[0].simulateIntersection(true);

			expect(consoleLogSpy).toHaveBeenCalledTimes(1);
			expect(consoleLogSpy).toHaveBeenCalledWith("[prefetch] /about");
		});

		it("clicking one link does not affect others", () => {
			const mockNavigate = mock(() => {}) as unknown as NavigateFn;
			render(
				<>
					<Link href="/about">About</Link>
					<Link href="/contact">Contact</Link>
				</>,
				{ wrapper: createWrapper(mockNavigate) },
			);

			const links = screen.getAllByRole("link");
			fireEvent.click(links[0]);

			expect(mockNavigate).toHaveBeenCalledTimes(1);
			expect(mockNavigate).toHaveBeenCalledWith("/about", {
				replace: undefined,
				state: undefined,
			});
		});
	});
});

describe("NavigationProgress integration", () => {
	beforeEach(() => {
		cleanup();
	});

	afterEach(() => {
		cleanup();
	});

	/**
	 * Test component that exposes progress controls.
	 */
	function TestProgressControls() {
		const progressCtx = useNavigationProgress();
		return (
			<div>
				<button type="button" onClick={() => progressCtx?.startNavigation()}>
					Start
				</button>
				<button type="button" onClick={() => progressCtx?.completeNavigation()}>
					Complete
				</button>
				<span data-testid="status">{progressCtx?.isNavigating ? "navigating" : "idle"}</span>
			</div>
		);
	}

	describe("progress indicator visibility", () => {
		it("renders nothing when not navigating", () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress />
				</NavigationProgressProvider>,
			);

			// Progress bar should not be visible
			expect(container.querySelector('[style*="position: fixed"]')).toBeNull();
		});

		it("shows progress bar when navigation starts", async () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			// Start navigation
			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			// Progress bar should be visible
			await waitFor(() => {
				const progressBar = container.querySelector('[style*="position: fixed"]');
				expect(progressBar).toBeTruthy();
			});
		});

		it("hides progress bar after navigation completes", async () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			// Start navigation
			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			// Verify visible
			await waitFor(() => {
				expect(container.querySelector('[style*="position: fixed"]')).toBeTruthy();
			});

			// Complete navigation
			act(() => {
				fireEvent.click(screen.getByText("Complete"));
			});

			// Wait for hide animation (200ms timeout in component)
			await waitFor(
				() => {
					expect(container.querySelector('[style*="position: fixed"]')).toBeNull();
				},
				{ timeout: 500 },
			);
		});

		it("updates isNavigating state correctly", () => {
			render(
				<NavigationProgressProvider>
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			expect(screen.getByTestId("status").textContent).toBe("idle");

			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			expect(screen.getByTestId("status").textContent).toBe("navigating");

			act(() => {
				fireEvent.click(screen.getByText("Complete"));
			});

			expect(screen.getByTestId("status").textContent).toBe("idle");
		});
	});

	describe("progress indicator customization", () => {
		it("uses default color when not specified", async () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			await waitFor(() => {
				const bar = container.querySelector('[style*="background-color"]');
				expect(bar).toBeTruthy();
				// happy-dom returns hex format, not rgb
				expect((bar as HTMLElement).style.backgroundColor).toBe("#0070f3");
			});
		});

		it("uses custom color when specified", async () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress color="#ff0000" />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			await waitFor(() => {
				const bar = container.querySelector('[style*="background-color"]');
				expect(bar).toBeTruthy();
				// happy-dom returns hex format, not rgb
				expect((bar as HTMLElement).style.backgroundColor).toBe("#ff0000");
			});
		});

		it("uses default height when not specified", async () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			await waitFor(() => {
				const wrapper = container.querySelector('[style*="position: fixed"]');
				expect(wrapper).toBeTruthy();
				expect((wrapper as HTMLElement).style.height).toBe("3px");
			});
		});

		it("uses custom height when specified", async () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress height={5} />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			await waitFor(() => {
				const wrapper = container.querySelector('[style*="position: fixed"]');
				expect(wrapper).toBeTruthy();
				expect((wrapper as HTMLElement).style.height).toBe("5px");
			});
		});
	});

	describe("progress without provider", () => {
		it("renders nothing when used outside NavigationProgressProvider", () => {
			const { container } = render(<NavigationProgress />);

			expect(container.querySelector('[style*="position: fixed"]')).toBeNull();
		});

		it("useNavigationProgress returns null outside provider", () => {
			let result: ReturnType<typeof useNavigationProgress> = null;

			function TestHook() {
				result = useNavigationProgress();
				return null;
			}

			render(<TestHook />);

			expect(result).toBeNull();
		});
	});

	describe("rapid navigation state changes", () => {
		it("handles rapid start/complete cycles", async () => {
			const { container } = render(
				<NavigationProgressProvider>
					<NavigationProgress />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			// Rapidly toggle navigation
			for (let i = 0; i < 5; i++) {
				act(() => {
					fireEvent.click(screen.getByText("Start"));
				});
				act(() => {
					fireEvent.click(screen.getByText("Complete"));
				});
			}

			// Final state should be idle
			expect(screen.getByTestId("status").textContent).toBe("idle");

			// Wait for animations to settle
			await waitFor(
				() => {
					expect(container.querySelector('[style*="position: fixed"]')).toBeNull();
				},
				{ timeout: 500 },
			);
		});

		it("handles start during completion animation", async () => {
			render(
				<NavigationProgressProvider>
					<NavigationProgress />
					<TestProgressControls />
				</NavigationProgressProvider>,
			);

			// Start navigation
			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			expect(screen.getByTestId("status").textContent).toBe("navigating");

			// Complete navigation
			act(() => {
				fireEvent.click(screen.getByText("Complete"));
			});

			// Immediately start new navigation (during animation)
			act(() => {
				fireEvent.click(screen.getByText("Start"));
			});

			// Should be navigating again
			expect(screen.getByTestId("status").textContent).toBe("navigating");
		});
	});
});

describe("Link and NavigationProgress together", () => {
	let originalIntersectionObserver: typeof IntersectionObserver;

	beforeEach(() => {
		cleanup();
		MockIntersectionObserver.reset();
		originalIntersectionObserver = globalThis.IntersectionObserver;
		globalThis.IntersectionObserver =
			MockIntersectionObserver as unknown as typeof IntersectionObserver;
	});

	afterEach(() => {
		globalThis.IntersectionObserver = originalIntersectionObserver;
		cleanup();
	});

	/**
	 * Wrapper combining router provider with progress provider.
	 */
	function createFullWrapper(navigate: NavigateFn) {
		return function FullWrapper({ children }: { children: ReactNode }) {
			return (
				<NavigationProgressProvider>
					<PulseRouterProvider
						location={{ pathname: "/", search: "", hash: "", state: null }}
						params={{}}
						navigate={navigate}
					>
						<NavigationProgress />
						{children}
					</PulseRouterProvider>
				</NavigationProgressProvider>
			);
		};
	}

	it("Link works alongside NavigationProgress", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		render(<Link href="/about">About</Link>, { wrapper: createFullWrapper(mockNavigate) });

		fireEvent.click(screen.getByRole("link"));

		expect(mockNavigate).toHaveBeenCalledWith("/about", {
			replace: undefined,
			state: undefined,
		});
	});

	it("multiple Links work with progress indicator", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		render(
			<nav>
				<Link href="/">Home</Link>
				<Link href="/about">About</Link>
				<Link href="/contact">Contact</Link>
			</nav>,
			{ wrapper: createFullWrapper(mockNavigate) },
		);

		const links = screen.getAllByRole("link");
		expect(links.length).toBe(3);

		// Each link should have its own observer
		expect(MockIntersectionObserver.instances.length).toBe(3);

		// Clicking any link should trigger navigation
		fireEvent.click(links[1]);

		expect(mockNavigate).toHaveBeenCalledWith("/about", {
			replace: undefined,
			state: undefined,
		});
	});
});
