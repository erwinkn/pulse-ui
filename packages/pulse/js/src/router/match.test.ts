import { describe, expect, it } from "bun:test";
import { matchRoutes, type PulseRoute } from "./match";

const tree: PulseRoute[] = [
	{ id: "/", index: true },
	{ id: "/about", path: "about" },
	{
		id: "/users",
		path: "users",
		children: [
			{ id: "/users/", index: true },
			{ id: "/users/new", path: "new" },
			{ id: "/users/:id", path: ":id" },
			{ id: "/users/:id/edit", path: ":id/edit" },
		],
	},
	{
		id: "<layout>",
		children: [
			{ id: "/dashboard", path: "dashboard" },
			{
				id: "<layout>/settings",
				path: "settings",
				children: [{ id: "/settings/", index: true }],
			},
		],
	},
	{ id: "/docs/:section?", path: "docs/:section?" },
	{ id: "/files/*", path: "files/*" },
];

describe("matchRoutes", () => {
	it("matches the index route", () => {
		const match = matchRoutes(tree, "/");
		expect(match?.matches.map((r) => r.id)).toEqual(["/"]);
	});

	it("matches static routes", () => {
		const match = matchRoutes(tree, "/about");
		expect(match?.matches.map((r) => r.id)).toEqual(["/about"]);
	});

	it("normalizes trailing slashes", () => {
		const match = matchRoutes(tree, "/about/");
		expect(match?.matches.map((r) => r.id)).toEqual(["/about"]);
	});

	it("matches nested index routes", () => {
		const match = matchRoutes(tree, "/users");
		expect(match?.matches.map((r) => r.id)).toEqual(["/users", "/users/"]);
	});

	it("prefers static segments over dynamic ones", () => {
		const match = matchRoutes(tree, "/users/new");
		expect(match?.matches.map((r) => r.id)).toEqual(["/users", "/users/new"]);
	});

	it("extracts dynamic params", () => {
		const match = matchRoutes(tree, "/users/42");
		expect(match?.matches.map((r) => r.id)).toEqual(["/users", "/users/:id"]);
		expect(match?.params).toEqual({ id: "42" });
	});

	it("matches multi-segment dynamic routes", () => {
		const match = matchRoutes(tree, "/users/42/edit");
		expect(match?.matches.map((r) => r.id)).toEqual(["/users", "/users/:id/edit"]);
		expect(match?.params).toEqual({ id: "42" });
	});

	it("matches through pathless layouts", () => {
		const match = matchRoutes(tree, "/dashboard");
		expect(match?.matches.map((r) => r.id)).toEqual(["<layout>", "/dashboard"]);
	});

	it("matches nested layouts with index children", () => {
		const match = matchRoutes(tree, "/settings");
		expect(match?.matches.map((r) => r.id)).toEqual([
			"<layout>",
			"<layout>/settings",
			"/settings/",
		]);
	});

	it("matches optional params when present", () => {
		const match = matchRoutes(tree, "/docs/intro");
		expect(match?.matches.map((r) => r.id)).toEqual(["/docs/:section?"]);
		expect(match?.params).toEqual({ section: "intro" });
	});

	it("matches optional params when absent", () => {
		const match = matchRoutes(tree, "/docs");
		expect(match?.matches.map((r) => r.id)).toEqual(["/docs/:section?"]);
		expect(match?.params).toEqual({});
	});

	it("captures catch-all segments", () => {
		const match = matchRoutes(tree, "/files/a/b/c");
		expect(match?.matches.map((r) => r.id)).toEqual(["/files/*"]);
		expect(match?.catchall).toEqual(["a", "b", "c"]);
	});

	it("matches catch-all with no segments", () => {
		const match = matchRoutes(tree, "/files");
		expect(match?.matches.map((r) => r.id)).toEqual(["/files/*"]);
		expect(match?.catchall).toEqual([]);
	});

	it("returns null for unknown paths", () => {
		expect(matchRoutes(tree, "/nope")).toBeNull();
		expect(matchRoutes(tree, "/users/42/nope")).toBeNull();
	});
});
