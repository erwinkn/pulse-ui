#!/usr/bin/env python3
"""
Run basedpyright --stats on various subsets of the codebase and output results.

Usage:
    uv run scripts/typecheck_stats.py           # Quick summary
    uv run scripts/typecheck_stats.py --deep    # Per-file analysis (slower)
"""

import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "profiling"

# Define subsets to check
SUBSETS = {
	"full": [],  # Empty means use pyrightconfig.json defaults
	"pulse-core": ["packages/pulse/python/src"],
	"pulse-tests": ["packages/pulse/python/tests"],
	"pulse-mantine": ["packages/pulse-mantine/python/src"],
	"pulse-recharts": ["packages/pulse-recharts/src"],
	"pulse-aws": ["packages/pulse-aws/src"],
	"pulse-lucide": ["packages/pulse-lucide/src"],
	"pulse-ag-grid": ["packages/pulse-ag-grid/src"],
	"pulse-msal": ["packages/pulse-msal/src"],
}

# Directories to analyze per-file
DEEP_ANALYZE_DIRS = [
	"packages/pulse/python/src",
	"packages/pulse/python/tests",
	"packages/pulse-mantine/python/src",
]


def run_pyright(paths: list[str]) -> str:
	"""Run basedpyright --stats and return output."""
	cmd = ["uv", "run", "basedpyright", "--stats", *paths]
	result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
	return result.stdout + result.stderr


def parse_timing(output: str) -> dict[str, float]:
	"""Extract timing stats from output as floats."""
	timing = {}
	in_timing = False
	for line in output.splitlines():
		if "Timing stats" in line:
			in_timing = True
			continue
		if in_timing and ":" in line:
			key, value = line.split(":", 1)
			# Parse "0.21sec" -> 0.21
			match = re.search(r"([\d.]+)sec", value)
			if match:
				timing[key.strip()] = float(match.group(1))
	return timing


def get_file_stats(filepath: str) -> tuple[str, dict[str, float]]:
	"""Get stats for a single file."""
	output = run_pyright([filepath])
	return filepath, parse_timing(output)


def analyze_directory_files(directory: str) -> list[tuple[str, dict[str, float]]]:
	"""Analyze all Python files in a directory."""
	dir_path = ROOT / directory
	files = list(dir_path.rglob("*.py"))
	results = []

	print(f"\n  Analyzing {len(files)} files in {directory}...")

	with ThreadPoolExecutor(max_workers=8) as executor:
		futures = {
			executor.submit(get_file_stats, str(f.relative_to(ROOT))): f for f in files
		}
		done = 0
		for future in as_completed(futures):
			done += 1
			if done % 20 == 0:
				print(f"    {done}/{len(files)} files analyzed...")
			filepath, timing = future.result()
			results.append((filepath, timing))

	return results


def main() -> None:
	deep_mode = "--deep" in sys.argv

	OUTPUT_DIR.mkdir(exist_ok=True)
	timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	suffix = "_deep" if deep_mode else ""
	output_file = OUTPUT_DIR / f"stats_{timestamp}{suffix}.txt"

	results: list[str] = []
	results.append(f"Typecheck Stats - {datetime.now().isoformat()}")
	results.append("=" * 60)

	# Run on subsets
	print("Running basedpyright on subsets...")
	for name, paths in SUBSETS.items():
		print(f"  {name}...", end=" ", flush=True)
		output = run_pyright(paths)
		timing = parse_timing(output)
		check_time = timing.get("Check", 0)
		total_line = next(
			(line for line in output.splitlines() if "Completed in" in line), ""
		)
		print(f"Check: {check_time:.2f}sec")

		results.append(f"\n## {name}")
		results.append(f"Paths: {paths or '(pyrightconfig.json defaults)'}")
		results.append(f"Check time: {check_time:.2f}sec")
		results.append(f"{total_line}")
		results.append("\nFull timing:")
		for k, v in timing.items():
			results.append(f"  {k}: {v:.2f}sec")

	if deep_mode:
		results.append("\n" + "=" * 60)
		results.append("PER-FILE ANALYSIS (sorted by Check time)")
		results.append("=" * 60)

		all_file_stats: list[tuple[str, dict[str, float]]] = []

		for directory in DEEP_ANALYZE_DIRS:
			file_stats = analyze_directory_files(directory)
			all_file_stats.extend(file_stats)

		# Sort by check time descending
		all_file_stats.sort(key=lambda x: x[1].get("Check", 0), reverse=True)

		results.append("\n### Top 50 Slowest Files by Check Time\n")
		results.append(f"{'File':<70} {'Check':>8} {'Bind':>8} {'Parse':>8}")
		results.append("-" * 100)

		for filepath, timing in all_file_stats[:50]:
			check = timing.get("Check", 0)
			bind = timing.get("Bind", 0)
			parse = timing.get("Parse", 0)
			results.append(
				f"{filepath:<70} {check:>7.2f}s {bind:>7.2f}s {parse:>7.2f}s"
			)

		# Summary stats
		results.append("\n### Summary Statistics\n")
		check_times = [t.get("Check", 0) for _, t in all_file_stats]
		bind_times = [t.get("Bind", 0) for _, t in all_file_stats]

		results.append(f"Total files analyzed: {len(all_file_stats)}")
		results.append(f"Sum of all Check times: {sum(check_times):.2f}sec")
		results.append(f"Sum of all Bind times: {sum(bind_times):.2f}sec")
		results.append(f"Max Check time: {max(check_times):.2f}sec")
		results.append(
			f"Median Check time: {sorted(check_times)[len(check_times) // 2]:.2f}sec"
		)

		# Files with check time > 0.1s
		slow_files = [(f, t) for f, t in all_file_stats if t.get("Check", 0) > 0.1]
		results.append(f"\nFiles with Check > 0.1sec: {len(slow_files)}")
		results.append(
			f"Their total Check time: {sum(t.get('Check', 0) for _, t in slow_files):.2f}sec"
		)

		# Group by directory
		results.append("\n### Check Time by Directory\n")
		dir_times: dict[str, float] = {}
		for filepath, timing in all_file_stats:
			parts = filepath.split("/")
			if len(parts) >= 5:
				# Get up to the 5th level (e.g., packages/pulse/python/src/pulse)
				dir_key = "/".join(parts[:5])
			else:
				dir_key = "/".join(parts[:-1])
			dir_times[dir_key] = dir_times.get(dir_key, 0) + timing.get("Check", 0)

		for dir_name, total in sorted(dir_times.items(), key=lambda x: -x[1]):
			results.append(f"  {dir_name}: {total:.2f}sec")

	# Write results
	output_file.write_text("\n".join(results))
	print(f"\nResults written to: {output_file}")

	# Also write a latest symlink/copy
	latest = OUTPUT_DIR / f"latest{suffix}.txt"
	latest.write_text("\n".join(results))
	print(f"Latest results: {latest}")


if __name__ == "__main__":
	sys.exit(main() or 0)
