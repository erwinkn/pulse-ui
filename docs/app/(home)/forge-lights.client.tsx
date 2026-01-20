"use client";

import { useEffect, useRef } from "react";

type LightState = {
	el: HTMLDivElement;
	x: number;
	y: number;
	vx: number;
	vy: number;
	size: number;
	color: string;
};

const bounds = {
	x: [8, 92],
	y: [8, 92],
};

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

export function ForgeLights() {
	const rootRef = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		const root = rootRef.current;
		if (!root) {
			return;
		}

		if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
			return;
		}

		const pulseLayer = root.querySelector<HTMLDivElement>(".forge-pulse-layer");
		const lightEls = Array.from(root.querySelectorAll<HTMLDivElement>(".forge-light"));
		const pulseEls = Array.from(root.querySelectorAll<HTMLDivElement>(".forge-pulse"));
		if (!pulseLayer || lightEls.length === 0) {
			return;
		}

		root.dataset.js = "true";

		const rootRect = root.getBoundingClientRect();
		const lights: LightState[] = lightEls.map((el) => {
			const rect = el.getBoundingClientRect();
			const centerX = (rect.left + rect.width / 2 - rootRect.left) / rootRect.width;
			const centerY = (rect.top + rect.height / 2 - rootRect.top) / rootRect.height;
			const color = getComputedStyle(el).getPropertyValue("--light-color").trim();
			return {
				el,
				x: clamp(centerX * 100, bounds.x[0], bounds.x[1]),
				y: clamp(centerY * 100, bounds.y[0], bounds.y[1]),
				vx: randomSigned(0.2, 0.55),
				vy: randomSigned(0.15, 0.45),
				size: Math.max(rect.width, rect.height),
				color: color || "rgba(255,255,255,0.2)",
			};
		});

		lights.forEach((light) => {
			light.el.style.left = `${light.x.toFixed(2)}%`;
			light.el.style.top = `${light.y.toFixed(2)}%`;
		});

		let rafId = 0;
		let lastTime = 0;
		const tick = (time: number) => {
			if (!lastTime) {
				lastTime = time;
			}
			const dt = Math.min(32, time - lastTime) / 1000;
			lastTime = time;

			lights.forEach((light) => {
				light.vx = clamp(light.vx + randomSigned(0, 0.06) * dt, -0.8, 0.8);
				light.vy = clamp(light.vy + randomSigned(0, 0.05) * dt, -0.6, 0.6);
				light.x += light.vx * dt;
				light.y += light.vy * dt;

				if (light.x < bounds.x[0] || light.x > bounds.x[1]) {
					light.vx *= -1;
					light.x = clamp(light.x, bounds.x[0], bounds.x[1]);
				}
				if (light.y < bounds.y[0] || light.y > bounds.y[1]) {
					light.vy *= -1;
					light.y = clamp(light.y, bounds.y[0], bounds.y[1]);
				}

				light.el.style.left = `${light.x.toFixed(2)}%`;
				light.el.style.top = `${light.y.toFixed(2)}%`;
			});

			rafId = window.requestAnimationFrame(tick);
		};

		rafId = window.requestAnimationFrame(tick);

		let pulseIndex = 0;
		const assignPulse = (pulseEl: HTMLDivElement) => {
			const light = lights[pulseIndex % lights.length];
			pulseIndex += 1;
			if (!light) {
				return;
			}
			pulseEl.style.left = `${light.x.toFixed(2)}%`;
			pulseEl.style.top = `${light.y.toFixed(2)}%`;
			pulseEl.style.width = `${(light.size * 1.05).toFixed(0)}px`;
			pulseEl.style.height = `${(light.size * 1.05).toFixed(0)}px`;
			pulseEl.style.setProperty("--pulse-color", light.color);
		};

		const handleIteration = (event: AnimationEvent) => {
			const pulseEl = event.currentTarget as HTMLDivElement;
			assignPulse(pulseEl);
		};

		pulseEls.forEach((pulseEl) => {
			pulseEl.addEventListener("animationiteration", handleIteration);
		});

		return () => {
			window.cancelAnimationFrame(rafId);
			pulseEls.forEach((pulseEl) => {
				pulseEl.removeEventListener("animationiteration", handleIteration);
			});
		};
	}, []);

	return (
		<div ref={rootRef} className="forge-field absolute inset-0">
			<div className="forge-pulse-layer">
				<div className="forge-pulse forge-pulse-a" />
				<div className="forge-pulse forge-pulse-b" />
				<div className="forge-pulse forge-pulse-c" />
			</div>
			<div className="forge-light forge-light-a">
				<div className="forge-light-core" />
			</div>
			<div className="forge-light forge-light-b">
				<div className="forge-light-core" />
			</div>
			<div className="forge-light forge-light-c">
				<div className="forge-light-core" />
			</div>
			<div className="forge-light forge-light-d">
				<div className="forge-light-core" />
			</div>
			<div className="forge-light forge-light-e">
				<div className="forge-light-core" />
			</div>
		</div>
	);
}
