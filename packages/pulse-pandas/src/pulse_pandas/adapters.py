from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from pandas.api.extensions import ExtensionArray
from pulse.serializer import SerializerAdapter

DataFrameOrient = Literal["records", "columns"]
NaiveTimestamps = Literal["utc", "reject"]


def _unsupported(value: object, conversion: str) -> None:
	raise TypeError(
		f"{type(value).__name__} values are unsupported; pass {conversion}."
	)


def normalize_scalar(
	value: object,
	naive_timestamps: NaiveTimestamps = "utc",
) -> object:
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
		if value.tzinfo is None:
			if naive_timestamps == "reject":
				raise TypeError(
					"Naive pandas timestamps are unsupported; pass "
					'value.tz_localize("UTC") or '
					'.dt.tz_localize("UTC") for a Series column.'
				)
			value = value.tz_localize("UTC")
		if value.microsecond % 1000 != 0 or value.nanosecond != 0:
			raise ValueError("Pandas timestamps must have exact millisecond precision")
		return value.to_pydatetime(warn=False)
	if isinstance(value, np.datetime64):
		return normalize_scalar(pd.Timestamp(value), naive_timestamps)
	if isinstance(value, np.generic):
		return normalize_scalar(value.item(), naive_timestamps)
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
	naive_timestamps: NaiveTimestamps,
) -> dict[str, object] | list[dict[str, object]]:
	columns = _validate_columns(frame)
	missing = frame.isna().to_numpy()
	cells = frame.to_numpy(dtype=object)
	rows: list[list[object]] = []
	for cell_row, missing_row in zip(cells, missing, strict=True):
		row: list[object] = []
		for value, is_missing in zip(cell_row, missing_row, strict=True):
			row.append(
				None if is_missing else normalize_scalar(value, naive_timestamps)
			)
		rows.append(row)
	if orient == "records":
		return [dict(zip(columns, row, strict=True)) for row in rows]
	return {"columns": columns, "rows": rows}


def _serialize_series(
	series: pd.Series[Any],
	naive_timestamps: NaiveTimestamps,
) -> list[object]:
	return [normalize_scalar(value, naive_timestamps) for value in series.tolist()]


def _serialize_index(
	index: pd.Index[Any],
	naive_timestamps: NaiveTimestamps,
) -> list[object]:
	return [normalize_scalar(value, naive_timestamps) for value in index.tolist()]


def _serialize_array(
	array: np.ndarray[Any, Any],
	naive_timestamps: NaiveTimestamps,
) -> object:
	if array.ndim == 0:
		return normalize_scalar(array[()], naive_timestamps)
	if array.dtype.kind in "iufb":
		return array.tolist()
	return [
		_serialize_array(item, naive_timestamps)
		if isinstance(item, np.ndarray)
		else normalize_scalar(item, naive_timestamps)
		for item in array
	]


def _serialize_extension_array(
	array: ExtensionArray,
	naive_timestamps: NaiveTimestamps,
) -> list[object]:
	return [normalize_scalar(value, naive_timestamps) for value in array.tolist()]


def _serialize_missing(_: object) -> None:
	return None


def serializer_adapters(
	orient: DataFrameOrient,
	naive_timestamps: NaiveTimestamps,
) -> list[SerializerAdapter[Any]]:
	return [
		SerializerAdapter(
			type=pd.DataFrame,
			serialize=lambda frame: _serialize_dataframe(
				frame, orient, naive_timestamps
			),
		),
		SerializerAdapter(
			type=pd.Series,
			serialize=lambda series: _serialize_series(series, naive_timestamps),
		),
		SerializerAdapter(
			type=pd.Index,
			serialize=lambda index: _serialize_index(index, naive_timestamps),
		),
		SerializerAdapter(
			type=np.ndarray,
			serialize=lambda array: _serialize_array(array, naive_timestamps),
		),
		SerializerAdapter(
			type=ExtensionArray,
			serialize=lambda array: _serialize_extension_array(array, naive_timestamps),
		),
		SerializerAdapter(
			type=pd.Timestamp,
			serialize=lambda value: normalize_scalar(value, naive_timestamps),
		),
		SerializerAdapter(
			type=np.datetime64,
			serialize=lambda value: normalize_scalar(value, naive_timestamps),
		),
		SerializerAdapter(
			type=np.generic,
			serialize=lambda value: normalize_scalar(value, naive_timestamps),
		),
		SerializerAdapter(type=type(pd.NaT), serialize=_serialize_missing),
		SerializerAdapter(type=type(pd.NA), serialize=_serialize_missing),
		SerializerAdapter(
			type=pd.Timedelta,
			serialize=lambda value: _unsupported(
				value, "value.total_seconds() or a formatted string"
			),
		),
		SerializerAdapter(
			type=np.timedelta64,
			serialize=lambda value: _unsupported(
				value, "value.astype('timedelta64[s]') or a formatted string"
			),
		),
		SerializerAdapter(
			type=pd.Period,
			serialize=lambda value: _unsupported(value, "str(value)"),
		),
		SerializerAdapter(
			type=pd.Interval,
			serialize=lambda value: _unsupported(value, "str(value)"),
		),
		SerializerAdapter(
			type=np.complexfloating,
			serialize=lambda value: _unsupported(
				value, "a real component or a formatted string"
			),
		),
	]
