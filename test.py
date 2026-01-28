from typing import TypeVar

T = TypeVar("T")


type QP[T] = T


def test(x: QP[int]):
	return x + 3
