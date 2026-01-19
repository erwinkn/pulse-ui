import * as fs from "node:fs/promises";
import * as path from "node:path";
import * as Python from "fumadocs-python";
import { rimraf } from "rimraf";

const jsonPath = "./generated/pulse.json";

async function generate() {
	// Output to api/pulse to match the generated hrefs (/docs/api/pulse/...)
	const out = "content/docs/api/pulse";

	// Clean previous output
	await rimraf("content/docs/api");

	const content = JSON.parse((await fs.readFile(jsonPath)).toString());
	const converted = Python.convert(content, {
		baseUrl: "/docs/api",
	});

	// fumadocs-python strips the first path segment, so we need to manually
	// write to preserve the pulse/ directory structure
	await fs.mkdir(out, { recursive: true });

	for (const file of converted) {
		// file.path is like "pulse/channel/index.mdx"
		// We want to write to "content/docs/api/pulse/channel/index.mdx"
		const filePath = path.join("content/docs/api", file.path);
		await fs.mkdir(path.dirname(filePath), { recursive: true });

		const frontmatter =
			Object.keys(file.frontmatter).length > 0
				? `---\n${Object.entries(file.frontmatter)
						.map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
						.join("\n")}\n---\n\n`
				: "";

		await fs.writeFile(filePath, frontmatter + file.content);
	}

	// Generate meta.json for navigation
	await generateMeta("content/docs/api", content);

	console.log(`Generated ${converted.length} files`);
}

async function generateMeta(outDir, content) {
	// Create root api meta.json
	const apiMeta = {
		title: "API",
		icon: "Code",
		root: true,
		pages: ["pulse"],
	};
	await fs.writeFile(path.join(outDir, "meta.json"), JSON.stringify(apiMeta, null, 2));

	// Create pulse meta.json
	const pulseMeta = {
		title: "pulse",
		icon: "Zap",
		defaultOpen: true,
		pages: [
			"index",
			"---Core---",
			"app",
			"component",
			"state",
			"reactive",
			"hooks",
			"---Data---",
			"queries",
			"form",
			"channel",
			"---Utilities---",
			"routing",
			"middleware",
			"context",
			"cookies",
			"serializer",
			"helpers",
			"---Advanced---",
			"dom",
			"components",
			"decorators",
			"reactive_extensions",
			"plugin",
			"render_session",
			"user_session",
			"---Internal---",
			"transpiler",
			"codegen",
			"cli",
			"js",
			"messages",
			"renderer",
			"request",
			"proxy",
			"code_analysis",
			"env",
			"types",
			"version",
			"react_component",
			"_examples",
		],
	};
	await fs.writeFile(path.join(outDir, "pulse", "meta.json"), JSON.stringify(pulseMeta, null, 2));

	// Create meta.json for each submodule
	for (const [name, mod] of Object.entries(content.modules)) {
		const modDir = path.join(outDir, "pulse", name);
		try {
			await fs.access(modDir);
			const subMeta = {
				title: name,
				pages: ["index", ...Object.keys(mod.classes || {}), ...Object.keys(mod.modules || {})],
			};
			await fs.writeFile(path.join(modDir, "meta.json"), JSON.stringify(subMeta, null, 2));
		} catch {
			// Directory doesn't exist, skip
		}
	}
}

void generate();
