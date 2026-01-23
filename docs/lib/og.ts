import { readFileSync } from "node:fs";
import path from "node:path";

export const ogPalette = {
	pulseMarine: { h: 208, s: 85, l: 55 },
	darkest: "#050505",
	homeBackground: "#0b0f14",
	homePanel: "#0a0f18",
};

export function getPulseMarineColors() {
	const { h, s, l } = ogPalette.pulseMarine;
	return {
		color: `hsl(${h}, ${s}%, ${l}%)`,
		glow: `hsla(${h}, ${s}%, ${l}%, 0.35)`,
	};
}

export function withSvgCircleBackground(svg: string, fill: string) {
	const marker = "<circle";
	if (!svg.includes(marker)) return svg;
	return svg.replace(
		marker,
		`<circle cx="16" cy="16" r="14" fill="${fill}"/>\n  <circle`,
	);
}

export function getFaviconDataUrl(fill = ogPalette.darkest) {
	const faviconSvg = readFileSync(path.join(process.cwd(), "public", "favicon.svg"), "utf8");
	const svgWithBg = withSvgCircleBackground(faviconSvg, fill);
	return `data:image/svg+xml;utf8,${encodeURIComponent(svgWithBg)}`;
}
