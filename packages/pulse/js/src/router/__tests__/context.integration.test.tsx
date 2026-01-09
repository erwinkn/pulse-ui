import { describe, expect, it, mock } from "bun:test";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import {
	type Location,
	type NavigateFn,
	type Params,
	PulseRouterProvider,
	useLocation,
	useNavigate,
	useParams,
} from "../context";

/**
 * Integration tests for nested PulseRouterProviders.
 * Simulates layout > page component structure where each level
 * has its own router context for scoped params.
 */

describe("nested PulseRouterProviders", () => {
	// Shared location - should be consistent across all levels
	const sharedLocation: Location = {
		pathname: "/org/acme/users/123",
		search: "?view=grid",
		hash: "#section",
		state: { from: "/home" },
	};

	// Layout-level params (outer provider)
	const layoutParams: Params = { org: "acme" };

	// Page-level params (inner provider)
	const pageParams: Params = { userId: "123" };

	/**
	 * Helper to create nested wrapper simulating layout > page structure.
	 * Both providers share the same location (URL is global),
	 * but have different params (scoped to their route pattern).
	 */
	function createNestedWrapper(outerNavigate: NavigateFn, innerNavigate: NavigateFn) {
		return function NestedWrapper({ children }: { children: ReactNode }) {
			return (
				<PulseRouterProvider
					location={sharedLocation}
					params={layoutParams}
					navigate={outerNavigate}
				>
					<PulseRouterProvider
						location={sharedLocation}
						params={pageParams}
						navigate={innerNavigate}
					>
						{children}
					</PulseRouterProvider>
				</PulseRouterProvider>
			);
		};
	}

	describe("useParams - scoped to nearest provider", () => {
		it("returns inner provider params, not outer", () => {
			const outerNavigate = mock(() => {}) as unknown as NavigateFn;
			const innerNavigate = mock(() => {}) as unknown as NavigateFn;

			const { result } = renderHook(() => useParams(), {
				wrapper: createNestedWrapper(outerNavigate, innerNavigate),
			});

			// Should only see inner (page) params
			expect(result.current).toEqual(pageParams);
			expect(result.current.userId).toBe("123");
			// Outer params should NOT be accessible
			expect(result.current.org).toBeUndefined();
		});

		it("does not merge params from parent providers", () => {
			const outerNavigate = mock(() => {}) as unknown as NavigateFn;
			const innerNavigate = mock(() => {}) as unknown as NavigateFn;

			const { result } = renderHook(() => useParams(), {
				wrapper: createNestedWrapper(outerNavigate, innerNavigate),
			});

			// Verify params are exactly the inner params, no extras
			expect(Object.keys(result.current)).toEqual(["userId"]);
		});
	});

	describe("useLocation - consistent across levels", () => {
		it("returns same location from inner provider", () => {
			const outerNavigate = mock(() => {}) as unknown as NavigateFn;
			const innerNavigate = mock(() => {}) as unknown as NavigateFn;

			const { result } = renderHook(() => useLocation(), {
				wrapper: createNestedWrapper(outerNavigate, innerNavigate),
			});

			// Location should be the shared location
			expect(result.current).toEqual(sharedLocation);
			expect(result.current.pathname).toBe("/org/acme/users/123");
			expect(result.current.search).toBe("?view=grid");
			expect(result.current.hash).toBe("#section");
			expect(result.current.state).toEqual({ from: "/home" });
		});

		it("returns location even when inner provider has different location", () => {
			// Edge case: different locations at different levels (unusual but valid)
			const outerLocation: Location = {
				pathname: "/layout",
				search: "",
				hash: "",
				state: null,
			};
			const innerLocation: Location = {
				pathname: "/layout/page",
				search: "?tab=1",
				hash: "",
				state: null,
			};

			function DifferentLocationsWrapper({ children }: { children: ReactNode }) {
				return (
					<PulseRouterProvider location={outerLocation} params={{}} navigate={() => {}}>
						<PulseRouterProvider location={innerLocation} params={{}} navigate={() => {}}>
							{children}
						</PulseRouterProvider>
					</PulseRouterProvider>
				);
			}

			const { result } = renderHook(() => useLocation(), {
				wrapper: DifferentLocationsWrapper,
			});

			// Should return inner location (nearest provider)
			expect(result.current).toEqual(innerLocation);
		});
	});

	describe("useNavigate - works from any level", () => {
		it("uses inner provider navigate function", () => {
			const outerNavigate = mock(() => {}) as unknown as NavigateFn;
			const innerNavigate = mock(() => {}) as unknown as NavigateFn;

			const { result } = renderHook(() => useNavigate(), {
				wrapper: createNestedWrapper(outerNavigate, innerNavigate),
			});

			result.current("/new-path");

			// Should call inner navigate, not outer
			expect(innerNavigate).toHaveBeenCalledWith("/new-path", undefined);
			expect(outerNavigate).not.toHaveBeenCalled();
		});

		it("resolves relative paths based on shared location", () => {
			const outerNavigate = mock(() => {}) as unknown as NavigateFn;
			const innerNavigate = mock(() => {}) as unknown as NavigateFn;

			const { result } = renderHook(() => useNavigate(), {
				wrapper: createNestedWrapper(outerNavigate, innerNavigate),
			});

			// Current: /org/acme/users/123, navigate to ../settings
			result.current("../settings");

			// Should resolve to /org/acme/users/settings
			expect(innerNavigate).toHaveBeenCalledWith("/org/acme/users/settings", undefined);
		});

		it("handles history navigation from nested context", () => {
			const outerNavigate = mock(() => {}) as unknown as NavigateFn;
			const innerNavigate = mock(() => {}) as unknown as NavigateFn;

			const { result } = renderHook(() => useNavigate(), {
				wrapper: createNestedWrapper(outerNavigate, innerNavigate),
			});

			result.current(-1);

			// History nav passes through to inner navigate
			expect(innerNavigate).toHaveBeenCalledWith(-1);
			expect(outerNavigate).not.toHaveBeenCalled();
		});

		it("passes options through when navigating", () => {
			const outerNavigate = mock(() => {}) as unknown as NavigateFn;
			const innerNavigate = mock(() => {}) as unknown as NavigateFn;

			const { result } = renderHook(() => useNavigate(), {
				wrapper: createNestedWrapper(outerNavigate, innerNavigate),
			});

			result.current("/new-path", { replace: true, state: { foo: "bar" } });

			expect(innerNavigate).toHaveBeenCalledWith("/new-path", {
				replace: true,
				state: { foo: "bar" },
			});
		});
	});

	describe("deeply nested providers (3+ levels)", () => {
		it("returns params from deepest provider only", () => {
			const rootParams: Params = { tenant: "corp" };
			const middleParams: Params = { org: "acme" };
			const leafParams: Params = { userId: "123" };

			function DeeplyNestedWrapper({ children }: { children: ReactNode }) {
				return (
					<PulseRouterProvider location={sharedLocation} params={rootParams} navigate={() => {}}>
						<PulseRouterProvider
							location={sharedLocation}
							params={middleParams}
							navigate={() => {}}
						>
							<PulseRouterProvider
								location={sharedLocation}
								params={leafParams}
								navigate={() => {}}
							>
								{children}
							</PulseRouterProvider>
						</PulseRouterProvider>
					</PulseRouterProvider>
				);
			}

			const { result } = renderHook(() => useParams(), {
				wrapper: DeeplyNestedWrapper,
			});

			// Only deepest (leaf) params
			expect(result.current).toEqual(leafParams);
			expect(result.current.userId).toBe("123");
			expect(result.current.org).toBeUndefined();
			expect(result.current.tenant).toBeUndefined();
		});

		it("uses navigate from deepest provider", () => {
			const rootNavigate = mock(() => {}) as unknown as NavigateFn;
			const middleNavigate = mock(() => {}) as unknown as NavigateFn;
			const leafNavigate = mock(() => {}) as unknown as NavigateFn;

			function DeeplyNestedWrapper({ children }: { children: ReactNode }) {
				return (
					<PulseRouterProvider location={sharedLocation} params={{}} navigate={rootNavigate}>
						<PulseRouterProvider location={sharedLocation} params={{}} navigate={middleNavigate}>
							<PulseRouterProvider location={sharedLocation} params={{}} navigate={leafNavigate}>
								{children}
							</PulseRouterProvider>
						</PulseRouterProvider>
					</PulseRouterProvider>
				);
			}

			const { result } = renderHook(() => useNavigate(), {
				wrapper: DeeplyNestedWrapper,
			});

			result.current("/path");

			expect(leafNavigate).toHaveBeenCalled();
			expect(middleNavigate).not.toHaveBeenCalled();
			expect(rootNavigate).not.toHaveBeenCalled();
		});
	});

	describe("mixed param types in nested contexts", () => {
		it("handles catch-all params in inner context", () => {
			const outerParams: Params = { section: "docs" };
			const innerParams: Params = { "*": ["api", "users", "create"] };

			function MixedParamsWrapper({ children }: { children: ReactNode }) {
				return (
					<PulseRouterProvider location={sharedLocation} params={outerParams} navigate={() => {}}>
						<PulseRouterProvider location={sharedLocation} params={innerParams} navigate={() => {}}>
							{children}
						</PulseRouterProvider>
					</PulseRouterProvider>
				);
			}

			const { result } = renderHook(() => useParams(), {
				wrapper: MixedParamsWrapper,
			});

			expect(result.current["*"]).toEqual(["api", "users", "create"]);
			expect(result.current.section).toBeUndefined();
		});

		it("handles optional params (undefined) in inner context", () => {
			const outerParams: Params = { org: "acme" };
			const innerParams: Params = { userId: "123", tab: undefined };

			function OptionalParamsWrapper({ children }: { children: ReactNode }) {
				return (
					<PulseRouterProvider location={sharedLocation} params={outerParams} navigate={() => {}}>
						<PulseRouterProvider location={sharedLocation} params={innerParams} navigate={() => {}}>
							{children}
						</PulseRouterProvider>
					</PulseRouterProvider>
				);
			}

			const { result } = renderHook(() => useParams(), {
				wrapper: OptionalParamsWrapper,
			});

			expect(result.current.userId).toBe("123");
			expect(result.current.tab).toBeUndefined();
			// Important: undefined is present in the object
			expect("tab" in result.current).toBe(true);
		});
	});
});
