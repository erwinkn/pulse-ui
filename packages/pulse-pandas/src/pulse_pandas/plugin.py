from __future__ import annotations

from typing import Any, Literal, override

import pulse as ps

from pulse_pandas.adapters import DataFrameOrient, NaiveTimestamps, serializer_adapters


class PulsePandas(ps.Plugin):
	"""Serialize Pandas and NumPy values for Pulse applications."""

	def __init__(
		self,
		*,
		dataframes: Literal["records", "columns"] = "records",
		naive_timestamps: Literal["utc", "reject"] = "utc",
	) -> None:
		if dataframes not in ("records", "columns"):
			raise ValueError("dataframes must be 'records' or 'columns'")
		if naive_timestamps not in ("utc", "reject"):
			raise ValueError("naive_timestamps must be 'utc' or 'reject'")
		self.dataframes: DataFrameOrient = dataframes
		self.naive_timestamps: NaiveTimestamps = naive_timestamps

	@override
	def serializer_adapters(self) -> list[ps.SerializerAdapter[Any]]:
		return serializer_adapters(self.dataframes, self.naive_timestamps)


__all__ = ["PulsePandas"]
