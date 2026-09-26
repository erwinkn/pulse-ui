import { beforeEach, describe, expect, it, vi } from "bun:test";
import { act, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { Link } from "./link";
import type { PulseRoute } from "./match";
import type { RouteLoaderMap } from "./modules";
import {
	Outlet,
	PulseRouterProvider,
	PulseRoutes,
	resolveHref,
	useNavigate,
	useNavigationError,
	useRouteInfo,
} from "./router";

function HomePage() {
	return <div data-testid="page">home</div>;
}

function LayoutShell() {
	return (
		<div data-testid="layout">
			<Outlet />
		</div>
	);
}

function UserPage() {
	const info = useRouteInfo();
	return <div data-testid="page">user:{info.pathParams.id}</div>;
}

const routes: PulseRoute[] = [
	{ id: "/", index: true },
	{
		id: "<layout>",
		children: [{ id: "/users/:id", path: "users/:id" }],
	},
];

const routeLoaders: RouteLoaderMap = {
	"/": async () => ({ default: HomePage }),
	"<layout>": async () => ({ default: LayoutShell }),
	"/users/:id": async () => ({ default: UserPage }),
};

function NavButton({ to, label }: { to: string; label: string }) {
	const navigate = useNavigate();
	return (
		<button type="button" data-testid={`nav-${label}`} onClick={() => navigate(to)}>
			{label}
		</button>
	);
}

function ErrorProbe() {
	const error = useNavigationError();
	return <div data-testid="nav-error">{error ? error.error.message : "none"}</div>;
}

describe("resolveHref", () => {
	it("keeps absolute and external URLs", () => {
		expect(resolveHref("/a/b", "/c")).toBe("/a/b");
		expect(resolveHref("https://example.com/x", "/c")).toBe("https://example.com/x");
		expect(resolveHref("mailto:a@b.c", "/c")).toBe("mailto:a@b.c");
	});

	it("treats protocol-relative URLs as external", () => {
		expect(resolveHref("//evil.com/x", "/c")).toBe("//evil.com/x");
	});

	it("resolves relative paths", () => {
		expect(resolveHref("child", "/parent")).toBe("/parent/child");
		expect(resolveHref("../sibling", "/parent/child")).toBe("/parent/sibling");
		expect(resolveHref("./here", "/parent")).toBe("/parent/here");
	});
});

describe("PulseRouterProvider", () => {
	beforeEach(() => {
		window.history.replaceState(null, "", "/");
	});

	it("renders the initial route once modules load", async () => {
		render(
			<PulseRouterProvider routes={routes} routeLoaders={routeLoaders} initialUrl="http://t/">
				<PulseRoutes />
			</PulseRouterProvider>,
		);
		await waitFor(() => {
			expect(screen.getByTestId("page")).toHaveTextContent("home");
		});
	});

	it("navigates between routes and renders nested layouts", async () => {
		const onNavigate = vi.fn(async () => {});
		render(
			<PulseRouterProvider
				routes={routes}
				routeLoaders={routeLoaders}
				initialUrl="http://t/"
				onNavigate={onNavigate}
			>
				<NavButton to="/users/7" label="user" />
				<PulseRoutes />
			</PulseRouterProvider>,
		);
		await waitFor(() => {
			expect(screen.getByTestId("page")).toHaveTextContent("home");
		});

		await act(async () => {
			screen.getByTestId("nav-user").click();
		});

		await waitFor(() => {
			expect(screen.getByTestId("layout")).toBeInTheDocument();
			expect(screen.getByTestId("page")).toHaveTextContent("user:7");
		});
		expect(onNavigate).toHaveBeenCalledTimes(1);
		expect(window.location.pathname).toBe("/users/7");
	});

	it("drops navigations superseded by a newer one", async () => {
		let resolveFirst: (() => void) | null = null;
		const onNavigate = vi.fn((target: { location: { pathname: string } }) => {
			if (target.location.pathname === "/users/1") {
				return new Promise<void>((resolve) => {
					resolveFirst = resolve;
				});
			}
			return Promise.resolve();
		});

		render(
			<PulseRouterProvider
				routes={routes}
				routeLoaders={routeLoaders}
				initialUrl="http://t/"
				onNavigate={onNavigate}
			>
				<NavButton to="/users/1" label="one" />
				<NavButton to="/users/2" label="two" />
				<PulseRoutes />
			</PulseRouterProvider>,
		);
		await waitFor(() => {
			expect(screen.getByTestId("page")).toHaveTextContent("home");
		});

		await act(async () => {
			screen.getByTestId("nav-one").click();
		});
		await act(async () => {
			screen.getByTestId("nav-two").click();
		});
		await waitFor(() => {
			expect(screen.getByTestId("page")).toHaveTextContent("user:2");
		});

		// The slow first navigation resolves afterwards and must not win.
		await act(async () => {
			resolveFirst?.();
			await Promise.resolve();
		});
		expect(screen.getByTestId("page")).toHaveTextContent("user:2");
		expect(window.location.pathname).toBe("/users/2");
	});

	it("surfaces navigation errors without committing", async () => {
		const onNavigate = vi.fn(async () => {
			throw new Error("prerender failed");
		});
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

		render(
			<PulseRouterProvider
				routes={routes}
				routeLoaders={routeLoaders}
				initialUrl="http://t/"
				onNavigate={onNavigate}
			>
				<NavButton to="/users/7" label="user" />
				<ErrorProbe />
				<PulseRoutes />
			</PulseRouterProvider>,
		);
		await waitFor(() => {
			expect(screen.getByTestId("page")).toHaveTextContent("home");
		});

		await act(async () => {
			screen.getByTestId("nav-user").click();
		});

		await waitFor(() => {
			expect(screen.getByTestId("nav-error")).toHaveTextContent("prerender failed");
		});
		// Still on the home page, URL unchanged.
		expect(screen.getByTestId("page")).toHaveTextContent("home");
		expect(window.location.pathname).toBe("/");
		consoleError.mockRestore();
	});

	it("Link clicks navigate client-side and prefetch on hover", async () => {
		const onNavigate = vi.fn(async () => {});
		const onPrefetch = vi.fn();
		render(
			<PulseRouterProvider
				routes={routes}
				routeLoaders={routeLoaders}
				initialUrl="http://t/"
				onNavigate={onNavigate}
				onPrefetch={onPrefetch}
			>
				<Link to="/users/9" data-testid="link">
					user 9
				</Link>
				<PulseRoutes />
			</PulseRouterProvider>,
		);
		await waitFor(() => {
			expect(screen.getByTestId("page")).toHaveTextContent("home");
		});

		const link = screen.getByTestId("link");
		await act(async () => {
			link.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
		});
		await waitFor(() => {
			expect(onPrefetch).toHaveBeenCalledTimes(1);
		});
		expect(onPrefetch.mock.calls[0]![0].location.pathname).toBe("/users/9");

		await act(async () => {
			link.click();
		});
		await waitFor(() => {
			expect(screen.getByTestId("page")).toHaveTextContent("user:9");
		});
	});
});
