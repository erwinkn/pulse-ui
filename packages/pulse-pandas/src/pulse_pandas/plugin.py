from __future__ import annotations

from typing import Literal

import pulse as ps
from pulse._serializer.types import SerializerAdapter

from pulse_pandas.adapters import DataFrameOrient, serializer_adapters


class PulsePandas(ps.Plugin):
	def __init__(
		self, *, dataframes: Literal["records", "columns"] = "records"
	) -> None:
		if dataframes not in ("records", "columns"):
			raise ValueError("dataframes must be 'records' or 'columns'")
		self.dataframes: DataFrameOrient = dataframes

	def serializer_adapters(self) -> list[SerializerAdapter[object]]:
		return serializer_adapters(self.dataframes)


__all__ = ["PulsePandas"]
