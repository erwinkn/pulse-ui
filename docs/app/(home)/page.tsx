import type { Metadata } from "next";
import { IBM_Plex_Mono, Oxanium } from "next/font/google";
import Link from "next/link";
import { codeToHtml } from "shiki";
import { HeroLights } from "./hero-lights.client";

const display = Oxanium({
	subsets: ["latin"],
	weight: ["400", "600", "700"],
	variable: "--font-display",
});

const mono = IBM_Plex_Mono({
	subsets: ["latin"],
	weight: ["400", "500", "600"],
	variable: "--font-body",
});

const CODE = `import pulse as ps

# Wrap any React component
@ps.react_component("Button", "@mantine/core")
def Button(*children, **props):
  ...

class Counter(ps.State):
    count: int = 0
    def inc(self):
        self.count += 1

@ps.component
def App():
    with ps.init():
        state = Counter()
    return ps.div(
        ps.h1(f"Count: {state.count}"),
        Button("+1", onClick=state.inc),
    )`;

const LINE_NUMBERS = Array.from({ length: 21 }, (_, i) => i + 1);

export const metadata: Metadata = {
	title: "Pulse",
	description:
		"Build interactive web apps entirely in Python. Pulse renders your code to a React frontend and keeps it in sync over WebSocket.",
	openGraph: {
		title: "Pulse",
		description:
			"Build interactive web apps entirely in Python. Pulse renders your code to a React frontend and keeps it in sync over WebSocket.",
		siteName: "Pulse",
		type: "website",
		url: "/",
		images: [
			{
				url: "/og/home",
				width: 1200,
				height: 630,
				alt: "Pulse — Reactive web apps. Pure Python.",
				type: "image/png",
			},
		],
	},
	twitter: {
		title: "Pulse",
		description:
			"Build interactive web apps entirely in Python. Pulse renders your code to a React frontend and keeps it in sync over WebSocket.",
		images: ["/og/home"],
	},
};

