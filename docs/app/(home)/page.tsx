import { IBM_Plex_Mono, Oxanium } from "next/font/google";
import Link from "next/link";
import { ForgeLights } from "./forge-lights.client";

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

export default function HomePage() {
	return (
		<div
			className={`${display.variable} ${mono.variable} home-shell relative overflow-hidden`}
			style={{ fontFamily: "var(--font-body)" }}
		>
			<div className="pointer-events-none absolute inset-0">
				<div className="absolute inset-0 opacity-70 forge-scan-lines" />
				<ForgeLights />
			</div>
			<div className="relative mx-auto w-full max-w-6xl px-6 pb-20 pt-12">
				<header className="flex flex-col gap-10 lg:flex-row lg:items-center lg:justify-between">
					<div className="max-w-xl">
						<p className="home-pill inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs uppercase tracking-[0.2em]">
							Pulse Forge
						</p>
						<h1
							className="mt-6 text-4xl font-semibold leading-tight md:text-6xl"
							style={{ fontFamily: "var(--font-display)" }}
						>
							Reactive web apps, forged in Python.
						</h1>
						<p className="home-muted mt-5 text-base md:text-lg">
							Pulse runs a React UI with WebSocket-driven updates, while you stay in Python for
							state, events, and composition.
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
						<div className="home-muted-strong mt-10 flex flex-wrap gap-4 text-xs uppercase tracking-[0.2em]">
							<span>Server state</span>
							<span>Typed updates</span>
							<span>React renderer</span>
						</div>
					</div>
					<div className="w-full max-w-lg space-y-4">
						<div className="home-card rounded-2xl border p-5">
							<div className="home-muted-strong flex items-center justify-between text-xs uppercase tracking-[0.2em]">
								<span>Pulse state</span>
								<span>live</span>
							</div>
							<pre className="home-code mt-4 whitespace-pre-wrap text-sm leading-relaxed">
								<code>{`import pulse as ps

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
        ps.button("Increment", onClick=state.inc),
    )`}</code>
							</pre>
						</div>
						<div className="grid gap-3 sm:grid-cols-3">
							<div className="home-card rounded-xl border p-3">
								<p className="home-muted-strong text-xs uppercase tracking-[0.2em]">Transport</p>
								<p className="mt-2 text-sm">WebSocket diff sync</p>
							</div>
							<div className="home-card rounded-xl border p-3">
								<p className="home-muted-strong text-xs uppercase tracking-[0.2em]">UI</p>
								<p className="mt-2 text-sm">React-driven render</p>
							</div>
							<div className="home-card rounded-xl border p-3">
								<p className="home-muted-strong text-xs uppercase tracking-[0.2em]">State</p>
								<p className="mt-2 text-sm">Python classes</p>
							</div>
						</div>
					</div>
				</header>

				<section className="mt-16 grid gap-6 md:grid-cols-3">
					<div className="home-card rounded-2xl border p-6">
						<h2 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
							Build in Python
						</h2>
						<p className="home-muted mt-3 text-sm">
							Keep server logic, state, and UI composition in one place. No glue code between
							stacks.
						</p>
					</div>
					<div className="home-card rounded-2xl border p-6">
						<h2 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
							React front-end
						</h2>
						<p className="home-muted mt-3 text-sm">
							Pulse renders to React and streams updates. Your UI feels instant without extra client
							state.
						</p>
					</div>
					<div className="home-card rounded-2xl border p-6">
						<h2 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
							Always in sync
						</h2>
						<p className="home-muted mt-3 text-sm">
							UI updates flow over WebSocket. The server is the source of truth.
						</p>
					</div>
				</section>

				<section className="home-panel mt-16 rounded-3xl border p-8">
					<div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
						<div>
							<p className="home-muted-strong text-xs uppercase tracking-[0.2em]">Flow</p>
							<h2
								className="mt-3 text-2xl font-semibold"
								style={{ fontFamily: "var(--font-display)" }}
							>
								{"State -> Render -> Event -> Update"}
							</h2>
							<p className="home-muted mt-3 text-sm">
								Keep loops tight. Ship complex flows without juggling multiple runtimes.
							</p>
						</div>
						<Link
							href="/docs"
							className="home-cta-outline rounded-full border px-5 py-2 text-sm font-semibold transition hover:translate-y-[-2px]"
						>
							Explore docs
						</Link>
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
					--home-panel-bg: linear-gradient(
						135deg,
						rgba(255, 255, 255, 0.9),
						rgba(255, 255, 255, 0.6)
					);
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
					--home-panel-bg: linear-gradient(
						135deg,
						rgba(255, 255, 255, 0.06),
						rgba(255, 255, 255, 0.02)
					);
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
				.home-code {
					color: rgba(15, 23, 42, 0.78);
				}
				.dark .home-code {
					color: rgba(255, 255, 255, 0.78);
				}
				.home-pill {
					border-color: var(--home-border);
					background: var(--home-pill);
					color: var(--home-muted);
				}
				.home-card {
					border-color: var(--home-border);
					background: var(--home-surface);
					box-shadow: var(--home-shadow);
				}
				.home-panel {
					border-color: var(--home-border);
					background: var(--home-panel-bg);
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
				.forge-scan-lines {
					background-image: linear-gradient(
						90deg,
						var(--scan-line-strong) 1px,
						transparent 1px
					), linear-gradient(var(--scan-line-soft) 1px, transparent 1px);
					background-size: 120px 120px;
					mask-image: var(--scan-mask);
				}
				.forge-field {
					pointer-events: none;
				}
				.forge-pulse-layer {
					position: absolute;
					inset: 0;
					pointer-events: none;
				}
				.forge-light {
					position: absolute;
					border-radius: 999px;
					pointer-events: none;
					transform: translate(-50%, -50%);
				}
				.forge-light-core {
					position: absolute;
					inset: 0;
					border-radius: inherit;
					will-change: transform;
					background: radial-gradient(circle, var(--light-color), transparent 70%);
					opacity: var(--light-opacity);
					mix-blend-mode: var(--light-blend);
				}
				.forge-field[data-js="true"] .forge-light-core {
					animation: none;
				}
				.forge-pulse {
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
					animation: forge-pulse 24s linear infinite;
					box-shadow: var(--pulse-shadow)
						color-mix(in srgb, var(--pulse-color, var(--light-color)), transparent 55%);
				}
				.forge-pulse-a {
					--pulse-x: 18%;
					--pulse-y: 20%;
					--pulse-size: 720px;
					--pulse-color: rgba(60, 140, 210, 0.48);
					animation-delay: 0s;
				}
				.forge-pulse-b {
					--pulse-x: 74%;
					--pulse-y: 26%;
					--pulse-size: 840px;
					--pulse-color: rgba(60, 180, 150, 0.48);
					animation-delay: -8s;
				}
				.forge-pulse-c {
					--pulse-x: 24%;
					--pulse-y: 76%;
					--pulse-size: 640px;
					--pulse-color: rgba(210, 125, 65, 0.54);
					animation-delay: -16s;
				}
				.forge-light-a {
					left: 18%;
					top: 20%;
					width: 720px;
					height: 720px;
					--light-color: rgba(50, 135, 220, 0.52);
				}
				.forge-light-b {
					left: 74%;
					top: 26%;
					width: 840px;
					height: 840px;
					--light-color: rgba(55, 185, 155, 0.5);
				}
				.forge-light-c {
					left: 24%;
					top: 76%;
					width: 640px;
					height: 640px;
					--light-color: rgba(230, 130, 70, 0.58);
				}
				.forge-light-d {
					left: 50%;
					top: -8%;
					width: 520px;
					height: 520px;
					--light-color: rgba(100, 165, 230, 0.48);
				}
				.forge-light-e {
					left: 92%;
					top: 70%;
					width: 520px;
					height: 520px;
					--light-color: rgba(70, 185, 135, 0.48);
				}
				.dark .forge-light-a {
					--light-color: rgba(70, 210, 255, 0.26);
				}
				.dark .forge-light-b {
					--light-color: rgba(120, 255, 210, 0.3);
				}
				.dark .forge-light-c {
					--light-color: rgba(255, 168, 88, 0.32);
				}
				.dark .forge-light-d {
					--light-color: rgba(170, 230, 255, 0.22);
				}
				.dark .forge-light-e {
					--light-color: rgba(130, 255, 190, 0.28);
				}
				.dark .forge-pulse-a {
					--pulse-color: rgba(70, 210, 255, 0.26);
				}
				.dark .forge-pulse-b {
					--pulse-color: rgba(120, 255, 210, 0.3);
				}
				.dark .forge-pulse-c {
					--pulse-color: rgba(255, 168, 88, 0.32);
				}
				@keyframes forge-pulse {
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
