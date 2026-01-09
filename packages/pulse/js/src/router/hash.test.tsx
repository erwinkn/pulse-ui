import { afterEach, beforeEach, describe, expect, it, mock } from "bun:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { type NavigateFn, PulseRouterProvider } from "./context";
import { scrollToHash, useHashScroll } from "./hash";

describe("scrollToHash", () => {
	beforeEach(() => {
		// Reset document body
		document.body.innerHTML = "";
	});

	it("scrolls to element with matching id", () => {
		// Create target element
		const element = document.createElement("div");
		element.id = "section";
		const scrollIntoViewMock = mock(() => {});
		element.scrollIntoView = scrollIntoViewMock;
		document.body.appendChild(element);

		scrollToHash("section");

		expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: "smooth" });
	});

	it("scrolls to element when hash includes # prefix", () => {
		const element = document.createElement("div");
		element.id = "section";
		const scrollIntoViewMock = mock(() => {});
		element.scrollIntoView = scrollIntoViewMock;
		document.body.appendChild(element);

		scrollToHash("#section");

		expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: "smooth" });
	});

	it("does nothing when element does not exist", () => {
		// No element created - should not throw
		expect(() => scrollToHash("nonexistent")).not.toThrow();
	});

	it("does nothing for empty hash", () => {
		expect(() => scrollToHash("")).not.toThrow();
		expect(() => scrollToHash("#")).not.toThrow();
	});
});

describe("useHashScroll", () => {
	const mockNavigate = mock(() => {}) as unknown as NavigateFn;

	function createWrapper(hash: string) {
		return function Wrapper({ children }: { children: ReactNode }) {
			return (
				<PulseRouterProvider
					location={{ pathname: "/page", search: "", hash, state: null }}
					params={{}}
					navigate={mockNavigate}
				>
					{children}
				</PulseRouterProvider>
			);
		};
	}

	beforeEach(() => {
		cleanup();
		document.body.innerHTML = "";
	});

	afterEach(() => {
		cleanup();
	});

	it("scrolls to element on initial render when hash exists", async () => {
		const element = document.createElement("div");
		element.id = "section";
		const scrollIntoViewMock = mock(() => {});
		element.scrollIntoView = scrollIntoViewMock;
		document.body.appendChild(element);

		renderHook(() => useHashScroll(), { wrapper: createWrapper("#section") });

		// Wait for requestAnimationFrame
		await new Promise((resolve) => requestAnimationFrame(resolve));

		expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: "smooth" });
	});

	it("does nothing on initial render when no hash", async () => {
		const element = document.createElement("div");
		element.id = "section";
		const scrollIntoViewMock = mock(() => {});
		element.scrollIntoView = scrollIntoViewMock;
		document.body.appendChild(element);

		renderHook(() => useHashScroll(), { wrapper: createWrapper("") });

		// Wait for requestAnimationFrame
		await new Promise((resolve) => requestAnimationFrame(resolve));

		expect(scrollIntoViewMock).not.toHaveBeenCalled();
	});

	it("scrolls when hash changes via provider", async () => {
		const element = document.createElement("div");
		element.id = "newSection";
		const scrollIntoViewMock = mock(() => {});
		element.scrollIntoView = scrollIntoViewMock;
		document.body.appendChild(element);

		// Use a stateful wrapper to test hash changes
		let setHashExternal: ((hash: string) => void) | null = null;
		function StatefulWrapper({ children }: { children: ReactNode }) {
			const [hash, setHash] = useState("");
			setHashExternal = setHash;
			return (
				<PulseRouterProvider
					location={{ pathname: "/page", search: "", hash, state: null }}
					params={{}}
					navigate={mockNavigate}
				>
					{children}
				</PulseRouterProvider>
			);
		}

		renderHook(() => useHashScroll(), { wrapper: StatefulWrapper });

		// Wait for initial render
		await new Promise((resolve) => requestAnimationFrame(resolve));
		expect(scrollIntoViewMock).not.toHaveBeenCalled();

		// Change hash via state update wrapped in act
		await act(async () => {
			setHashExternal!("#newSection");
			// Wait for requestAnimationFrame within act
			await new Promise((resolve) => requestAnimationFrame(resolve));
		});

		expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: "smooth" });
	});

	it("does not scroll again if hash is unchanged", async () => {
		const element = document.createElement("div");
		element.id = "section";
		const scrollIntoViewMock = mock(() => {});
		element.scrollIntoView = scrollIntoViewMock;
		document.body.appendChild(element);

		const { rerender } = renderHook(() => useHashScroll(), {
			wrapper: createWrapper("#section"),
		});

		// Wait for initial render
		await new Promise((resolve) => requestAnimationFrame(resolve));
		expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);

		// Re-render with same wrapper (hash unchanged)
		rerender();

		// Wait for requestAnimationFrame
		await new Promise((resolve) => requestAnimationFrame(resolve));

		// Should not be called again
		expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
	});

	it("does not throw when element does not exist", async () => {
		// No element in DOM

		expect(() => {
			renderHook(() => useHashScroll(), { wrapper: createWrapper("#nonexistent") });
		}).not.toThrow();
	});
});
