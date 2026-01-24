import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import devtoolsJson from "vite-plugin-devtools-json";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig(({ isSsrBuild }) => ({
	plugins: [react(), tailwindcss(), tsconfigPaths(), devtoolsJson()],
	resolve: {
		alias: {
			pulse: resolve(__dirname, "app", "pulse"),
		},
		conditions: ["@pulse/source", "module", "browser", "development|production"],
	},
	ssr: {
		noExternal: [/^pulse-/],
		resolve: {
			conditions: ["@pulse/source", "module", "node", "development|production"],
		},
	},
	build: {
		manifest: !isSsrBuild,
		ssrManifest: !isSsrBuild,
		outDir: isSsrBuild ? "dist/server" : "dist/client",
	},
}));
