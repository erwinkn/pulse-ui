"use client";

import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { buildStops, type CurveType, clamp, formatNumber, hexToRgb, type Stop } from "./logo-utils";

const display = Space_Grotesk({
	subsets: ["latin"],
	weight: ["400", "600", "700"],
	variable: "--font-display",
});

const mono = IBM_Plex_Mono({
	subsets: ["latin"],
	weight: ["400", "500", "600"],
	variable: "--font-mono",
});

type Settings = {
	color: string;
	peakOpacity: number;
	flatPercent: number;
	fadeEndPercent: number;
	curve: CurveType;
	curvePower: number;
	stopCount: number;
	x1: number;
	y1: number;
	x2: number;
	y2: number;
	radius: number;
};

const PRESETS: Array<{
	name: string;
	settings: Partial<Settings>;
	notes: string;
}> = [
	{
		name: "Favicon v2",
		settings: {
			flatPercent: 20,
			fadeEndPercent: 78,
			curve: "ease-in-out",
			curvePower: 2,
			stopCount: 10,
			x1: 75,
			y1: 0,
			x2: 5,
			y2: 95,
		},
		notes: "Current favicon",
	},
	{
		name: "Base 20",
		settings: { flatPercent: 20, fadeEndPercent: 70, curve: "ease-out", curvePower: 2 },
		notes: "Longer full core",
	},
	{
		name: "Soft tail",
		settings: { flatPercent: 15, fadeEndPercent: 82, curve: "ease-in-out", curvePower: 2 },
		notes: "Longer fade",
	},
	{
		name: "Sharp drop",
		settings: { flatPercent: 15, fadeEndPercent: 62, curve: "ease-in", curvePower: 2.4 },
		notes: "Faster falloff",
	},
];

const SURFACES = [
	{ name: "Quartz", value: "quartz" },
	{ name: "Midnight", value: "midnight" },
	{ name: "Ink", value: "ink" },
];

const DEFAULT_SETTINGS: Settings = {
	color: "#1f4bff",
	peakOpacity: 1,
	flatPercent: 20,
	fadeEndPercent: 78,
	curve: "ease-in-out",
	curvePower: 2,
	stopCount: 10,
	x1: 75,
	y1: 0,
	x2: 5,
	y2: 95,
	radius: 14,
};

