export type CurveType =
	| "linear"
	| "ease-in"
	| "ease-out"
	| "ease-in-out"
	| "sine-in"
	| "sine-out"
	| "sine-in-out"
	| "expo-in"
	| "expo-out"
	| "expo-in-out";

export type Stop = {
	offset: number;
	opacity: number;
};

export const clamp = (value: number, min: number, max: number) =>
	Math.min(max, Math.max(min, value));

export const curveValue = (curve: CurveType, power: number, t: number) => {
	switch (curve) {
		case "ease-in":
			return t ** power;
		case "ease-out":
			return 1 - (1 - t) ** power;
		case "ease-in-out":
			if (t < 0.5) return 0.5 * (2 * t) ** power;
			return 1 - 0.5 * (2 * (1 - t)) ** power;
		case "sine-in":
			return 1 - Math.cos((t * Math.PI) / 2);
		case "sine-out":
			return Math.sin((t * Math.PI) / 2);
		case "sine-in-out":
			return -(Math.cos(Math.PI * t) - 1) / 2;
		case "expo-in":
			return t === 0 ? 0 : 2 ** (10 * (t - 1));
		case "expo-out":
			return t === 1 ? 1 : 1 - 2 ** (-10 * t);
		case "expo-in-out":
			if (t === 0 || t === 1) return t;
			if (t < 0.5) return 2 ** (20 * t - 10) / 2;
			return (2 - 2 ** (-20 * t + 10)) / 2;
		case "linear":
		default:
			return t;
	}
};

export const hexToRgb = (hex: string) => {
	const normalized = hex.replace("#", "");
	if (normalized.length !== 6) return { r: 31, g: 75, b: 255 };
	const r = Number.parseInt(normalized.slice(0, 2), 16);
	const g = Number.parseInt(normalized.slice(2, 4), 16);
	const b = Number.parseInt(normalized.slice(4, 6), 16);
	return { r, g, b };
};

export const formatNumber = (value: number, digits = 2) => {
	const fixed = value.toFixed(digits);
	return fixed.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
};

export const buildStops = ({
	flatPercent,
	fadeEndPercent,
	peakOpacity,
	stopCount,
	curve,
	curvePower,
}: {
	flatPercent: number;
	fadeEndPercent: number;
	peakOpacity: number;
	stopCount: number;
	curve: CurveType;
	curvePower: number;
}): Stop[] => {
	const fadeStops = Math.max(2, stopCount - 1);
	const addExtra = flatPercent === 0 ? 1 : 0;
	const totalFadeStops = fadeStops + addExtra;
	const results: Stop[] = [{ offset: 0, opacity: peakOpacity }];
	const startIndex = flatPercent === 0 ? 1 : 0;
	for (let i = startIndex; i < totalFadeStops; i += 1) {
		const t = totalFadeStops === 1 ? 1 : i / (totalFadeStops - 1);
		const eased = curveValue(curve, curvePower, t);
		const opacity = peakOpacity * (1 - eased);
		const offset = flatPercent + t * (fadeEndPercent - flatPercent);
		results.push({ offset, opacity });
	}
	if (fadeEndPercent < 100) {
		results.push({ offset: 100, opacity: 0 });
	}
	return results;
};
