import { readFileSync } from "node:fs";
import { ColorSchemeScript, MantineProvider } from "@mantine/core";
import { deserialize, preloadRoutesForPath, type PulsePrerender } from "pulse-ui-client";
import { renderToString } from "react-dom/server";
import { PulseApp } from "../app/pulse/_layout";
import { pulseRouteTree, routeLoaders } from "../app/pulse/routes";

import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";

const inProd = process.env.PULSE_ENV === "prod";

type ManifestEntry = {
	file: string;
	css?: string[];
	imports?: string[];
};

function renderPreloadLinks(manifest: Record<string, ManifestEntry>, entry: string) {
	const seen = new Set<string>();
	const tags: string[] = [];
	const addFile = (file: string) => {
		if (seen.has(file)) return;
		seen.add(file);
		if (file.endsWith(".js")) {
			tags.push(`<link rel="modulepreload" href="/${file}">`);
		}
	};

	const entryData = manifest[entry];
	if (!entryData) return "";
	entryData.imports?.forEach(addFile);
	entryData.css?.forEach((file) => tags.push(`<link rel="stylesheet" href="/${file}">`));
	return tags.join("");
}

function renderProdScripts(manifest: Record<string, ManifestEntry>, entry: string) {
	const entryData = manifest[entry];
	if (!entryData) return "";
	const css = (entryData.css ?? [])
		.map((file) => `<link rel="stylesheet" href="/${file}">`)
		.join("");
	return `${css}<script type="module" src="/${entryData.file}"></script>`;
}

function jsonForScript(value: unknown) {
	return JSON.stringify(value).replace(/</g, "\\u003c");
}

const reactRefreshPreamble = `<script type="module">
import RefreshRuntime from "/@react-refresh";
RefreshRuntime.injectIntoGlobalHook(window);
window.$RefreshReg$ = () => {};
window.$RefreshSig$ = () => (type) => type;
window.__vite_plugin_react_preamble_installed__ = true;
</script>`;
// Load Mantine styles as real stylesheets in dev so SSR HTML doesn't flash
// unstyled before the entry module imports them.
const devCss = [
	'<link rel="stylesheet" href="/node_modules/@mantine/core/styles.css">',
	'<link rel="stylesheet" href="/node_modules/@mantine/dates/styles.css">',
	'<link rel="stylesheet" href="/node_modules/@mantine/charts/styles.css">',
].join("");

export async function render(url: string, serialized: unknown) {
	const prerender = deserialize(serialized) as PulsePrerender;
	const pathname = new URL(url, "http://pulse").pathname;
	await preloadRoutesForPath(pulseRouteTree, routeLoaders, pathname);

	const appHtml = renderToString(
		<MantineProvider>
			<PulseApp prerender={prerender} url={url} />
		</MantineProvider>,
	);
	const colorSchemeScript = renderToString(<ColorSchemeScript />);
	const prerenderJson = jsonForScript(serialized);

	let head = "";
	let scripts = "";
	if (inProd) {
		try {
			const manifestPath = `${import.meta.dirname}/../dist/client/.vite/manifest.json`;
			const manifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as Record<
				string,
				ManifestEntry
			>;
			head = renderPreloadLinks(manifest, "src/entry-client.tsx");
			scripts = renderProdScripts(manifest, "src/entry-client.tsx");
		} catch {
			scripts = '<script type="module" src="/src/entry-client.tsx"></script>';
		}
	} else {
		head = devCss;
		scripts =
			reactRefreshPreamble +
			'<script type="module" src="/@vite/client"></script>' +
			'<script type="module" src="/src/entry-client.tsx"></script>';
	}

	return `<!doctype html>
<html lang="en" data-mantine-color-scheme="light">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    ${colorSchemeScript}
    ${head}
  </head>
  <body>
    <div id="root">${appHtml}</div>
    <script>window.__PULSE_PRERENDER__ = ${prerenderJson};</script>
    ${scripts}
  </body>
</html>`;
}
