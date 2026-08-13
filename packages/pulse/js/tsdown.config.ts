import { defineConfig } from "tsdown";

export default defineConfig({
	entry: ["src/index.ts", "src/vite.ts"],
	platform: "neutral",
	target: "esnext",
	dts: true,
	external: [/^node:/],
	minify: true,
	sourcemap: true,
	exports: { devExports: "@pulse/source" },
});
