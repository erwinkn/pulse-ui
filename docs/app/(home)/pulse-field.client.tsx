"use client";

import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";

const palettes = [
	{
		core: "rgba(80, 240, 210, 0.32)",
		ring: "rgba(80, 240, 210, 0.38)",
		ringAlt: "rgba(255, 168, 88, 0.3)",
	},
	{
		core: "rgba(120, 210, 255, 0.26)",
		ring: "rgba(120, 210, 255, 0.34)",
		ringAlt: "rgba(120, 255, 210, 0.28)",
	},
	{
		core: "rgba(130, 255, 190, 0.28)",
		ring: "rgba(130, 255, 190, 0.34)",
		ringAlt: "rgba(255, 200, 120, 0.28)",
	},
] as const;

const bounds = {
	x: [50, 94],
	y: [8, 86],
	size: [700, 1100],
};

type PulseSource = {
	id: number;
	x: number;
	y: number;
	size: number;
	paletteIndex: number;
};

type Velocity = {
	vx: number;
	vy: number;
};

type PulseRing = {
	id: number;
	x: number;
	y: number;
	size: number;
	paletteIndex: number;
};

const pulseIntervalMs = 8500;
const pulseDurationMs = 12000;

function clamp(value: number, min: number, max: number) {
	return Math.min(max, Math.max(min, value));
}

function randomRange(min: number, max: number) {
	return Math.random() * (max - min) + min;
}

function randomSigned(min: number, max: number) {
	const sign = Math.random() < 0.5 ? -1 : 1;
	return randomRange(min, max) * sign;
}

function makeSource(id: number): PulseSource {
	return {
		id,
		x: randomRange(bounds.x[0], bounds.x[1]),
		y: randomRange(bounds.y[0], bounds.y[1]),
		size: randomRange(bounds.size[0], bounds.size[1]),
		paletteIndex: Math.floor(Math.random() * palettes.length),
	};
}

function makeVelocity(): Velocity {
	return {
		vx: randomSigned(0.3, 0.7),
		vy: randomSigned(0.15, 0.35),
	};
}

