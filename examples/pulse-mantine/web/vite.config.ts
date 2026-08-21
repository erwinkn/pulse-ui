import { reactRouter } from "@react-router/dev/vite";
import { pulse } from "pulse-ui-client/vite";
import { defineConfig } from "vite";
import devtoolsJson from "vite-plugin-devtools-json";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
	plugins: [reactRouter(), tsconfigPaths(), devtoolsJson(), pulse()],
});
