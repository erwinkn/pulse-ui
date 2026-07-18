import { deserialize, serialize } from "../src/serialize/serializer";

function fixtures(): Record<string, unknown> {
	const shared = { kind: "button", enabled: true };
	return {
		small_callback: {
			callback: "onClick",
			args: [{ clientX: 42, clientY: 18, button: 0 }],
		},
		vdom_71kb: {
			type: "main",
			props: { className: "dashboard" },
			children: Array.from({ length: 366 }, (_, index) => ({
				type: "article",
				key: `row-${index}`,
				props: {
					className: "card card--interactive",
					"data-index": index,
					"aria-label": `Open dashboard item ${index}`,
				},
				children: [`Item ${index}`, { type: "span", children: [index] }],
			})),
		},
		mixed_special: Array.from({ length: 800 }, (_, index) => ({
			at: new Date(Date.UTC(2026, 6, 16, 12, index % 60)),
			tags: new Set([`tag-${index % 7}`, index]),
			optional: index % 5 === 0 ? Number.NaN : null,
		})),
		references_3000: Array.from({ length: 3000 }, () => shared),
	};
}

function runSample(fn: () => unknown, iterations: number): number {
	const start = performance.now();
	for (let index = 0; index < iterations; index += 1) fn();
	return (performance.now() - start) / iterations;
}

function measure(fn: () => unknown): { median: number; cv: number } {
	for (let index = 0; index < 20; index += 1) fn();
	let iterations = 1;
	while (runSample(fn, iterations) * iterations < 100) iterations *= 2;

	let result = { median: 0, cv: Number.POSITIVE_INFINITY };
	for (let attempt = 0; attempt < 3 && result.cv > 0.05; attempt += 1) {
		const samples = Array.from({ length: 7 }, () => runSample(fn, iterations));
		samples.sort((left, right) => left - right);
		const mean = samples.reduce((sum, value) => sum + value, 0) / samples.length;
		const variance =
			samples.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
			(samples.length - 1);
		result = {
			median: samples[Math.floor(samples.length / 2)],
			cv: Math.sqrt(variance) / mean,
		};
	}
	return result;
}

for (const [name, value] of Object.entries(fixtures())) {
	const result = measure(() => deserialize(serialize(value)));
	const size = JSON.stringify(serialize(value)).length;
	console.log(
		`${name.padEnd(20)} ${result.median.toFixed(3)} ms  ` +
			`${size.toLocaleString("en-US")} bytes  CV ${(result.cv * 100).toFixed(1)}%`,
	);
}
