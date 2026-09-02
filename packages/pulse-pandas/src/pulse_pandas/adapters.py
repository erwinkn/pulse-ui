from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from pandas.api.extensions import ExtensionArray
from pulse.serializer import SerializerAdapter

DataFrameOrient = Literal["records", "columns"]


def _unsupported(value: object, conversion: str) -> None:
	raise TypeError(
		f"{type(value).__name__} values are unsupported; pass {conversion}."
	)


def normalize_scalar(value: object) -> object:
	if value is None or value is pd.NA or value is pd.NaT:
		return None
	if type(value) is float and math.isnan(value):
		return None
	if isinstance(value, pd.Timedelta):
		_unsupported(value, "value.total_seconds() or a formatted string")
	if isinstance(value, np.timedelta64):
		_unsupported(value, "value.astype('timedelta64[s]') or a formatted string")
	if isinstance(value, pd.Period):
		_unsupported(value, "str(value)")
	if isinstance(value, pd.Interval):
		_unsupported(value, "str(value)")
	if isinstance(value, np.complexfloating):
		_unsupported(value, "a real component or a formatted string")
	if isinstance(value, pd.Timestamp):
		if value.microsecond % 1000 != 0 or value.nanosecond != 0:
			raise ValueError("Pandas timestamps must have exact millisecond precision")
		return value.to_pydatetime(warn=False)
	if isinstance(value, np.datetime64):
		return normalize_scalar(pd.Timestamp(value))
	if isinstance(value, np.generic):
		return normalize_scalar(value.item())
	return value


def _validate_columns(frame: pd.DataFrame) -> list[str]:
	columns = list(frame.columns)
	if not all(type(column) is str for column in columns):
		raise TypeError("DataFrame column names must be strings")
	if len(set(columns)) != len(columns):
		raise ValueError("DataFrame column names must be unique")
	return columns


def _serialize_dataframe(
	frame: pd.DataFrame,
	orient: DataFrameOrient,
) -> dict[str, object] | list[dict[str, object]]:
	columns = _validate_columns(frame)
	missing = frame.isna().to_numpy()
	cells = frame.to_numpy(dtype=object)
	rows: list[list[object]] = []
	for cell_row, missing_row in zip(cells, missing, strict=True):
		row: list[object] = []
		for value, is_missing in zip(cell_row, missing_row, strict=True):
			row.append(None if is_missing else normalize_scalar(value))
		rows.append(row)
	if orient == "records":
		return [dict(zip(columns, row, strict=True)) for row in rows]
	return {"columns": columns, "rows": rows}


def _serialize_series(series: pd.Series[Any]) -> list[object]:
	return [normalize_scalar(value) for value in series.tolist()]


def _serialize_index(index: pd.Index[Any]) -> list[object]:
	return [normalize_scalar(value) for value in index.tolist()]


def _serialize_array(array: np.ndarray[Any, Any]) -> object:
	return _normalize_nested(array.tolist())


def _normalize_nested(value: object) -> object:
	if isinstance(value, list):
		return [_normalize_nested(item) for item in value]
	if isinstance(value, tuple):
		return tuple(_normalize_nested(item) for item in value)
	return normalize_scalar(value)


def _serialize_extension_array(array: ExtensionArray) -> list[object]:
	return [normalize_scalar(value) for value in array.tolist()]


def _serialize_timestamp(value: pd.Timestamp) -> object:
	return normalize_scalar(value)


def _serialize_datetime64(value: np.datetime64) -> object:
	return normalize_scalar(value)


def _serialize_numpy_scalar(value: np.generic) -> object:
	return normalize_scalar(value)


def _serialize_missing(_: object) -> None:
	return None


def serializer_adapters(
	orient: DataFrameOrient,
) -> list[SerializerAdapter[Any]]:
	return [
		SerializerAdapter(
			pd.DataFrame,
			lambda frame: _serialize_dataframe(frame, orient),
		),
		SerializerAdapter(pd.Series, _serialize_series),
		SerializerAdapter(pd.Index, _serialize_index),
		SerializerAdapter(np.ndarray, _serialize_array),
		SerializerAdapter(ExtensionArray, _serialize_extension_array),
		SerializerAdapter(pd.Timestamp, _serialize_timestamp),
		SerializerAdapter(np.datetime64, _serialize_datetime64),
		SerializerAdapter(np.generic, _serialize_numpy_scalar),
		SerializerAdapter(type(pd.NaT), _serialize_missing),
		SerializerAdapter(type(pd.NA), _serialize_missing),
		SerializerAdapter(
			pd.Timedelta,
			lambda value: _unsupported(
				value, "value.total_seconds() or a formatted string"
			),
		),
		SerializerAdapter(
			np.timedelta64,
			lambda value: _unsupported(
				value, "value.astype('timedelta64[s]') or a formatted string"
			),
		),
		SerializerAdapter(pd.Period, lambda value: _unsupported(value, "str(value)")),
		SerializerAdapter(pd.Interval, lambda value: _unsupported(value, "str(value)")),
		SerializerAdapter(
			np.complexfloating,
			lambda value: _unsupported(value, "a real component or a formatted string"),
		),
	]
