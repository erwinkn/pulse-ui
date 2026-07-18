from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from datetime import datetime, timezone

from pulse.serializer import deserialize, serialize


def fixtures() -> dict[str, object]:
	shared = {"kind": "button", "enabled": True}
	return {
		"small_callback": {
			"callback": "onClick",
			"args": [{"clientX": 42, "clientY": 18, "button": 0}],
		},
		"vdom_71kb": {
			"type": "main",
			"props": {"className": "dashboard"},
			"children": [
				{
					"type": "article",
					"key": f"row-{index}",
					"props": {
						"className": "card card--interactive",
						"data-index": index,
						"aria-label": f"Open dashboard item {index}",
					},
					"children": [
						f"Item {index}",
						{"type": "span", "children": [index]},
					],
				}
				for index in range(366)
			],
		},
		"mixed_special": [
			{
				"at": datetime(2026, 7, 16, 12, index % 60, tzinfo=timezone.utc),
				"tags": {f"tag-{index % 7}", index},
				"optional": float("nan") if index % 5 == 0 else None,
			}
			for index in range(800)
		],
		"references_3000": [shared for _ in range(3000)],
	}


def run_sample(function: Callable[[], object], iterations: int) -> float:
	start = time.perf_counter()
	for _ in range(iterations):
		function()
	return (time.perf_counter() - start) / iterations


def measure(function: Callable[[], object]) -> tuple[float, float]:
	for _ in range(20):
		function()
	iterations = 1
	while run_sample(function, iterations) * iterations < 0.1:
		iterations *= 2

	median = 0.0
	cv = float("inf")
	for _ in range(3):
		samples = [run_sample(function, iterations) for _ in range(7)]
		median = statistics.median(samples)
		cv = statistics.stdev(samples) / statistics.mean(samples)
		if cv <= 0.05:
			break
	return median, cv


def main() -> None:
	for name, value in fixtures().items():
		median, cv = measure(lambda value=value: deserialize(serialize(value)))
		size = len(json.dumps(serialize(value), separators=(",", ":")))
		print(f"{name:20} {median * 1000:.3f} ms  {size:,} bytes  CV {cv:.1%}")


if __name__ == "__main__":
	main()
