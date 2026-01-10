import { defineConfig } from "vite";

export default defineConfig({
	server: {
		middlewareMode: false,
		port: 5173,
		hmr: {
			port: 5173,
		},
	},
});
