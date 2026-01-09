import { describe, expect, it } from "bun:test";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import {
	type Location,
	type NavigateFn,
	type Params,
	PulseRouterProvider,
	useLocation,
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
