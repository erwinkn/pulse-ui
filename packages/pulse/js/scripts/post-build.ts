#!/usr/bin/env bun
import { rename } from "node:fs/promises";
import { join } from "node:path";

const distDir = join(import.meta.dir, "..", "dist");

await rename(join(distDir, "index.js"), join(distDir, "index.browser.js"));
await rename(join(distDir, "index.js.map"), join(distDir, "index.browser.js.map"));

console.log("✓ Renamed index.js to index.browser.js");
