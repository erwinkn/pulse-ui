import { describe, expect, it } from "bun:test";
import { selectBestMatch } from "../match";

/**
 * Integration tests for route matching.
 * Simulates a real-world route tree with nested layouts, mixed segment types.
 */
describe("Route matching integration", () => {
	// Simulate a typical app route structure:
	// - / (home)
	// - /about (static page)
	// - /dashboard (layout)
	//   - /dashboard (index)
	//   - /dashboard/settings (static)
	//   - /dashboard/profile (static)
	// - /users (layout)
	//   - /users (index - list)
	//   - /users/new (static - create form)
	//   - /users/:id (dynamic - user detail)
	//   - /users/:id/edit (dynamic + static)
	//   - /users/:id/posts (dynamic + static)
	//   - /users/:id/posts/:postId (nested dynamic)
	// - /blog (layout)
	//   - /blog (index)
	//   - /blog/:slug (dynamic)
	//   - /blog/:slug? (optional - same as index if no slug)
	// - /files/* (catch-all)
	// - /docs/* (catch-all with prefix)
	// - /api/:version/* (dynamic + catch-all)
	// - /* (fallback catch-all)

	// Note: Routes with catch-all at root (/*) will match "/" before a static "/"
	// because longer patterns are considered more specific. In practice, apps should
	// either not use /* or accept that it catches the root path too.
	const routes = [
		{ pattern: "/", name: "home" },
		{ pattern: "/about", name: "about" },
		{ pattern: "/dashboard", name: "dashboard-index" },
		{ pattern: "/dashboard/settings", name: "dashboard-settings" },
		{ pattern: "/dashboard/profile", name: "dashboard-profile" },
		{ pattern: "/users", name: "users-list" },
		{ pattern: "/users/new", name: "users-new" },
		{ pattern: "/users/:id", name: "user-detail" },
		{ pattern: "/users/:id/edit", name: "user-edit" },
		{ pattern: "/users/:id/posts", name: "user-posts" },
		{ pattern: "/users/:id/posts/:postId", name: "user-post-detail" },
		{ pattern: "/blog", name: "blog-index" },
		{ pattern: "/blog/:slug", name: "blog-post" },
		{ pattern: "/files/*", name: "files-browser" },
		{ pattern: "/docs/*", name: "docs-page" },
		{ pattern: "/api/:version/*", name: "api-proxy" },
	];

	describe("static routes", () => {
		it("matches home route", () => {
			const result = selectBestMatch(routes, "/");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("home");
			expect(result!.params).toEqual({});
		});

		it("matches about page", () => {
			const result = selectBestMatch(routes, "/about");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("about");
		});

		it("matches dashboard index", () => {
			const result = selectBestMatch(routes, "/dashboard");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("dashboard-index");
		});

		it("matches dashboard settings", () => {
			const result = selectBestMatch(routes, "/dashboard/settings");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("dashboard-settings");
		});

		it("matches dashboard profile", () => {
			const result = selectBestMatch(routes, "/dashboard/profile");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("dashboard-profile");
		});
	});

	describe("static vs dynamic precedence", () => {
		it("prefers /users/new over /users/:id", () => {
			const result = selectBestMatch(routes, "/users/new");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("users-new");
			// Should NOT be user-detail with id="new"
		});

		it("matches /users/:id for numeric id", () => {
			const result = selectBestMatch(routes, "/users/123");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("user-detail");
			expect(result!.params).toEqual({ id: "123" });
		});

		it("matches /users/:id for uuid-like id", () => {
			const result = selectBestMatch(routes, "/users/a1b2c3d4-e5f6-7890-abcd-ef1234567890");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("user-detail");
			expect(result!.params.id).toBe("a1b2c3d4-e5f6-7890-abcd-ef1234567890");
		});
	});

	describe("nested dynamic routes", () => {
		it("matches /users/:id/edit", () => {
			const result = selectBestMatch(routes, "/users/456/edit");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("user-edit");
			expect(result!.params).toEqual({ id: "456" });
		});

		it("matches /users/:id/posts", () => {
			const result = selectBestMatch(routes, "/users/789/posts");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("user-posts");
			expect(result!.params).toEqual({ id: "789" });
		});

		it("matches /users/:id/posts/:postId", () => {
			const result = selectBestMatch(routes, "/users/1/posts/42");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("user-post-detail");
			expect(result!.params).toEqual({ id: "1", postId: "42" });
		});
	});

	describe("blog routes with dynamic slug", () => {
		it("matches blog index", () => {
			const result = selectBestMatch(routes, "/blog");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("blog-index");
		});

		it("matches blog post by slug", () => {
			const result = selectBestMatch(routes, "/blog/hello-world");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("blog-post");
			expect(result!.params).toEqual({ slug: "hello-world" });
		});

		it("matches blog post with complex slug", () => {
			const result = selectBestMatch(routes, "/blog/2024-01-09-my-awesome-post");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("blog-post");
			expect(result!.params.slug).toBe("2024-01-09-my-awesome-post");
		});
	});

	describe("catch-all routes", () => {
		it("matches /files/* for nested paths", () => {
			const result = selectBestMatch(routes, "/files/documents/reports/2024/q1.pdf");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("files-browser");
			expect(result!.params).toEqual({ "*": ["documents", "reports", "2024", "q1.pdf"] });
		});

		it("matches /files/* for single file", () => {
			const result = selectBestMatch(routes, "/files/readme.md");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("files-browser");
			expect(result!.params).toEqual({ "*": ["readme.md"] });
		});

		it("matches /files/* with no path (empty array)", () => {
			const result = selectBestMatch(routes, "/files");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("files-browser");
			expect(result!.params).toEqual({ "*": [] });
		});

		it("matches /docs/* for documentation paths", () => {
			const result = selectBestMatch(routes, "/docs/getting-started/installation");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("docs-page");
			expect(result!.params).toEqual({ "*": ["getting-started", "installation"] });
		});

		it("matches /api/:version/* for API proxy", () => {
			const result = selectBestMatch(routes, "/api/v2/users/123/profile");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("api-proxy");
			expect(result!.params).toEqual({ version: "v2", "*": ["users", "123", "profile"] });
		});
	});

	describe("no match for unknown routes (without /* fallback)", () => {
		it("returns null for unknown routes when no catch-all exists", () => {
			const result = selectBestMatch(routes, "/unknown/path");
			expect(result).toBeNull();
		});

		it("returns null for deeply unknown routes", () => {
			const result = selectBestMatch(routes, "/a/b/c/d/e/f/g");
			expect(result).toBeNull();
		});
	});

	describe("fallback with /* route", () => {
		const routesWithFallback = [
			{ pattern: "/about", name: "about" },
			{ pattern: "/users/:id", name: "user-detail" },
			{ pattern: "/*", name: "not-found" },
		];

		it("falls back to /* for unknown routes", () => {
			const result = selectBestMatch(routesWithFallback, "/unknown/path");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("not-found");
			expect(result!.params).toEqual({ "*": ["unknown", "path"] });
		});

		it("/* matches root path with empty array", () => {
			// When /* is present, it matches "/" too (longer pattern wins over zero-segment patterns)
			const result = selectBestMatch(routesWithFallback, "/");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("not-found");
			expect(result!.params).toEqual({ "*": [] });
		});
	});

	describe("specificity with mixed segment types", () => {
		// Routes with overlapping patterns to test specificity
		// Note: Longer patterns (even with optional segments) are considered more specific
		// because they're designed to handle more specific cases
		const overlappingRoutes = [
			{ pattern: "/products", name: "products-list" },
			{ pattern: "/products/featured", name: "products-featured" },
			{ pattern: "/products/sale", name: "products-sale" },
			{ pattern: "/products/:category", name: "products-category" },
			{ pattern: "/products/:category/:id", name: "product-detail" },
			{ pattern: "/products/*", name: "products-catchall" },
		];

		it("static 'featured' wins over dynamic :category", () => {
			const result = selectBestMatch(overlappingRoutes, "/products/featured");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("products-featured");
		});

		it("static 'sale' wins over dynamic :category", () => {
			const result = selectBestMatch(overlappingRoutes, "/products/sale");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("products-sale");
		});

		it("dynamic :category matches unknown category", () => {
			const result = selectBestMatch(overlappingRoutes, "/products/electronics");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("products-category");
			expect(result!.params).toEqual({ category: "electronics" });
		});

		it("required :id wins over catch-all", () => {
			const result = selectBestMatch(overlappingRoutes, "/products/books/978");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("product-detail");
			expect(result!.params).toEqual({ category: "books", id: "978" });
		});

		it("catch-all matches deeper paths", () => {
			const result = selectBestMatch(overlappingRoutes, "/products/books/978/reviews/5");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("products-catchall");
			expect(result!.params).toEqual({ "*": ["books", "978", "reviews", "5"] });
		});
	});

	describe("optional segment specificity", () => {
		// When both required and optional patterns exist at same depth,
		// required wins because dynamic (2) > optional (1)
		const optionalRoutes = [
			{ pattern: "/items/:id", name: "item-required" },
			{ pattern: "/items/:id?", name: "item-optional" },
		];

		it("required dynamic wins over optional for same segment", () => {
			const result = selectBestMatch(optionalRoutes, "/items/123");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("item-required");
		});

		it("optional matches when path is shorter (no id)", () => {
			const result = selectBestMatch(optionalRoutes, "/items");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("item-optional");
			expect(result!.params).toEqual({ id: undefined });
		});
	});

	describe("edge cases", () => {
		it("handles trailing slashes", () => {
			const result = selectBestMatch(routes, "/users/123/");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("user-detail");
			expect(result!.params).toEqual({ id: "123" });
		});

		it("handles URL-encoded segments", () => {
			// Note: URL decoding is typically done before matching
			const result = selectBestMatch(routes, "/blog/hello%20world");
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe("blog-post");
			expect(result!.params.slug).toBe("hello%20world");
		});

		it("handles empty pattern array gracefully", () => {
			const result = selectBestMatch([], "/any/path");
			expect(result).toBeNull();
		});
	});

	describe("real-world scenario: e-commerce app", () => {
		// Note: In this example we don't use /* fallback because it would
		// catch "/" before the static home route. Real apps can handle 404s
		// by checking if selectBestMatch returns null.
		const ecommerceRoutes = [
			{ pattern: "/", name: "home" },
			{ pattern: "/search", name: "search" },
			{ pattern: "/cart", name: "cart" },
			{ pattern: "/checkout", name: "checkout" },
			{ pattern: "/checkout/success", name: "checkout-success" },
			{ pattern: "/account", name: "account" },
			{ pattern: "/account/orders", name: "orders" },
			{ pattern: "/account/orders/:orderId", name: "order-detail" },
			{ pattern: "/account/settings", name: "settings" },
			{ pattern: "/shop", name: "shop-all" },
			{ pattern: "/shop/:category", name: "shop-category" },
			{ pattern: "/shop/:category/:subcategory", name: "shop-subcategory" },
			{ pattern: "/product/:slug", name: "product-page" },
		];

		const testCases = [
			{ path: "/", expected: "home" },
			{ path: "/search", expected: "search" },
			{ path: "/cart", expected: "cart" },
			{ path: "/checkout", expected: "checkout" },
			{ path: "/checkout/success", expected: "checkout-success" },
			{ path: "/account", expected: "account" },
			{ path: "/account/orders", expected: "orders" },
			{ path: "/account/orders/ORD-12345", expected: "order-detail" },
			{ path: "/account/settings", expected: "settings" },
			{ path: "/shop", expected: "shop-all" },
			{ path: "/shop/clothing", expected: "shop-category" },
			{ path: "/shop/clothing/shirts", expected: "shop-subcategory" },
			{ path: "/product/blue-widget-xl", expected: "product-page" },
		];

		it.each(testCases)("matches $path to $expected", ({ path, expected }) => {
			const result = selectBestMatch(ecommerceRoutes, path);
			expect(result).not.toBeNull();
			expect(result!.route.name).toBe(expected);
		});

		it("returns null for non-existent routes (404 handling)", () => {
			const result = selectBestMatch(ecommerceRoutes, "/non-existent-page");
			expect(result).toBeNull();
		});
	});
});
