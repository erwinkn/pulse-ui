import { describe, expect, it } from "bun:test";
import type { PulseRoute } from "./router";
import { matchRoutes } from "./router";

describe("matchRoutes", () => {
	it("matches static routes", () => {
		const routes: PulseRoute[] = [
			{ id: "/", index: true, file: "routes/index.jsx" },
			{ id: "/about", path: "about", file: "routes/about.jsx" },
		];
		const match = matchRoutes(routes, "/about");
		expect(match?.matches.map((route) => route.id)).toEqual(["/about"]);
	});

	it("matches nested layouts", () => {
		const routes: PulseRoute[] = [
			{
				id: "/<layout>",
				file: "layouts/layout/_layout.tsx",
				children: [{ id: "/dashboard", path: "dashboard", file: "routes/dashboard.jsx" }],
			},
		];
		const match = matchRoutes(routes, "/dashboard");
		expect(match?.matches.map((route) => route.id)).toEqual(["/<layout>", "/dashboard"]);
	});

	it("matches dynamic params", () => {
		const routes: PulseRoute[] = [
			{
				id: "/users",
				path: "users",
				file: "routes/users.jsx",
				children: [{ id: "/users/:id", path: ":id", file: "routes/users/_id.jsx" }],
			},
		];
		const match = matchRoutes(routes, "/users/123");
		expect(match?.params).toEqual({ id: "123" });
	});

	it("matches optional params", () => {
		const routes: PulseRoute[] = [
			{ id: "/docs/:lang", path: "docs/:lang?", file: "routes/docs.jsx" },
		];
		const matchRoot = matchRoutes(routes, "/docs");
		const matchLang = matchRoutes(routes, "/docs/en");
		expect(matchRoot?.params).toEqual({});
		expect(matchLang?.params).toEqual({ lang: "en" });
	});

	it("matches splat segments", () => {
		const routes: PulseRoute[] = [
			{ id: "/files/*", path: "files/*", file: "routes/files.jsx" },
		];
		const match = matchRoutes(routes, "/files/a/b/c");
		expect(match?.catchall).toEqual(["a", "b", "c"]);
	});

	it("matches sibling layouts based on child matches", () => {
		const routes: PulseRoute[] = [
			{
				id: "/<layout-a>",
				file: "layouts/a/_layout.tsx",
				children: [{ id: "/settings", path: "settings", file: "routes/a/settings.jsx" }],
			},
			{
				id: "/<layout-b>",
				file: "layouts/b/_layout.tsx",
				children: [{ id: "/dashboard", path: "dashboard", file: "routes/b/dashboard.jsx" }],
			},
		];
		const match = matchRoutes(routes, "/dashboard");
		expect(match?.matches.map((route) => route.id)).toEqual([
			"/<layout-b>",
			"/dashboard",
		]);
	});

	it("matches nested layouts (layout inside layout)", () => {
		const routes: PulseRoute[] = [
			{
				id: "/<outer>",
				file: "layouts/outer/_layout.tsx",
				children: [
					{
						id: "/<inner>",
						file: "layouts/inner/_layout.tsx",
						children: [{ id: "/settings", path: "settings", file: "routes/settings.jsx" }],
					},
				],
			},
		];
		const match = matchRoutes(routes, "/settings");
		expect(match?.matches.map((route) => route.id)).toEqual([
			"/<outer>",
			"/<inner>",
			"/settings",
		]);
	});

	it("prefers static over dynamic and splat routes", () => {
		const routes: PulseRoute[] = [
			{ id: "/users/:id", path: "users/:id", file: "routes/users/_id.jsx" },
			{ id: "/users/new", path: "users/new", file: "routes/users/new.jsx" },
			{ id: "/users/*", path: "users/*", file: "routes/users/splat.jsx" },
		];
		const match = matchRoutes(routes, "/users/new");
		expect(match?.matches.map((route) => route.id)).toEqual(["/users/new"]);
	});

	it("prefers dynamic over splat routes", () => {
		const routes: PulseRoute[] = [
			{ id: "/users/:id", path: "users/:id", file: "routes/users/_id.jsx" },
			{ id: "/users/*", path: "users/*", file: "routes/users/splat.jsx" },
		];
		const match = matchRoutes(routes, "/users/123");
		expect(match?.matches.map((route) => route.id)).toEqual(["/users/:id"]);
	});
});
