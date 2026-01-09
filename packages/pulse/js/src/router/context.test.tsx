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
} from "./context";

function createWrapper(location: Location, params: Params = {}, navigate: NavigateFn = () => {}) {
	return function Wrapper({ children }: { children: ReactNode }) {
		return (
			<PulseRouterProvider location={location} params={params} navigate={navigate}>
				{children}
			</PulseRouterProvider>
		);
	};
}

describe("useLocation", () => {
	it("returns location from context", () => {
		const location: Location = {
			pathname: "/users/123",
			search: "?tab=posts",
			hash: "#comments",
			state: { from: "/home" },
		};

		const { result } = renderHook(() => useLocation(), {
			wrapper: createWrapper(location),
		});

		expect(result.current).toEqual(location);
	});

	it("returns all location fields", () => {
		const location: Location = {
			pathname: "/",
			search: "",
			hash: "",
			state: null,
		};

		const { result } = renderHook(() => useLocation(), {
			wrapper: createWrapper(location),
		});

		expect(result.current.pathname).toBe("/");
		expect(result.current.search).toBe("");
		expect(result.current.hash).toBe("");
		expect(result.current.state).toBe(null);
	});

	it("throws when used outside PulseRouterProvider", () => {
		expect(() => {
			renderHook(() => useLocation());
		}).toThrow("useLocation/useParams/useNavigate must be used within a PulseRouterProvider");
	});
});

describe("useParams", () => {
	const defaultLocation: Location = {
		pathname: "/users/123",
		search: "",
		hash: "",
		state: null,
	};

	it("returns params from context", () => {
		const params: Params = { id: "123", name: "john" };

		const { result } = renderHook(() => useParams(), {
			wrapper: createWrapper(defaultLocation, params),
		});

		expect(result.current).toEqual(params);
	});

	it("returns empty object when no params", () => {
		const { result } = renderHook(() => useParams(), {
			wrapper: createWrapper(defaultLocation, {}),
		});

		expect(result.current).toEqual({});
	});

	it("handles optional params (undefined values)", () => {
		const params: Params = { id: "123", tab: undefined };

		const { result } = renderHook(() => useParams(), {
			wrapper: createWrapper(defaultLocation, params),
		});

		expect(result.current.id).toBe("123");
		expect(result.current.tab).toBeUndefined();
	});

	it("handles catch-all params (string[] values)", () => {
		const params: Params = { "*": ["docs", "api", "users"] };

		const { result } = renderHook(() => useParams(), {
			wrapper: createWrapper(defaultLocation, params),
		});

		expect(result.current["*"]).toEqual(["docs", "api", "users"]);
	});

	it("returns scoped params from nearest provider", () => {
		// Outer provider has parent params
		const outerParams: Params = { org: "acme" };
		// Inner provider has scoped params
		const innerParams: Params = { userId: "456" };

		function OuterWrapper({ children }: { children: ReactNode }) {
			return (
				<PulseRouterProvider location={defaultLocation} params={outerParams} navigate={() => {}}>
					<PulseRouterProvider location={defaultLocation} params={innerParams} navigate={() => {}}>
						{children}
					</PulseRouterProvider>
				</PulseRouterProvider>
			);
		}

		const { result } = renderHook(() => useParams(), {
			wrapper: OuterWrapper,
		});

		// Should see inner (scoped) params, not outer
		expect(result.current).toEqual(innerParams);
		expect(result.current.userId).toBe("456");
		expect(result.current.org).toBeUndefined();
	});

	it("throws when used outside PulseRouterProvider", () => {
		expect(() => {
			renderHook(() => useParams());
		}).toThrow("useLocation/useParams/useNavigate must be used within a PulseRouterProvider");
	});
});

describe("useNavigate", () => {
	const defaultLocation: Location = {
		pathname: "/users/123",
		search: "",
		hash: "",
		state: null,
	};

	it("returns a navigate function", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		expect(typeof result.current).toBe("function");
	});

	it("navigates to absolute path", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current("/posts");

		expect(mockNavigate).toHaveBeenCalledWith("/posts", undefined);
	});

	it("navigates with replace option", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current("/posts", { replace: true });

		expect(mockNavigate).toHaveBeenCalledWith("/posts", { replace: true });
	});

	it("navigates with state option", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		const state = { from: "/home" };

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current("/posts", { state });

		expect(mockNavigate).toHaveBeenCalledWith("/posts", { state });
	});

	it("navigates with replace and state options", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		const state = { from: "/home" };

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current("/posts", { replace: true, state });

		expect(mockNavigate).toHaveBeenCalledWith("/posts", { replace: true, state });
	});

	it("resolves relative path with ../", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		// Current: /users/123
		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current("../posts");

		// /users/123 -> ../posts -> /users/posts
		expect(mockNavigate).toHaveBeenCalledWith("/users/posts", undefined);
	});

	it("resolves relative path with multiple ../", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		const location: Location = {
			pathname: "/org/acme/users/123",
			search: "",
			hash: "",
			state: null,
		};

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(location, {}, mockNavigate),
		});

		result.current("../../settings");

		// /org/acme/users/123 -> ../../settings -> /org/acme/settings
		expect(mockNavigate).toHaveBeenCalledWith("/org/acme/settings", undefined);
	});

	it("resolves relative path with ./ (current directory)", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		// Current: /users/123
		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current("./posts");

		// /users/123 -> ./posts -> /users/123/posts
		expect(mockNavigate).toHaveBeenCalledWith("/users/123/posts", undefined);
	});

	it("resolves relative path without prefix (same as ./)", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		// Current: /users/123
		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current("posts");

		// /users/123 -> posts -> /users/123/posts
		expect(mockNavigate).toHaveBeenCalledWith("/users/123/posts", undefined);
	});

	it("handles history navigation with negative number", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current(-1);

		expect(mockNavigate).toHaveBeenCalledWith(-1);
	});

	it("handles history navigation with positive number", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(defaultLocation, {}, mockNavigate),
		});

		result.current(2);

		expect(mockNavigate).toHaveBeenCalledWith(2);
	});

	it("throws when used outside PulseRouterProvider", () => {
		expect(() => {
			renderHook(() => useNavigate());
		}).toThrow("useLocation/useParams/useNavigate must be used within a PulseRouterProvider");
	});

	it("resolves to root when going up from root", () => {
		const mockNavigate = mock(() => {}) as unknown as NavigateFn;
		const location: Location = {
			pathname: "/users",
			search: "",
			hash: "",
			state: null,
		};

		const { result } = renderHook(() => useNavigate(), {
			wrapper: createWrapper(location, {}, mockNavigate),
		});

		result.current("../../..");

		// Going above root should still result in /
		expect(mockNavigate).toHaveBeenCalledWith("/", undefined);
	});
});