export function LogoPlayground() {
	const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
	const [surface, setSurface] = useState("midnight");
	const [copied, setCopied] = useState<string | null>(null);
	const gradientIdBase = useId().replace(/:/g, "");
	const originalRefs = useRef<{
		icons: Map<HTMLLinkElement, string>;
		logo: HTMLImageElement | null;
		logoSrc: string | null;
		observer: MutationObserver | null;
	} | null>(null);
	const dataUrlRef = useRef("");

	const normalized = useMemo(() => {
		const flatPercent = clamp(settings.flatPercent, 0, 80);
		const fadeEndPercent = clamp(settings.fadeEndPercent, flatPercent + 1, 100);
		const peakOpacity = clamp(settings.peakOpacity, 0, 1);
		const stopCount = clamp(Math.round(settings.stopCount), 4, 12);
		const curvePower = clamp(settings.curvePower, 0.35, 4);
		const radius = clamp(settings.radius, 10, 15);
		return {
			...settings,
			flatPercent,
			fadeEndPercent,
			peakOpacity,
			stopCount,
			curvePower,
			radius,
		};
	}, [settings]);

	const stops = useMemo<Stop[]>(() => {
		return buildStops({
			flatPercent: normalized.flatPercent,
			fadeEndPercent: normalized.fadeEndPercent,
			peakOpacity: normalized.peakOpacity,
			stopCount: normalized.stopCount,
			curve: normalized.curve,
			curvePower: normalized.curvePower,
		});
	}, [normalized]);

	const gradientStops = useMemo(
		() =>
			stops.map((stop) => ({
				offset: clamp(stop.offset, 0, 100),
				opacity: clamp(stop.opacity, 0, 1),
			})),
		[stops],
	);

	const exportData = useMemo(
		() => ({
			settings: normalized,
			stops: gradientStops,
			viewBox: 32,
			center: 16,
		}),
		[gradientStops, normalized],
	);

	const settingsJson = useMemo(() => JSON.stringify(exportData, null, 2), [exportData]);

	const svgMarkup = useMemo(() => {
		const stopMarkup = gradientStops
			.map(
				(stop) =>
					`<stop offset=\"${formatNumber(stop.offset)}%\" stop-color=\"${normalized.color}\" stop-opacity=\"${formatNumber(stop.opacity)}\"/>`,
			)
			.join("\n    ");
		return `<svg viewBox=\"0 0 32 32\" xmlns=\"http://www.w3.org/2000/svg\">\n  <defs>\n    <linearGradient id=\"pulse-grad\" x1=\"${formatNumber(normalized.x1)}%\" y1=\"${formatNumber(normalized.y1)}%\" x2=\"${formatNumber(normalized.x2)}%\" y2=\"${formatNumber(normalized.y2)}%\">\n    ${stopMarkup}\n    </linearGradient>\n  </defs>\n  <circle cx=\"16\" cy=\"16\" r=\"${formatNumber(normalized.radius, 2)}\" fill=\"url(#pulse-grad)\"/>\n</svg>`;
	}, [gradientStops, normalized]);

	const gradientCss = useMemo(() => {
		const { r, g, b } = hexToRgb(normalized.color);
		const angle = Math.round(
			(Math.atan2(normalized.y2 - normalized.y1, normalized.x2 - normalized.x1) * 180) / Math.PI,
		);
		const stopMarkup = gradientStops
			.map((stop) => {
				const alpha = formatNumber(stop.opacity, 3);
				return `rgba(${r}, ${g}, ${b}, ${alpha}) ${formatNumber(stop.offset)}%`;
			})
			.join(", ");
		return `linear-gradient(${angle}deg, ${stopMarkup})`;
	}, [gradientStops, normalized]);

	const onCopy = async (text: string, label: string) => {
		try {
			if (navigator.clipboard?.writeText) {
				await navigator.clipboard.writeText(text);
			} else {
				const textarea = document.createElement("textarea");
				textarea.value = text;
				textarea.style.position = "fixed";
				textarea.style.opacity = "0";
				document.body.appendChild(textarea);
				textarea.select();
				document.execCommand("copy");
				document.body.removeChild(textarea);
			}
			setCopied(label);
			window.setTimeout(() => setCopied(null), 1400);
		} catch {
			setCopied("fail");
			window.setTimeout(() => setCopied(null), 1400);
		}
	};

	useEffect(() => {
		const dataUrl = `data:image/svg+xml;utf8,${encodeURIComponent(svgMarkup)}`;
		dataUrlRef.current = dataUrl;
		if (!originalRefs.current) {
			originalRefs.current = {
				icons: new Map(),
				logo: null,
				logoSrc: null,
				observer: null,
			};
		}
		const refs = originalRefs.current;
		if (!refs) return;
		const apply = () => {
			const icons = Array.from(
				document.querySelectorAll<HTMLLinkElement>(
					'link[rel~="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]',
				),
			);
			for (const icon of icons) {
				if (!refs.icons.has(icon)) {
					refs.icons.set(icon, icon.href);
				}
				if (icon.href !== dataUrlRef.current) {
					icon.href = dataUrlRef.current;
				}
			}
			const logo = document.querySelector<HTMLImageElement>('img[data-pulse-logo="true"]');
			if (logo) {
				if (!refs.logo) {
					refs.logo = logo;
					refs.logoSrc = logo.src;
				}
				if (logo.src !== dataUrlRef.current) {
					logo.src = dataUrlRef.current;
				}
			}
		};
		apply();
		if (!refs.observer) {
			refs.observer = new MutationObserver(() => {
				apply();
			});
			refs.observer.observe(document.head, {
				subtree: true,
				childList: true,
				attributes: true,
				attributeFilter: ["href", "rel"],
			});
		}
	}, [svgMarkup]);

	useEffect(() => {
		return () => {
			const refs = originalRefs.current;
			if (!refs) return;
			for (const [icon, href] of refs.icons.entries()) {
				icon.href = href;
			}
			if (refs.logo && refs.logoSrc) {
				refs.logo.src = refs.logoSrc;
			}
			refs.observer?.disconnect();
		};
	}, []);

	return (
		<div
			className={`${display.variable} ${mono.variable} playground-shell min-h-screen`}
			style={{ fontFamily: "var(--font-display)" }}
		>
			<div className="pointer-events-none absolute inset-0">
				<div className="playground-glow" />
				<div className="playground-grid" />
			</div>
			<div className="relative mx-auto flex w-full max-w-6xl flex-col gap-10 px-6 pb-20 pt-12">
				<header className="flex flex-col gap-6">
					<div className="flex flex-wrap items-center justify-between gap-4">
						<div>
							<p className="playground-kicker">Logo Lab</p>
							<h1 className="text-3xl font-semibold md:text-4xl">Pulse fade playground</h1>
						</div>
						<div className="flex flex-wrap gap-2">
							{PRESETS.map((preset) => (
								<button
									key={preset.name}
									type="button"
									className="playground-pill"
									onClick={() =>
										setSettings((prev) => ({
											...prev,
											...preset.settings,
										}))
									}
								>
									<span>{preset.name}</span>
									<span className="playground-caption">{preset.notes}</span>
								</button>
							))}
						</div>
					</div>
					<p className="playground-muted max-w-2xl text-sm md:text-base">
						Tune the gradient curve, flat core, stops, and transparency. Export settings for favicon
						work or future logo variants.
					</p>
				</header>

				<div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
					<section className="playground-card">
						<div className="flex flex-wrap items-center justify-between gap-3">
							<h2 className="text-lg font-semibold">Controls</h2>
							<div className="flex gap-2">
								<button
									type="button"
									className="playground-button"
									onClick={() => setSettings(DEFAULT_SETTINGS)}
								>
									Reset
								</button>
								<button
									type="button"
									className="playground-button"
									onClick={() => onCopy(settingsJson, "settings")}
								>
									{copied === "settings" ? "Copied" : "Copy settings"}
								</button>
							</div>
						</div>

						<div className="mt-6 grid gap-6">
							<div className="grid gap-3">
								<p className="playground-section">Color + opacity</p>
								<div className="grid gap-3 sm:grid-cols-2">
									<label className="playground-field">
										<span>Color</span>
										<input
											type="color"
											value={normalized.color}
											onChange={(event) =>
												setSettings((prev) => ({
													...prev,
													color: event.currentTarget.value,
												}))
											}
										/>
									</label>
									<RangeControl
										label="Peak opacity"
										value={normalized.peakOpacity}
										min={0}
										max={1}
										step={0.02}
										precision={2}
										onChange={(value) => setSettings((prev) => ({ ...prev, peakOpacity: value }))}
									/>
								</div>
							</div>

							<div className="grid gap-3">
								<p className="playground-section">Fade curve</p>
								<div className="grid gap-3 sm:grid-cols-2">
									<RangeControl
										label="Flat core (%)"
										value={normalized.flatPercent}
										min={0}
										max={60}
										step={1}
										unit="%"
										onChange={(value) => setSettings((prev) => ({ ...prev, flatPercent: value }))}
									/>
									<RangeControl
										label="Fade end (%)"
										value={normalized.fadeEndPercent}
										min={40}
										max={100}
										step={1}
										unit="%"
										onChange={(value) =>
											setSettings((prev) => ({ ...prev, fadeEndPercent: value }))
										}
									/>
								</div>
								<div className="grid gap-3 sm:grid-cols-2">
									<label className="playground-field">
										<span>Curve style</span>
										<select
											value={normalized.curve}
											onChange={(event) => {
												const value = event.currentTarget.value;
												setSettings((prev) => ({
													...prev,
													curve: value as CurveType,
												}));
											}}
										>
											<option value="linear">Linear</option>
											<option value="ease-in">Ease in</option>
											<option value="ease-out">Ease out</option>
											<option value="ease-in-out">Ease in/out</option>
											<option value="sine-in">Sine in</option>
											<option value="sine-out">Sine out</option>
											<option value="sine-in-out">Sine in/out</option>
											<option value="expo-in">Expo in</option>
											<option value="expo-out">Expo out</option>
											<option value="expo-in-out">Expo in/out</option>
										</select>
									</label>
									<RangeControl
										label="Curve power"
										value={normalized.curvePower}
										min={0.5}
										max={3.5}
										step={0.1}
										precision={2}
										onChange={(value) => setSettings((prev) => ({ ...prev, curvePower: value }))}
									/>
								</div>
								<RangeControl
									label="Stop count"
									value={normalized.stopCount}
									min={4}
									max={12}
									step={1}
									onChange={(value) => setSettings((prev) => ({ ...prev, stopCount: value }))}
								/>
							</div>

							<div className="grid gap-3">
								<p className="playground-section">Gradient vector</p>
								<div className="grid gap-3 sm:grid-cols-2">
									<RangeControl
										label="Start X (%)"
										value={normalized.x1}
										min={0}
										max={100}
										step={1}
										unit="%"
										onChange={(value) => setSettings((prev) => ({ ...prev, x1: value }))}
									/>
									<RangeControl
										label="Start Y (%)"
										value={normalized.y1}
										min={0}
										max={100}
										step={1}
										unit="%"
										onChange={(value) => setSettings((prev) => ({ ...prev, y1: value }))}
									/>
									<RangeControl
										label="End X (%)"
										value={normalized.x2}
										min={0}
										max={100}
										step={1}
										unit="%"
										onChange={(value) => setSettings((prev) => ({ ...prev, x2: value }))}
									/>
									<RangeControl
										label="End Y (%)"
										value={normalized.y2}
										min={0}
										max={100}
										step={1}
										unit="%"
										onChange={(value) => setSettings((prev) => ({ ...prev, y2: value }))}
									/>
								</div>
							</div>

							<div className="grid gap-3">
								<p className="playground-section">Geometry</p>
								<div className="grid gap-3 sm:grid-cols-2">
									<RangeControl
										label="Radius"
										value={normalized.radius}
										min={10}
										max={15}
										step={0.5}
										precision={1}
										onChange={(value) => setSettings((prev) => ({ ...prev, radius: value }))}
									/>
									<div className="playground-field">
										<span>Viewbox</span>
										<div className="playground-chip">0 0 32 32</div>
									</div>
								</div>
							</div>
						</div>
					</section>

					<section className="playground-card">
						<div className="flex flex-wrap items-center justify-between gap-3">
							<h2 className="text-lg font-semibold">Preview</h2>
							<div className="flex gap-2">
								{SURFACES.map((item) => (
									<button
										key={item.value}
										type="button"
										className={`playground-button ${
											surface === item.value ? "playground-button-active" : ""
										}`}
										onClick={() => setSurface(item.value)}
									>
										{item.name}
									</button>
								))}
							</div>
						</div>

						<div className={`playground-preview playground-surface-${surface}`}>
							<div className="flex flex-wrap items-center justify-between gap-4">
								<div>
									<p className="playground-label">Logo</p>
									<p className="playground-muted text-sm">Live size sweep</p>
								</div>
								<div className="playground-preview-row">
									{[16, 24, 32, 64, 128].map((size) => (
										<LogoSvg
											key={size}
											size={size}
											gradientId={`${gradientIdBase}-${size}`}
											stops={gradientStops}
											settings={normalized}
										/>
									))}
								</div>
							</div>
							<div className="mt-6">
								<p className="playground-label">Gradient band</p>
								<div
									className="mt-3 h-4 w-full rounded-full"
									style={{
										background: `linear-gradient(90deg, ${gradientStops
											.map((stop) => {
												const { r, g, b } = hexToRgb(normalized.color);
												return `rgba(${r}, ${g}, ${b}, ${formatNumber(stop.opacity, 3)}) ${formatNumber(stop.offset)}%`;
											})
											.join(", ")})`,
									}}
								/>
							</div>
						</div>

						<div className="mt-8 grid gap-4 md:grid-cols-2">
							<div className="playground-panel">
								<div className="flex items-center justify-between">
									<p className="playground-label">Stops</p>
									<span className="playground-caption">{gradientStops.length} total</span>
								</div>
								<div className="mt-3 grid gap-2 text-xs playground-muted">
									{gradientStops.map((stop, index) => (
										<div key={`${stop.offset}-${index}`} className="flex justify-between">
											<span>{formatNumber(stop.offset)}%</span>
											<span>{formatNumber(stop.opacity, 3)}</span>
										</div>
									))}
								</div>
							</div>
							<div className="playground-panel">
								<div className="flex items-center justify-between">
									<p className="playground-label">Export</p>
									<button
										type="button"
										className="playground-button"
										onClick={() => onCopy(svgMarkup, "svg")}
									>
										{copied === "svg" ? "Copied" : "Copy SVG"}
									</button>
								</div>
								<pre className="playground-code mt-3">{settingsJson}</pre>
							</div>
						</div>
					</section>
				</div>

				<section className="playground-card">
					<h2 className="text-lg font-semibold">SVG preview</h2>
					<p className="playground-muted mt-2 text-sm">
						This is the exported SVG with your current settings.
					</p>
					<pre className="playground-code mt-4">{svgMarkup}</pre>
					<p className="playground-muted mt-4 text-sm">Gradient CSS (for mockups):</p>
					<pre className="playground-code mt-3">{gradientCss}</pre>
				</section>
			</div>
			<style>{`
				.playground-shell {
					position: relative;
					background: radial-gradient(circle at 20% 15%, rgba(46, 104, 255, 0.25), transparent 55%),
						linear-gradient(140deg, #0a0e14 0%, #0d1420 45%, #0a1017 100%);
					color: #f5f7fb;
					font-family: var(--font-display);
				}
				.playground-glow {
					position: absolute;
					inset: 0;
					background: radial-gradient(circle at 80% 10%, rgba(23, 91, 255, 0.25), transparent 40%),
						radial-gradient(circle at 10% 80%, rgba(43, 125, 255, 0.2), transparent 45%);
					opacity: 0.9;
				}
				.playground-grid {
					position: absolute;
					inset: 0;
					background-image: linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
						linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
					background-size: 48px 48px;
					mask-image: radial-gradient(circle at 50% 0%, black, transparent 60%);
				}
				.playground-kicker {
					letter-spacing: 0.35em;
					font-size: 0.65rem;
					text-transform: uppercase;
					color: rgba(255, 255, 255, 0.55);
				}
				.playground-muted {
					color: rgba(255, 255, 255, 0.65);
				}
				.playground-card {
					border-radius: 24px;
					border: 1px solid rgba(255, 255, 255, 0.1);
					background: rgba(10, 14, 20, 0.62);
					backdrop-filter: blur(16px);
					padding: 24px;
					box-shadow: 0 20px 60px rgba(8, 10, 16, 0.5);
				}
				.playground-section {
					font-size: 0.75rem;
					text-transform: uppercase;
					letter-spacing: 0.2em;
					color: rgba(255, 255, 255, 0.5);
				}
				.playground-label {
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.2em;
					color: rgba(255, 255, 255, 0.55);
				}
				.playground-caption {
					font-size: 0.7rem;
					color: rgba(255, 255, 255, 0.55);
				}
				.playground-field {
					display: grid;
					gap: 0.35rem;
					font-size: 0.75rem;
					color: rgba(255, 255, 255, 0.65);
				}
				.playground-field input[type="color"] {
					width: 100%;
					height: 40px;
					border-radius: 12px;
					border: 1px solid rgba(255, 255, 255, 0.16);
					background: rgba(255, 255, 255, 0.05);
					padding: 0;
				}
				.playground-field select {
					height: 40px;
					border-radius: 12px;
					border: 1px solid rgba(255, 255, 255, 0.16);
					background: rgba(255, 255, 255, 0.05);
					padding: 0 12px;
					color: #f5f7fb;
				}
				.playground-chip {
					display: inline-flex;
					align-items: center;
					height: 40px;
					border-radius: 12px;
					border: 1px solid rgba(255, 255, 255, 0.16);
					padding: 0 12px;
					background: rgba(255, 255, 255, 0.05);
					color: rgba(255, 255, 255, 0.7);
					font-family: var(--font-mono);
					font-size: 0.75rem;
				}
				.playground-number {
					display: inline-flex;
					align-items: center;
					gap: 6px;
					height: 40px;
					border-radius: 12px;
					border: 1px solid rgba(255, 255, 255, 0.16);
					padding: 0 10px;
					background: rgba(255, 255, 255, 0.05);
					font-family: var(--font-mono);
					font-size: 0.75rem;
					color: rgba(255, 255, 255, 0.75);
				}
				.playground-number input {
					width: 64px;
					border: none;
					background: transparent;
					color: inherit;
					font: inherit;
					outline: none;
				}
				.playground-number-unit {
					font-size: 0.7rem;
					color: rgba(255, 255, 255, 0.55);
				}
				.playground-pill {
					display: grid;
					gap: 0.1rem;
					border-radius: 999px;
					border: 1px solid rgba(255, 255, 255, 0.14);
					background: rgba(255, 255, 255, 0.05);
					padding: 0.5rem 0.9rem;
					font-size: 0.8rem;
					text-align: left;
					color: #f5f7fb;
					transition: transform 0.2s ease, border 0.2s ease, background 0.2s ease;
				}
				.playground-pill:hover {
					transform: translateY(-2px);
					border-color: rgba(255, 255, 255, 0.3);
					background: rgba(255, 255, 255, 0.08);
				}
				.playground-button {
					border-radius: 999px;
					border: 1px solid rgba(255, 255, 255, 0.16);
					padding: 0.4rem 0.9rem;
					font-size: 0.75rem;
					color: #f5f7fb;
					background: rgba(255, 255, 255, 0.05);
					transition: border 0.2s ease, background 0.2s ease;
				}
				.playground-button:hover {
					border-color: rgba(255, 255, 255, 0.35);
					background: rgba(255, 255, 255, 0.1);
				}
				.playground-button-active {
					border-color: rgba(62, 114, 255, 0.6);
					background: rgba(62, 114, 255, 0.18);
				}
				.playground-preview {
					margin-top: 20px;
					border-radius: 20px;
					padding: 24px;
					border: 1px solid rgba(255, 255, 255, 0.08);
					background: rgba(9, 13, 18, 0.6);
				}
				.playground-preview-row {
					display: flex;
					flex-wrap: wrap;
					align-items: center;
					gap: 12px;
				}
				.playground-surface-quartz {
					background: radial-gradient(circle at top, rgba(255, 255, 255, 0.12), transparent 50%),
						linear-gradient(120deg, #e8edf5, #cdd6e6);
					color: #0f172a;
				}
				.playground-surface-midnight {
					background: radial-gradient(circle at 20% 20%, rgba(38, 96, 255, 0.25), transparent 50%),
						linear-gradient(135deg, #0b1220 0%, #121a2c 50%, #0a0f18 100%);
				}
				.playground-surface-ink {
					background: radial-gradient(circle at 70% 20%, rgba(45, 98, 255, 0.25), transparent 40%),
						linear-gradient(135deg, #05070c 0%, #090b12 60%, #07090f 100%);
				}
				.playground-panel {
					border-radius: 18px;
					border: 1px solid rgba(255, 255, 255, 0.1);
					background: rgba(9, 12, 17, 0.6);
					padding: 16px;
				}
				.playground-code {
					border-radius: 16px;
					border: 1px solid rgba(255, 255, 255, 0.12);
					background: rgba(5, 7, 12, 0.8);
					padding: 16px;
					font-family: var(--font-mono);
					font-size: 0.75rem;
					white-space: pre-wrap;
					color: rgba(255, 255, 255, 0.7);
				}
				.playground-surface-quartz .playground-preview-row,
				.playground-surface-quartz .playground-panel,
				.playground-surface-quartz .playground-code {
					color: #0f172a;
				}
				.playground-surface-quartz .playground-label,
				.playground-surface-quartz .playground-muted,
				.playground-surface-quartz .playground-caption {
					color: rgba(15, 23, 42, 0.72);
				}
				.playground-surface-quartz .playground-number {
					background: rgba(255, 255, 255, 0.75);
					border-color: rgba(15, 23, 42, 0.12);
					color: rgba(15, 23, 42, 0.8);
				}
				.playground-surface-quartz .playground-number-unit {
					color: rgba(15, 23, 42, 0.6);
				}
				.playground-surface-quartz .playground-panel,
				.playground-surface-quartz .playground-code {
					background: rgba(255, 255, 255, 0.65);
					border-color: rgba(15, 23, 42, 0.12);
					color: rgba(15, 23, 42, 0.8);
				}
			`}</style>
		</div>
	);
}

