import { describe, expect, it, mock } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { NavigateFn } from "./context";
import { PulseRouterProvider } from "./context";
import { isExternalUrl, Link } from "./link";

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
});
