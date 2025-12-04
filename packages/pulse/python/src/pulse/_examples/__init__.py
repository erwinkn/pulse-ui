"""Example helper module for demonstrating cross-module transpilation."""

from __future__ import annotations

# =============================================================================
# Helper functions that can be imported and used in transpiled functions
# =============================================================================


def square(x: float) -> float:
	"""Square a number. This function will be auto-transpiled when used."""
	return x**2


def cube(x: float) -> float:
	"""Cube a number. This function will be auto-transpiled when used."""
	return x * x * x


def clamp(value: float, min_val: float, max_val: float) -> float:
	"""Clamp a value between min and max."""
	if value < min_val:
		return min_val
	if value > max_val:
		return max_val
	return value


def is_even(n: int) -> bool:
	"""Check if a number is even."""
	return n % 2 == 0


def factorial(n: int) -> int:
	"""Calculate factorial iteratively."""
	result = 1
	for i in range(1, n + 1):
		result = result * i
	return result
