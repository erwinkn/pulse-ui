/** Clamp a value between min and max bounds. */
export function clamp(value: number, min: number, max: number): number {
	return Math.min(max, Math.max(min, value));
}
