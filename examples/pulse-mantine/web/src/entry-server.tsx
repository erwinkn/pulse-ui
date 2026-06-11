import { existsSync, readFileSync } from "node:fs";
import { ColorSchemeScript, MantineProvider } from "@mantine/core";
import { deserialize, preHydrationInputCaptureScript, preloadRoutesForPath, type PulsePrerender } from "pulse-ui-client";
import { renderToStaticMarkup } from "react-dom/server";
import { prerender as reactPrerender } from "react-dom/static";
import { PulseApp } from "../app/pulse/_layout";
import { pulseRouteTree, routeLoaders } from "../app/pulse/routes";

import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";

const inProd = process.env.PULSE_ENV === "prod";

type ManifestEntry = {
	file: string;
	isEntry?: boolean;
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
	for (const file of entryData.css ?? []) {
		tags.push(`<link rel="stylesheet" href="/${file}">`);
	}
	return tags.join("");
}

function renderProdScripts(manifest: Record<string, ManifestEntry>, entry: string) {
	const entryData = manifest[entry];
	if (!entryData) return "";
	// CSS links are emitted in <head> by renderPreloadLinks.
	return `<script type="module" src="/${entryData.file}"></script>`;
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

	// prerender (unlike renderToString) waits for lazy components and Suspense
	// boundaries, so the HTML is complete.
	const { prelude } = await reactPrerender(
		<MantineProvider>
			<PulseApp prerender={prerender} url={url} />
		</MantineProvider>,
	);
	const appHtml = await new Response(prelude).text();
	const colorSchemeScript = renderToStaticMarkup(<ColorSchemeScript />);
	const prerenderJson = jsonForScript(serialized);

	let head = "";
	let scripts = "";
	if (inProd) {
		// The built entry runs from dist/server/; the unbuilt one from src/.
		const manifestCandidates = [
			`${import.meta.dirname}/../client/.vite/manifest.json`,
			`${import.meta.dirname}/../dist/client/.vite/manifest.json`,
		];
		const manifestPath = manifestCandidates.find((path) => existsSync(path));
		if (!manifestPath) {
			throw new Error(
				`[Pulse] Client build manifest not found (looked in: ${manifestCandidates.join(", ")}). Run the client build first.`,
			);
		}
		const manifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as Record<
			string,
			ManifestEntry
		>;
		const entry = Object.keys(manifest).find((key) => manifest[key]!.isEntry);
		if (!entry) {
			throw new Error("[Pulse] No entry chunk in the client build manifest");
		}
		head = renderPreloadLinks(manifest, entry);
		scripts = renderProdScripts(manifest, entry);
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
    <script>${preHydrationInputCaptureScript}</script>
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
