def square(x: float) -> float:
	"""Return the square of x."""
	return x * x


def cube(x: float) -> float:
	"""Return the cube of x."""
	return x * x * x


def factorial(n: int) -> int:
	"""Calculate factorial recursively."""
	if n <= 1:
		return 1
	return n * factorial(n - 1)


def is_even(n: int) -> bool:
	"""Check if n is even."""
	return n % 2 == 0


def clamp(value: float, min_val: float, max_val: float) -> float:
	"""Clamp value between min_val and max_val."""
	if value < min_val:
		return min_val
	if value > max_val:
		return max_val
	return value
