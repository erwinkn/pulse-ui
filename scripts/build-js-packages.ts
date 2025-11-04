#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { $ } from "bun";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packagesRoot = join(__dirname, "..", "packages");

const BUILD_ORDER = ["pulse/js", "pulse-mantine/js"];

async function readPackageJson(packagePath: string) {
	const data = await readFile(join(packagesRoot, packagePath, "package.json"), "utf8");
	return JSON.parse(data);
}

async function buildPackage(packagePath: string) {
	const pkg = await readPackageJson(packagePath);
	const name = pkg.name || packagePath;

	if (!pkg.scripts || !pkg.scripts.build) {
		console.log(`⏭️  Skipping ${name} (no build script)`);
		return;
	}

	console.log(`\n▶ Building ${name}`);

	const packageDir = join(packagesRoot, packagePath);

	await $`cd ${packageDir} && bun run build`;

	console.log(`  ✅ ${name} built successfully`);
}

async function main() {
	console.log("🏗️  Building JS packages in order...\n");

	for (const packagePath of BUILD_ORDER) {
		await buildPackage(packagePath);
	}

	console.log("\n✅ Finished building all JS packages");
}

main().catch((err) => {
	console.error("\n❌ Build failed:", err.message);
	process.exitCode = 1;
});
