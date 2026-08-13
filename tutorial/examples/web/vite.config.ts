import { reactRouter } from "@react-router/dev/vite";
import { pulseVitePlugin } from "pulse-ui-client/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import devtoolsJson from "vite-plugin-devtools-json";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
	plugins: [
		tailwindcss(),
		reactRouter(),
		tsconfigPaths(),
		devtoolsJson(),
		pulseVitePlugin(),
	],
});