export function PulseField() {
	const [sources, setSources] = useState<PulseSource[]>([]);
	const [pulses, setPulses] = useState<PulseRing[]>([]);
	const velocitiesRef = useRef<Velocity[]>([]);
	const sourcesRef = useRef<PulseSource[]>(sources);
	const pulseIdRef = useRef(0);
	const timeoutsRef = useRef<number[]>([]);

	useEffect(() => {
		const nextSources = Array.from({ length: 3 }, (_, index) => makeSource(index));
		velocitiesRef.current = Array.from({ length: 3 }, () => makeVelocity());
		setSources(nextSources);
	}, []);

	useEffect(() => {
		const interval = setInterval(() => {
			setSources((current) =>
				current.map((source, index) => {
					const velocity = velocitiesRef.current[index] ?? makeVelocity();
					velocitiesRef.current[index] = velocity;
					const next = {
						...source,
						x: source.x + velocity.vx * 0.1,
						y: source.y + velocity.vy * 0.1,
						size: source.size + randomSigned(0.2, 0.6),
					};

					if (next.x < bounds.x[0] || next.x > bounds.x[1]) {
						velocity.vx *= -1;
						next.x = clamp(next.x, bounds.x[0], bounds.x[1]);
					}
					if (next.y < bounds.y[0] || next.y > bounds.y[1]) {
						velocity.vy *= -1;
						next.y = clamp(next.y, bounds.y[0], bounds.y[1]);
					}

					velocity.vx = clamp(velocity.vx + randomSigned(0.0, 0.02), -0.8, 0.8);
					velocity.vy = clamp(velocity.vy + randomSigned(0.0, 0.02), -0.5, 0.5);

					return {
						...next,
						size: clamp(next.size, bounds.size[0], bounds.size[1]),
					};
				}),
			);
		}, 100);

		return () => clearInterval(interval);
	}, []);

	useEffect(() => {
		sourcesRef.current = sources;
	}, [sources]);

	useEffect(() => {
		const spawnPulse = () => {
			const currentSources = sourcesRef.current;
			if (currentSources.length === 0) {
				return;
			}
			const nextIndex = Math.floor(Math.random() * currentSources.length);
			const source = currentSources[nextIndex];
			if (!source) {
				return;
			}
			const nextId = pulseIdRef.current;
			pulseIdRef.current += 1;
			setPulses((current) => [
				...current,
				{
					id: nextId,
					x: source.x,
					y: source.y,
					size: source.size,
					paletteIndex: source.paletteIndex,
				},
			]);
			const timeout = window.setTimeout(() => {
				setPulses((current) => current.filter((pulse) => pulse.id !== nextId));
			}, pulseDurationMs);
			timeoutsRef.current.push(timeout);
		};

		spawnPulse();
		const interval = setInterval(spawnPulse, pulseIntervalMs);

		return () => {
			clearInterval(interval);
			timeoutsRef.current.forEach((timeout) => void clearTimeout(timeout));
			timeoutsRef.current = [];
		};
	}, []);

	return (
		<div className="absolute inset-0">
			{sources.map((source) => {
				const palette = palettes[source.paletteIndex];
				return (
					<div
						key={source.id}
						className="forge-source"
						style={
							{
								left: `${source.x}%`,
								top: `${source.y}%`,
								width: `${source.size}px`,
								height: `${source.size}px`,
								"--pulse-core": palette.core,
							} as CSSProperties
						}
					>
						<div className="forge-source-core" />
					</div>
				);
			})}
			{pulses.map((pulse) => {
				const palette = palettes[pulse.paletteIndex];
				return (
					<div
						key={pulse.id}
						className="forge-pulse-ring"
						style={
							{
								left: `${pulse.x}%`,
								top: `${pulse.y}%`,
								width: `${pulse.size}px`,
								height: `${pulse.size}px`,
								"--pulse-ring": palette.ring,
								"--pulse-ring-alt": palette.ringAlt,
							} as CSSProperties
						}
						aria-hidden
					/>
				);
			})}
			<style jsx>{`
				.forge-source,
				.forge-pulse-ring {
					position: absolute;
					transform: translate(-50%, -50%);
					pointer-events: none;
				}
				.forge-source {
					opacity: 0.8;
					filter: saturate(1.1);
				}
				.forge-source-core {
					position: absolute;
					inset: 0;
					border-radius: 999px;
					background: radial-gradient(
						circle,
						var(--pulse-core),
						rgba(10, 20, 28, 0.02) 55%,
						transparent 80%
					);
					filter: blur(12px);
					opacity: 0.65;
				}
				.forge-pulse-ring {
					border-radius: 999px;
					border: 2px solid var(--pulse-ring);
					opacity: 0;
					transform: translate(-50%, -50%) scale(0.16);
					animation: forge-pulse-scale 12s linear forwards,
						forge-pulse-fade 12s ease-in forwards;
					mask-image: radial-gradient(circle, black 70%, transparent 85%);
					box-shadow: 0 0 50px rgba(80, 240, 210, 0.2);
				}
				@keyframes forge-pulse-scale {
					0% {
						transform: translate(-50%, -50%) scale(0.16);
					}
					100% {
						transform: translate(-50%, -50%) scale(1.25);
					}
				}
				@keyframes forge-pulse-fade {
					0% {
						opacity: 0;
						box-shadow: 0 0 50px rgba(80, 240, 210, 0.2);
					}
					10% {
						opacity: 0.55;
					}
					35% {
						opacity: 0.2;
					}
					55% {
						opacity: 0.12;
					}
					70% {
						opacity: 0.08;
						border-color: var(--pulse-ring-alt);
						box-shadow: 0 0 10px rgba(80, 240, 210, 0.08);
					}
					100% {
						opacity: 0;
						box-shadow: 0 0 0 rgba(80, 240, 210, 0);
					}
				}
				@media (max-width: 768px) {
					.forge-source {
						opacity: 0.45;
					}
					.forge-pulse-ring {
						border-width: 1px;
					}
				}
			`}</style>
		</div>
	);
}
