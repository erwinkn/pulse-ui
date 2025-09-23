
import { $ } from "bun";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const entry = "./src/index.ts";
const outdir = "dist";
const define = {
  "process.env.NODE_ENV": '"production"',
  __DEV__: "false",
};

const pkgPath = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "package.json"
);
const pkgJson = await Bun.file(pkgPath).json();
const external = [
  ...new Set([
    ...Object.keys(pkgJson.dependencies ?? {}),
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
    minify: true,
    sourcemap: "external",
    external,
    define,
  });
  if (!result.success) throw new Error("Browser build failed");
}

async function buildNode() {
  const result = await Bun.build({
    entrypoints: [entry],
    outdir,
    naming: { entry: "index.node.js" },
    target: "node",
    format: "esm",
    minify: true,
    sourcemap: "inline",
    external,
    define,
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
    minify: true,
    sourcemap: "inline",
    external,
    define,
  });
  if (!result.success) throw new Error("Bun build failed");
}

async function main() {
  await clean();
  // build sequentially for clearer logs
  await buildBrowser();
  await buildNode();
  await buildBun();
}

await main();
