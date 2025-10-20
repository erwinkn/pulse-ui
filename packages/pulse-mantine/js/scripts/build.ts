import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { $ } from "bun";

const entry = "./src/index.ts";
const outdir = "dist";
const prodDefine = {
	"process.env.NODE_ENV": '"production"',
	__DEV__: "false",
};
const devDefine = {
	"process.env.NODE_ENV": '"development"',
	__DEV__: "true",
};

const pkgPath = join(dirname(fileURLToPath(import.meta.url)), "..", "package.json");
const pkgJson = await Bun.file(pkgPath).json();
const external = [
	...new Set([
		...Object.keys(pkgJson.devDependencies ?? {}).filter(
			(dep) =>
				dep !== "@types/bun" &&
				dep !== "@types/node" &&
				dep !== "@types/react" &&
				dep !== "@types/react-dom" &&
				dep !== "typescript",
		),
		...Object.keys(pkgJson.peerDependencies ?? {}),
	]),
];

async function clean() {
	await $`rm -rf ${outdir}`;
}

async function buildBrowser() {
	const result = await Bun.build({
		entrypoints: [entry],
		outdir,
		target: "browser",
		format: "esm",
		minify: {
			whitespace: true,
			identifiers: true,
			syntax: true,
		},
		sourcemap: "external",
		external,
		define: prodDefine,
	});
	if (!result.success) throw new Error("Browser build failed");
}

async function buildBrowserDev() {
	const result = await Bun.build({
		entrypoints: [entry],
		outdir,
		naming: { entry: "index.development.js" },
		target: "browser",
		format: "esm",
		minify: false,
		sourcemap: "inline",
		external,
		define: devDefine,
	});
	if (!result.success) throw new Error("Browser dev build failed");
}

async function buildNode() {
	const result = await Bun.build({
		entrypoints: [entry],
		outdir,
		naming: { entry: "index.node.js" },
		target: "node",
		format: "esm",
		minify: {
			whitespace: true,
			identifiers: true,
			syntax: true,
		},
		sourcemap: "inline",
		external,
		define: prodDefine,
	});
	if (!result.success) throw new Error("Node build failed");
}

async function buildBun() {
	const result = await Bun.build({
		entrypoints: [entry],
		outdir,
		naming: { entry: "index.bun.js" },
		target: "bun",
		format: "esm",
		minify: {
			whitespace: true,
			identifiers: true,
			syntax: true,
		},
		sourcemap: "inline",
		external,
		define: prodDefine,
	});
	if (!result.success) throw new Error("Bun build failed");
}

async function main() {
	await clean();
	await buildBrowser();
	await buildBrowserDev();
	await buildNode();
	await buildBun();
}

await main();
