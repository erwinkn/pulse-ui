import * as fs from "node:fs/promises";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import * as Python from "fumadocs-python";
import { rimraf } from "rimraf";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const jsonPath = path.resolve(__dirname, "../generated/pulse.json");

async function generate() {
	const outRoot = "content/docs/api";
	const out = path.join(outRoot, "pulse");
	await rimraf(outRoot);

	const content = JSON.parse((await fs.readFile(jsonPath)).toString());
	const converted = Python.convert(content, {
		baseUrl: "/docs/api",
	});

	await Python.write(converted, {
		outDir: out,
	});

	const meta = {
		title: "API Reference",
		icon: "Code",
		root: true,
		pages: ["pulse"],
	};
	await fs.writeFile(path.join(outRoot, "meta.json"), JSON.stringify(meta, null, 2));
}

void generate();