export default async function HomePage() {
	const highlighted = await codeToHtml(CODE, {
		lang: "python",
		themes: { light: "github-light", dark: "github-dark" },
	});
	return (
		<div
			className={`${display.variable} ${mono.variable} home-shell relative overflow-hidden`}
			style={{ fontFamily: "var(--font-body)" }}
		>
			<div className="pointer-events-none absolute inset-0">
				<div className="absolute inset-0 opacity-70 hero-scan-lines" />
				<HeroLights />
			</div>
			<div className="relative mx-auto w-full max-w-6xl px-6 pb-20 pt-12">
				<header className="flex flex-col gap-10 lg:flex-row lg:items-center lg:justify-between">
					<div className="max-w-xl">
						<h1
							className=" text-4xl font-semibold leading-tight md:text-6xl"
							style={{ fontFamily: "var(--font-display)" }}
						>
							Reactive web apps. Pure Python.
						</h1>
						<p className="home-muted mt-5 text-base md:text-lg">
							Build interactive web apps entirely in Python. Pulse renders your code to a React
							frontend and keeps it in sync over WebSocket. No JavaScript required.
						</p>
						<div className="mt-8 flex flex-wrap gap-3">
							<Link
								href="/docs/setup"
								className="home-cta rounded-full px-5 py-2 text-sm font-semibold transition hover:-translate-y-0.5"
							>
								Get started
							</Link>
							<Link
								href="/docs"
								className="home-cta-outline rounded-full border px-5 py-2 text-sm font-semibold transition hover:translate-y-[-2px]"
							>
								Docs
							</Link>
						</div>
					</div>
					<div className="w-full max-w-lg">
						<div className="home-editor rounded-xl border overflow-hidden">
							<div className="home-editor-titlebar flex items-center gap-3 px-4 py-3">
								<div className="flex gap-[7px]">
									<span className="home-dot home-dot-red" />
									<span className="home-dot home-dot-yellow" />
									<span className="home-dot home-dot-green" />
								</div>
								<div className="home-editor-tab rounded-md px-3 py-1 text-xs">example.py</div>
							</div>
							<div className="home-code flex overflow-x-auto text-[13px] leading-[1.7]">
								<div className="home-line-numbers select-none text-right pr-4 pl-4 py-4">
									{LINE_NUMBERS.map((n) => (
										<div key={n}>{n}</div>
									))}
								</div>
								<div
									className="flex-1 py-4 pr-4 [&_pre]:!bg-transparent [&_code]:!bg-transparent"
									// biome-ignore lint/security/noDangerouslySetInnerHtml: shiki output
									dangerouslySetInnerHTML={{ __html: highlighted }}
								/>
							</div>
						</div>
					</div>
				</header>

				<section className="mt-16">
					<div className="grid gap-6 md:grid-cols-3">
						<div className="home-feature">
							<p className="home-feature-title">Pure Python</p>
							<p className="home-muted mt-2 text-sm">
								Components, state, events—all Python. Use pandas, SQLAlchemy, or any library
								directly in your UI code.
							</p>
						</div>
						<div className="home-feature">
							<p className="home-feature-title">React-powered</p>
							<p className="home-muted mt-2 text-sm">
								Renders to a real React frontend. Access the full ecosystem of component libraries
								when you need them.
							</p>
						</div>
						<div className="home-feature">
							<p className="home-feature-title">Server-driven</p>
							<p className="home-muted mt-2 text-sm">
								State lives on the server. Changes sync instantly over WebSocket. No API layer to
								build.
							</p>
						</div>
					</div>
				</section>

				<section className="home-panel mt-16 rounded-3xl border p-8">
					<div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
						<div>
							<p className="home-muted-strong text-xs uppercase tracking-[0.2em]">
								Built for Python developers
							</p>
							<h2
								className="mt-3 text-2xl font-semibold"
								style={{ fontFamily: "var(--font-display)" }}
							>
								Dashboards, internal tools, data apps
							</h2>
							<p className="home-muted mt-3 text-sm">
								Ship production web apps without learning a frontend framework. One codebase, one
								language.
							</p>
						</div>
						{/*<Link
							href="/docs/tutorial"
							className="home-cta-outline rounded-full border px-5 py-2 text-sm font-semibold transition hover:translate-y-[-2px]"
						>
							Start the tutorial
						</Link>*/}
					</div>
				</section>
			</div>
			<style>{`
				.home-shell {
					background-color: var(--home-bg);
					color: var(--home-fg);
					--home-bg: #e4e9ef;
					--home-fg: #0b0f14;
					--home-muted: rgba(15, 23, 42, 0.82);
					--home-muted-strong: rgba(15, 23, 42, 0.62);
					--home-border: rgba(15, 23, 42, 0.12);
					--home-border-strong: rgba(15, 23, 42, 0.2);
					--home-surface: rgba(255, 255, 255, 0.7);
					--home-surface-strong: rgba(255, 255, 255, 0.85);
					--home-editor-bg: rgba(255, 255, 255, 0.92);
					--home-editor-titlebar: rgba(245, 247, 250, 0.95);
					--home-editor-tab: rgba(255, 255, 255, 0.8);
					--home-line-number: rgba(15, 23, 42, 0.35);
					--home-panel-bg: rgba(255, 255, 255, 0.25);
					--home-panel-border-outer: rgba(15, 23, 42, 0.08);
					--home-panel-border-inner: rgba(255, 255, 255, 0.7);
					--home-panel-shadow: 0 8px 32px rgba(15, 23, 42, 0.08);
					--home-pill: rgba(255, 255, 255, 0.85);
					--home-cta-bg: #0b0f14;
					--home-cta-fg: #ffffff;
					--home-shadow: 0 16px 40px rgba(15, 23, 42, 0.12);
					--scan-line-strong: rgba(10, 20, 30, 0.08);
					--scan-line-soft: rgba(10, 20, 30, 0.06);
					--scan-mask: radial-gradient(circle at 50% 20%, black, transparent 70%);
					--light-blend: normal;
					--light-opacity: 0.78;
					--pulse-peak: 0.72;
					--pulse-mid: 0.36;
					--pulse-tail: 0.18;
					--pulse-border: 3px;
					--pulse-shadow: 0 0 65px;
				}
				.dark .home-shell {
					--home-bg: #0b0f14;
					--home-fg: #ffffff;
					--home-muted: rgba(255, 255, 255, 0.7);
					--home-muted-strong: rgba(255, 255, 255, 0.5);
					--home-border: rgba(255, 255, 255, 0.15);
					--home-border-strong: rgba(255, 255, 255, 0.3);
					--home-surface: rgba(255, 255, 255, 0.06);
					--home-surface-strong: rgba(255, 255, 255, 0.09);
					--home-editor-bg: rgba(15, 20, 28, 0.92);
					--home-editor-titlebar: rgba(20, 26, 36, 0.95);
					--home-editor-tab: rgba(255, 255, 255, 0.08);
					--home-line-number: rgba(255, 255, 255, 0.25);
					--home-panel-bg: rgba(255, 255, 255, 0.04);
					--home-panel-border-outer: rgba(255, 255, 255, 0.1);
					--home-panel-border-inner: rgba(255, 255, 255, 0.15);
					--home-panel-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
					--home-pill: rgba(255, 255, 255, 0.06);
					--home-cta-bg: #ffffff;
					--home-cta-fg: #0b0f14;
					--home-shadow: 0 0 40px rgba(0, 0, 0, 0.45);
					--scan-line-strong: rgba(255, 255, 255, 0.05);
					--scan-line-soft: rgba(255, 255, 255, 0.04);
					--scan-mask: radial-gradient(circle at 50% 20%, black, transparent 70%);
					--light-blend: screen;
					--light-opacity: 0.4;
					--pulse-peak: 0.45;
					--pulse-mid: 0.18;
					--pulse-tail: 0.07;
					--pulse-border: 2px;
					--pulse-shadow: 0 0 45px;
				}
				.home-muted {
					color: var(--home-muted);
				}
				.home-muted-strong {
					color: var(--home-muted-strong);
				}
				html.dark .home-code span,
				.dark .home-code span {
					color: var(--shiki-dark) !important;
				}
				.home-pill {
					border-color: var(--home-border);
					background: var(--home-pill);
					color: var(--home-muted);
				}
				.home-editor {
					border-color: var(--home-border);
					background: var(--home-editor-bg);
					box-shadow: var(--home-shadow);
				}
				.home-editor-titlebar {
					background: var(--home-editor-titlebar);
					border-bottom: 1px solid var(--home-border);
				}
				.home-editor-tab {
					background: var(--home-editor-tab);
					color: var(--home-muted);
				}
				.home-dot {
					width: 12px;
					height: 12px;
					border-radius: 50%;
				}
				.home-dot-red {
					background: #ff5f57;
				}
				.home-dot-yellow {
					background: #febc2e;
				}
				.home-dot-green {
					background: #28c840;
				}
				.home-line-numbers {
					color: var(--home-line-number);
					border-right: 1px solid var(--home-border);
				}
				.home-panel {
					border-color: var(--home-panel-border-outer);
					background: var(--home-panel-bg);
					backdrop-filter: blur(24px);
					-webkit-backdrop-filter: blur(24px);
					box-shadow:
						var(--home-panel-shadow),
						inset 0 1px 0 0 var(--home-panel-border-inner),
						inset 1px 0 0 0 var(--home-panel-border-inner);
				}
				.home-feature {
					padding-top: 1.5rem;
					border-top: 1px solid var(--home-border);
				}
				.home-feature-title {
					font-family: var(--font-display);
					font-size: 1.05rem;
					font-weight: 600;
				}
				@media (min-width: 768px) {
					.home-feature {
						padding-top: 0;
						padding-left: 1.5rem;
						border-top: 0;
						border-left: 1px solid var(--home-border);
					}
					.home-feature:first-child {
						padding-left: 0;
						border-left-color: transparent;
					}
				}
				@media (max-width: 767px) {
					.home-feature:first-child {
						padding-top: 0;
						border-top: 0;
					}
				}
				.home-cta {
					background: var(--home-cta-bg);
					color: var(--home-cta-fg);
				}
				.home-cta-outline {
					border-color: var(--home-border-strong);
					color: var(--home-muted);
				}
					.home-cta-outline:hover {
						color: var(--home-fg);
						border-color: var(--home-fg);
					}
					.hero-scan-lines {
						background-image: linear-gradient(
							90deg,
							var(--scan-line-strong) 1px,
						transparent 1px
					), linear-gradient(var(--scan-line-soft) 1px, transparent 1px);
					background-size: 120px 120px;
					mask-image: var(--scan-mask);
				}
				.hero-field {
					pointer-events: none;
				}
				.hero-pulse-layer {
					position: absolute;
					inset: 0;
					pointer-events: none;
				}
				.hero-light {
					position: absolute;
					border-radius: 999px;
					pointer-events: none;
					transform: translate(-50%, -50%);
				}
				.hero-light-core {
					position: absolute;
					inset: 0;
					border-radius: inherit;
					will-change: transform;
					background: radial-gradient(circle, var(--light-color), transparent 70%);
					opacity: var(--light-opacity);
					mix-blend-mode: var(--light-blend);
				}
				.hero-field[data-js="true"] .hero-light-core {
					animation: none;
				}
				.hero-pulse {
					position: absolute;
					border-radius: 999px;
					pointer-events: none;
					left: var(--pulse-x, 50%);
					top: var(--pulse-y, 50%);
					width: var(--pulse-size, 600px);
					height: var(--pulse-size, 600px);
					border: var(--pulse-border) solid
						color-mix(in srgb, var(--pulse-color, var(--light-color)), transparent 35%);
					opacity: 0;
					transform: translate(-50%, -50%) scale(0.18);
					transform-origin: center;
					animation: hero-pulse 24s linear infinite;
					box-shadow: var(--pulse-shadow)
						color-mix(in srgb, var(--pulse-color, var(--light-color)), transparent 55%);
				}
				.hero-pulse-a {
					--pulse-x: 18%;
					--pulse-y: 20%;
					--pulse-size: 720px;
					--pulse-color: rgba(60, 140, 210, 0.48);
					animation-delay: 0s;
				}
				.hero-pulse-b {
					--pulse-x: 74%;
					--pulse-y: 26%;
					--pulse-size: 840px;
					--pulse-color: rgba(60, 180, 150, 0.48);
					animation-delay: -8s;
				}
				.hero-pulse-c {
					--pulse-x: 24%;
					--pulse-y: 76%;
					--pulse-size: 640px;
					--pulse-color: rgba(210, 125, 65, 0.54);
					animation-delay: -16s;
				}
				.hero-light-a {
					left: 18%;
					top: 20%;
					width: 720px;
					height: 720px;
					--light-color: rgba(50, 135, 220, 0.52);
				}
				.hero-light-b {
					left: 74%;
					top: 26%;
					width: 840px;
					height: 840px;
					--light-color: rgba(55, 185, 155, 0.5);
				}
				.hero-light-c {
					left: 24%;
					top: 76%;
					width: 640px;
					height: 640px;
					--light-color: rgba(230, 130, 70, 0.58);
				}
				.hero-light-d {
					left: 50%;
					top: -8%;
					width: 520px;
					height: 520px;
					--light-color: rgba(100, 165, 230, 0.48);
				}
				.hero-light-e {
					left: 92%;
					top: 70%;
					width: 520px;
					height: 520px;
					--light-color: rgba(70, 185, 135, 0.48);
				}
				.dark .hero-light-a {
					--light-color: rgba(70, 210, 255, 0.26);
				}
				.dark .hero-light-b {
					--light-color: rgba(120, 255, 210, 0.3);
				}
				.dark .hero-light-c {
					--light-color: rgba(255, 168, 88, 0.32);
				}
				.dark .hero-light-d {
					--light-color: rgba(170, 230, 255, 0.22);
				}
				.dark .hero-light-e {
					--light-color: rgba(130, 255, 190, 0.28);
				}
				.dark .hero-pulse-a {
					--pulse-color: rgba(70, 210, 255, 0.26);
				}
				.dark .hero-pulse-b {
					--pulse-color: rgba(120, 255, 210, 0.3);
				}
				.dark .hero-pulse-c {
					--pulse-color: rgba(255, 168, 88, 0.32);
				}
				@keyframes hero-pulse {
					0% {
						opacity: 0;
						transform: translate(-50%, -50%) scale(0.18);
					}
					12% {
						opacity: var(--pulse-peak);
					}
					32% {
						opacity: var(--pulse-mid);
					}
					55% {
						opacity: var(--pulse-tail);
					}
					100% {
						opacity: 0;
						transform: translate(-50%, -50%) scale(1.6);
					}
				}
			`}</style>
		</div>
	);
}
