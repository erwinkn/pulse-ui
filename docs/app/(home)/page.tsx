import { IBM_Plex_Mono, Oxanium } from "next/font/google";
import Link from "next/link";
import { PulseField } from "./pulse-field.client";

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
			className={`${display.variable} ${mono.variable} relative overflow-hidden bg-[#0b0f14] text-white`}
			style={{ fontFamily: "var(--font-body)" }}
		>
			<div className="pointer-events-none absolute inset-0">
				<div className="absolute inset-0 opacity-70 forge-scan-lines" />
				<div className="absolute -top-32 left-1/2 h-[420px] w-[420px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,_rgba(70,210,255,0.25),_transparent_65%)] blur-2xl" />
				<div className="absolute -bottom-40 -left-10 h-[360px] w-[360px] rounded-full bg-[radial-gradient(circle,_rgba(255,155,65,0.18),_transparent_70%)] blur-2xl forge-orb" />
				<div className="absolute right-[-10%] top-[30%] h-[280px] w-[280px] rounded-full bg-[radial-gradient(circle,_rgba(70,255,194,0.18),_transparent_70%)] blur-2xl forge-orb-alt" />
				<PulseField />
			</div>
			<div className="relative mx-auto w-full max-w-6xl px-6 pb-20 pt-12">
				<header className="flex flex-col gap-10 lg:flex-row lg:items-center lg:justify-between">
					<div className="max-w-xl">
						<p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.2em] text-white/70">
							Pulse Forge
						</p>
						<h1
							className="mt-6 text-4xl font-semibold leading-tight md:text-6xl"
							style={{ fontFamily: "var(--font-display)" }}
						>
							Reactive web apps, forged in Python.
						</h1>
						<p className="mt-5 text-base text-white/70 md:text-lg">
							Pulse runs a React UI with WebSocket-driven updates, while you stay in Python for
							state, events, and composition.
						</p>
						<div className="mt-8 flex flex-wrap gap-3">
							<Link
								href="/docs/setup"
								className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-black transition hover:-translate-y-0.5"
							>
								Get started
							</Link>
							<Link
								href="/docs"
								className="rounded-full border border-white/20 px-5 py-2 text-sm font-semibold text-white/80 transition hover:border-white/60 hover:text-white"
							>
								Docs
							</Link>
						</div>
						<div className="mt-10 flex flex-wrap gap-4 text-xs uppercase tracking-[0.2em] text-white/50">
							<span>Server state</span>
							<span>Typed updates</span>
							<span>React renderer</span>
						</div>
					</div>
					<div className="w-full max-w-lg space-y-4">
						<div className="rounded-2xl border border-white/15 bg-white/5 p-5 shadow-[0_0_40px_rgba(0,0,0,0.5)]">
							<div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-white/60">
								<span>Pulse state</span>
								<span>live</span>
							</div>
							<pre className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-white/80">
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
							<div className="rounded-xl border border-white/10 bg-white/5 p-3">
								<p className="text-xs uppercase tracking-[0.2em] text-white/50">Transport</p>
								<p className="mt-2 text-sm">WebSocket diff sync</p>
							</div>
							<div className="rounded-xl border border-white/10 bg-white/5 p-3">
								<p className="text-xs uppercase tracking-[0.2em] text-white/50">UI</p>
								<p className="mt-2 text-sm">React-driven render</p>
							</div>
							<div className="rounded-xl border border-white/10 bg-white/5 p-3">
								<p className="text-xs uppercase tracking-[0.2em] text-white/50">State</p>
								<p className="mt-2 text-sm">Python classes</p>
							</div>
						</div>
					</div>
				</header>

				<section className="mt-16 grid gap-6 md:grid-cols-3">
					<div className="rounded-2xl border border-white/15 bg-white/5 p-6">
						<h2 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
							Build in Python
						</h2>
						<p className="mt-3 text-sm text-white/70">
							Keep server logic, state, and UI composition in one place. No glue code between
							stacks.
						</p>
					</div>
					<div className="rounded-2xl border border-white/15 bg-white/5 p-6">
						<h2 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
							React front-end
						</h2>
						<p className="mt-3 text-sm text-white/70">
							Pulse renders to React and streams updates. Your UI feels instant without extra client
							state.
						</p>
					</div>
					<div className="rounded-2xl border border-white/15 bg-white/5 p-6">
						<h2 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
							Always in sync
						</h2>
						<p className="mt-3 text-sm text-white/70">
							UI updates flow over WebSocket. The server is the source of truth.
						</p>
					</div>
				</section>

				<section className="mt-16 rounded-3xl border border-white/15 bg-gradient-to-br from-white/5 via-white/0 to-white/5 p-8">
					<div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
						<div>
							<p className="text-xs uppercase tracking-[0.2em] text-white/60">Flow</p>
							<h2
								className="mt-3 text-2xl font-semibold"
								style={{ fontFamily: "var(--font-display)" }}
							>
								{"State -> Render -> Event -> Update"}
							</h2>
							<p className="mt-3 text-sm text-white/70">
								Keep loops tight. Ship complex flows without juggling multiple runtimes.
							</p>
						</div>
						<Link
							href="/docs"
							className="rounded-full border border-white/30 px-5 py-2 text-sm font-semibold text-white transition hover:border-white/60"
						>
							Explore docs
						</Link>
					</div>
				</section>
			</div>
			<style>{`
				.forge-scan-lines {
					background-image: linear-gradient(
						90deg,
						rgba(255, 255, 255, 0.05) 1px,
						transparent 1px
					), linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
					background-size: 120px 120px;
					mask-image: radial-gradient(circle at 50% 20%, black, transparent 70%);
				}
				.forge-orb {
					animation: forge-drift 14s ease-in-out infinite;
				}
				.forge-orb-alt {
					animation: forge-drift-alt 18s ease-in-out infinite;
				}
				@keyframes forge-drift {
					0% {
						transform: translateY(0px);
					}
					50% {
						transform: translateY(-18px);
					}
					100% {
						transform: translateY(0px);
					}
				}
				@keyframes forge-drift-alt {
					0% {
						transform: translateY(0px) scale(1);
					}
					50% {
						transform: translateY(14px) scale(1.05);
					}
					100% {
						transform: translateY(0px) scale(1);
					}
				}
			`}</style>
		</div>
	);
}
