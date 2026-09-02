from __future__ import annotations

from typing import Any, Literal, override

import pulse as ps

from pulse_pandas.adapters import DataFrameOrient, serializer_adapters


class PulsePandas(ps.Plugin):
	"""Serialize Pandas and NumPy values for Pulse applications."""

	def __init__(
		self, *, dataframes: Literal["records", "columns"] = "records"
	) -> None:
		if dataframes not in ("records", "columns"):
			raise ValueError("dataframes must be 'records' or 'columns'")
		self.dataframes: DataFrameOrient = dataframes

	@override
	def serializer_adapters(self) -> list[ps.SerializerAdapter[Any]]:
		return serializer_adapters(self.dataframes)


__all__ = ["PulsePandas"]
