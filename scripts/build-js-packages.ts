#!/usr/bin/env node
import { readdir } from "node:fs/promises";
import { readFile } from "node:fs/promises";
import { access } from "node:fs/promises";
import { constants } from "node:fs";
import { spawn } from "node:child_process";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packagesRoot = join(__dirname, "..", "packages");
const ignoreDirs = new Set(["node_modules", "dist", "build", ".git"]);

async function hasPackageJson(dir: string) {
  try {
    await access(join(dir, "package.json"), constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

async function findPackageDirs(dir: string) {
  const entries = await readdir(dir, { withFileTypes: true });
  const packages: string[] = [];
  const hasPkg = await hasPackageJson(dir);
  if (hasPkg) {
    packages.push(dir);
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    if (ignoreDirs.has(entry.name) || entry.name.startsWith(".")) continue;
    const nested = await findPackageDirs(join(dir, entry.name));
    packages.push(...nested);
  }
  return packages;
}

async function readPackageJson(dir: string) {
  const data = await readFile(join(dir, "package.json"), "utf8");
  return JSON.parse(data);
}

function runBuild(dir: string) {
  return new Promise<void>((resolve, reject) => {
    const proc = spawn("bun", ["run", "build"], {
      cwd: dir,
      stdio: "inherit",
    });
    proc.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`Build failed for ${dir} with exit code ${code}`));
      }
    });
    proc.on("error", reject);
  });
}

async function main() {
  const packageDirs = await findPackageDirs(packagesRoot);
  if (packageDirs.length === 0) {
    console.log("No packages found under packages/");
    return;
  }

  for (const dir of packageDirs) {
    const pkg = await readPackageJson(dir);
    if (!pkg.scripts || !pkg.scripts.build) {
      continue;
    }
    const name = pkg.name || relative(packagesRoot, dir);
    console.log(`\n▶ Building ${name} (${relative(packagesRoot, dir)})`);
    await runBuild(dir);
  }

  console.log("\n✅ Finished building JS packages");
}

main().catch((err) => {
  console.error(err.message);
  process.exitCode = 1;
});
