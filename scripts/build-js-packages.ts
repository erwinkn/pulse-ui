#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { $ } from "bun";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packagesRoot = join(__dirname, "..", "packages");

const BUILD_ORDER = [
  "pulse-ui-client",
  "pulse-mantine/js",
];

const prodDefine = {
  "process.env.NODE_ENV": '"production"',
  __DEV__: "false",
};

const devDefine = {
  "process.env.NODE_ENV": '"development"',
  __DEV__: "true",
};

async function readPackageJson(packagePath: string) {
  const data = await readFile(join(packagesRoot, packagePath, "package.json"), "utf8");
  return JSON.parse(data);
}

function getExternals(pkg: any): string[] {
  return [
    ...new Set([
      ...Object.keys(pkg.devDependencies ?? {}).filter(
        (dep) => !dep.startsWith("@types/") && dep !== "typescript" && dep !== "esbuild"
      ),
      ...Object.keys(pkg.peerDependencies ?? {}),
    ]),
  ];
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
  const entry = "./src/index.ts";
  const outdir = "dist";
  const external = getExternals(pkg);

  await $`cd ${packageDir} && rm -rf ${outdir}`.quiet();

  console.log(`  📦 Building browser bundle...`);
  const browserResult = await Bun.build({
    entrypoints: [join(packageDir, entry)],
    outdir: join(packageDir, outdir),
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
  if (!browserResult.success) throw new Error(`Browser build failed for ${name}`);

  console.log(`  🔧 Building browser dev bundle...`);
  const browserDevResult = await Bun.build({
    entrypoints: [join(packageDir, entry)],
    outdir: join(packageDir, outdir),
    naming: { entry: "index.development.js" },
    target: "browser",
    format: "esm",
    minify: false,
    sourcemap: "inline",
    external,
    define: devDefine,
  });
  if (!browserDevResult.success) throw new Error(`Browser dev build failed for ${name}`);

  console.log(`  🟢 Building node bundle...`);
  const nodeResult = await Bun.build({
    entrypoints: [join(packageDir, entry)],
    outdir: join(packageDir, outdir),
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
  if (!nodeResult.success) throw new Error(`Node build failed for ${name}`);

  console.log(`  🥟 Building bun bundle...`);
  const bunResult = await Bun.build({
    entrypoints: [join(packageDir, entry)],
    outdir: join(packageDir, outdir),
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
  if (!bunResult.success) throw new Error(`Bun build failed for ${name}`);

  console.log(`  📝 Building types...`);
  await $`cd ${packageDir} && bun run build:types`.quiet();

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