function RangeControl({
	label,
	value,
	min,
	max,
	step,
	onChange,
	unit,
	precision,
}: {
	label: string;
	value: number;
	min: number;
	max: number;
	step: number;
	onChange: (value: number) => void;
	unit?: string;
	precision?: number;
}) {
	const displayValue = formatNumber(value, precision ?? (step < 1 ? 2 : 0));
	return (
		<label className="playground-field">
			<span>{label}</span>
			<div className="flex items-center gap-3">
				<input
					type="range"
					min={min}
					max={max}
					step={step}
					value={value}
					onChange={(event) => onChange(Number(event.currentTarget.value))}
					className="flex-1"
				/>
				<div className="playground-number">
					<input
						type="number"
						min={min}
						max={max}
						step={step}
						value={displayValue}
						onChange={(event) => {
							const raw = event.currentTarget.value;
							if (raw === "") return;
							const next = Number(raw);
							if (Number.isNaN(next)) return;
							onChange(clamp(next, min, max));
						}}
					/>
					{unit ? <span className="playground-number-unit">{unit}</span> : null}
				</div>
			</div>
		</label>
	);
}

function LogoSvg({
	size,
	gradientId,
	stops,
	settings,
}: {
	size: number;
	gradientId: string;
	stops: Stop[];
	settings: Settings;
}) {
	return (
		<svg
			width={size}
			height={size}
			viewBox="0 0 32 32"
			xmlns="http://www.w3.org/2000/svg"
			className="rounded-xl"
		>
			<defs>
				<linearGradient
					id={gradientId}
					x1={`${formatNumber(settings.x1)}%`}
					y1={`${formatNumber(settings.y1)}%`}
					x2={`${formatNumber(settings.x2)}%`}
					y2={`${formatNumber(settings.y2)}%`}
				>
					{stops.map((stop, index) => (
						<stop
							key={`${stop.offset}-${index}`}
							offset={`${formatNumber(stop.offset)}%`}
							stopColor={settings.color}
							stopOpacity={formatNumber(stop.opacity, 3)}
						/>
					))}
				</linearGradient>
			</defs>
			<circle cx="16" cy="16" r={formatNumber(settings.radius, 2)} fill={`url(#${gradientId})`} />
		</svg>
	);
}
