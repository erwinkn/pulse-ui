from datetime import date, datetime, timezone
from re import escape

import numpy as np
import pandas as pd
import pytest
from pulse.serializer import Serializer, SerializerAdapter
from pulse_pandas import PulsePandas
from pulse_pandas.adapters import DataFrameOrient, NaiveTimestamps


def serializer(
	orient: DataFrameOrient = "records",
	naive_timestamps: NaiveTimestamps = "utc",
) -> Serializer:
	return Serializer(
		PulsePandas(
			dataframes=orient,
			naive_timestamps=naive_timestamps,
		).serializer_adapters()
	)


def roundtrip(
	value: object,
	orient: DataFrameOrient = "records",
	naive_timestamps: NaiveTimestamps = "utc",
) -> object:
	serializer_instance = serializer(orient, naive_timestamps)
	return serializer_instance.deserialize(serializer_instance.serialize(value))


def test_dataframe_defaults_to_records_without_index() -> None:
	frame = pd.DataFrame(
		{"name": ["Ada", "Grace"], "score": [np.int64(4), np.float64(5.5)]},
		index=[10, 20],
	)

	assert roundtrip(frame) == [
		{"name": "Ada", "score": 4},
		{"name": "Grace", "score": 5.5},
	]


def test_dataframe_columns_orient_preserves_existing_shape() -> None:
	frame = pd.DataFrame(
		{"name": ["Ada", "Grace"], "score": [np.int64(4), np.float64(5.5)]},
		index=[10, 20],
	)

	assert roundtrip(frame, "columns") == {
		"columns": ["name", "score"],
		"rows": [["Ada", 4], ["Grace", 5.5]],
	}


def test_dataframe_converts_numpy_boolean_and_string_scalars() -> None:
	frame = pd.DataFrame(
		{
			"ready": pd.Series([np.bool_(True)], dtype=object),
			"label": pd.Series([np.str_("done")], dtype=object),
		}
	)

	assert roundtrip(frame, "columns") == {
		"columns": ["ready", "label"],
		"rows": [[True, "done"]],
	}


def test_dataframe_normalizes_all_missing_sentinels() -> None:
	frame = pd.DataFrame(
		{"none": [None], "nan": [float("nan")], "na": [pd.NA], "nat": [pd.NaT]}
	)

	assert roundtrip(frame, "columns") == {
		"columns": ["none", "nan", "na", "nat"],
		"rows": [[None, None, None, None]],
	}


def test_dataframe_temporal_values_follow_core_convention() -> None:
	frame = pd.DataFrame(
		{
			"timestamp": [pd.Timestamp("2026-07-16T12:30:00Z")],
			"date": [date(2026, 7, 16)],
		}
	)

	assert roundtrip(frame, "columns") == {
		"columns": ["timestamp", "date"],
		"rows": [
			[
				datetime(2026, 7, 16, 12, 30, tzinfo=timezone.utc),
				datetime(2026, 7, 16, tzinfo=timezone.utc),
			]
		],
	}


def test_dataframe_preserves_numeric_string_column_order() -> None:
	frame = pd.DataFrame([["ten", "two", "Ada"]], columns=["10", "2", "name"])

	result = roundtrip(frame, "columns")

	assert isinstance(result, dict)
	assert result["columns"] == ["10", "2", "name"]
	assert result["rows"] == [["ten", "two", "Ada"]]


@pytest.mark.parametrize("orient", ["records", "columns"])
@pytest.mark.parametrize("columns", [[1], ["value", "value"]])
def test_dataframe_rejects_invalid_columns(
	orient: DataFrameOrient, columns: list[object]
) -> None:
	frame = pd.DataFrame([[1] * len(columns)], columns=columns)

	with pytest.raises((TypeError, ValueError)):
		roundtrip(frame, orient)


@pytest.mark.parametrize("orient", ["records", "columns"])
def test_dataframe_rejects_string_subclass_columns(orient: DataFrameOrient) -> None:
	class Column(str):
		pass

	frame = pd.DataFrame([[1]], columns=[Column("value")])

	with pytest.raises(TypeError, match="column names must be strings"):
		roundtrip(frame, orient)


def test_dataframe_infinity_is_rejected_by_core_serializer() -> None:
	frame = pd.DataFrame({"value": [float("inf")]})

	with pytest.raises(ValueError, match="finite"):
		roundtrip(frame, "columns")


def test_dataframe_rejects_sub_millisecond_timestamp() -> None:
	frame = pd.DataFrame({"at": [pd.Timestamp("2026-07-16T00:00:00.000000001Z")]})

	with pytest.raises(ValueError, match="millisecond"):
		roundtrip(frame, "columns")


def test_dataframe_values_continue_through_other_adapters() -> None:
	class Label:
		def __init__(self, value: str) -> None:
			self.value = value

	serializer_instance = serializer("columns").with_adapters(
		[SerializerAdapter(Label, lambda label: label.value)]
	)
	frame = pd.DataFrame({"label": [Label("ready")]})

	assert serializer_instance.deserialize(serializer_instance.serialize(frame)) == {
		"columns": ["label"],
		"rows": [["ready"]],
	}


def test_series_drops_index_and_normalizes_values() -> None:
	series = pd.Series([np.int64(3), pd.NA], index=["a", "b"], dtype="Int64")

	assert roundtrip(series) == [3, None]


def test_index_uses_values_and_drops_index_metadata() -> None:
	index = pd.DatetimeIndex(["2026-01-01T00:00:00Z"])

	assert roundtrip(index) == [datetime(2026, 1, 1, tzinfo=timezone.utc)]


def test_multi_index_projects_tuples_to_wire_arrays() -> None:
	index = pd.MultiIndex.from_tuples([("a", 1), ("b", 2)])

	assert roundtrip(index) == [["a", 1], ["b", 2]]


def test_ndarray_projects_nested_lists() -> None:
	array = np.array([[1, 2], [3, 4]], dtype=np.int64)

	assert roundtrip(array) == [[1, 2], [3, 4]]


def test_ndarray_normalizes_missing_values() -> None:
	array = np.array([[1.0, np.nan], [3.0, 4.0]])

	assert roundtrip(array) == [[1.0, None], [3.0, 4.0]]


def test_float_ndarray_fast_path_normalizes_nan_in_core_encoder() -> None:
	array = np.array([1.0, np.nan])

	assert roundtrip(array) == [1.0, None]


@pytest.mark.parametrize("unit", ["ns", "us"])
@pytest.mark.parametrize("naive_timestamps", ["reject"])
def test_datetime64_array_uses_timestamp_normalization(
	unit: str,
	naive_timestamps: NaiveTimestamps,
) -> None:
	array = np.array(["2026-01-01"], dtype=f"datetime64[{unit}]")

	with pytest.raises(TypeError, match="tz_localize"):
		roundtrip(array, naive_timestamps=naive_timestamps)


def test_tz_aware_datetime_object_array_roundtrips() -> None:
	array = np.array(
		[pd.Timestamp("2026-01-01T00:00:00Z")],
		dtype=object,
	)

	assert roundtrip(array) == [datetime(2026, 1, 1, tzinfo=timezone.utc)]


@pytest.mark.parametrize("naive_timestamps", ["reject"])
def test_2d_datetime64_array_uses_timestamp_normalization(
	naive_timestamps: NaiveTimestamps,
) -> None:
	array = np.array([["2026-01-01"]], dtype="datetime64[ns]")

	with pytest.raises(TypeError, match="tz_localize"):
		roundtrip(array, naive_timestamps=naive_timestamps)


def test_timedelta64_array_has_actionable_error() -> None:
	array = np.array([1], dtype="timedelta64[s]")

	with pytest.raises(TypeError, match="formatted string"):
		roundtrip(array)


def test_complex_array_has_actionable_error() -> None:
	array = np.array([1 + 2j])

	with pytest.raises(TypeError, match="real component"):
		roundtrip(array)


def test_categorical_extension_array_preserves_missing_values() -> None:
	array = pd.Categorical(["ready", None], categories=["ready", "waiting"])

	assert roundtrip(array) == ["ready", None]


@pytest.mark.parametrize(
	"array",
	[
		pd.array([1, None], dtype="Int64"),
		pd.array(["ready", None], dtype="string"),
	],
)
def test_extension_arrays_preserve_missing_values(array: object) -> None:
	assert roundtrip(array) == [array[0], None]  # type: ignore[index]


@pytest.mark.parametrize(
	"value",
	[
		pd.Timestamp("2026-01-01T00:00:00Z"),
		pd.Timestamp("2026-01-01T00:00:00"),
	],
)
@pytest.mark.parametrize("naive_timestamps", ["reject"])
def test_timestamp_adapter_supports_tz_aware_and_rejects_naive(
	value: pd.Timestamp,
	naive_timestamps: NaiveTimestamps,
) -> None:
	if value.tzinfo is None:
		with pytest.raises(TypeError, match="tz_localize"):
			roundtrip(value, naive_timestamps=naive_timestamps)
	else:
		assert roundtrip(value, naive_timestamps=naive_timestamps) == datetime(
			2026, 1, 1, tzinfo=timezone.utc
		)


@pytest.mark.parametrize(
	"value",
	[
		pd.Timestamp("2026-01-01"),
		pd.Series(pd.date_range("2026-01-01", periods=1)),
		pd.DatetimeIndex(pd.date_range("2026-01-01", periods=1)),
	],
)
@pytest.mark.parametrize("naive_timestamps", ["reject"])
def test_naive_timestamps_have_actionable_error(
	value: object,
	naive_timestamps: NaiveTimestamps,
) -> None:
	with pytest.raises(TypeError, match="tz_localize"):
		roundtrip(value, naive_timestamps=naive_timestamps)


@pytest.mark.parametrize("orient", ["records", "columns"])
@pytest.mark.parametrize("naive_timestamps", ["reject"])
def test_naive_dataframe_timestamps_have_actionable_error(
	orient: DataFrameOrient,
	naive_timestamps: NaiveTimestamps,
) -> None:
	frame = pd.DataFrame({"at": pd.date_range("2026-01-01", periods=1)})

	with pytest.raises(TypeError, match="tz_localize"):
		roundtrip(frame, orient, naive_timestamps)


def test_naive_timestamp_defaults_to_utc() -> None:
	assert roundtrip(pd.Timestamp("2026-01-01")) == datetime(
		2026, 1, 1, tzinfo=timezone.utc
	)


def test_numpy_datetime64_defaults_to_utc() -> None:
	assert roundtrip(np.datetime64("2026-01-01")) == datetime(
		2026, 1, 1, tzinfo=timezone.utc
	)


def test_numpy_datetime64_reject_mode_has_actionable_error() -> None:
	with pytest.raises(TypeError, match="tz_localize"):
		roundtrip(np.datetime64("2026-01-01"), naive_timestamps="reject")


def test_naive_series_defaults_to_utc() -> None:
	series = pd.Series(pd.date_range("2026-01-01", periods=1))

	assert roundtrip(series) == [datetime(2026, 1, 1, tzinfo=timezone.utc)]


def test_naive_index_defaults_to_utc() -> None:
	index = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=1))

	assert roundtrip(index) == [datetime(2026, 1, 1, tzinfo=timezone.utc)]


@pytest.mark.parametrize("orient", ["records", "columns"])
def test_naive_dataframe_defaults_to_utc(orient: DataFrameOrient) -> None:
	frame = pd.DataFrame({"at": pd.date_range("2026-01-01", periods=1)})

	if orient == "records":
		expected: object = [{"at": datetime(2026, 1, 1, tzinfo=timezone.utc)}]
	else:
		expected = {
			"columns": ["at"],
			"rows": [[datetime(2026, 1, 1, tzinfo=timezone.utc)]],
		}

	assert roundtrip(frame, orient) == expected


@pytest.mark.parametrize("unit", ["ns", "us"])
def test_naive_datetime64_array_defaults_to_utc(unit: str) -> None:
	array = np.array(["2026-01-01"], dtype=f"datetime64[{unit}]")

	assert roundtrip(array) == [datetime(2026, 1, 1, tzinfo=timezone.utc)]


@pytest.mark.parametrize(
	"array",
	[
		np.array([["2026-01-01"]], dtype="datetime64[ns]"),
		np.array([["2026-01-01"]], dtype="datetime64[us]"),
	],
)
def test_naive_2d_datetime64_array_defaults_to_utc(array: np.ndarray) -> None:
	assert roundtrip(array) == [[datetime(2026, 1, 1, tzinfo=timezone.utc)]]


def test_naive_sub_millisecond_timestamp_still_rejects_precision() -> None:
	with pytest.raises(ValueError, match="millisecond"):
		roundtrip(pd.Timestamp("2026-01-01T00:00:00.000000001"))


@pytest.mark.parametrize(
	"value",
	[
		np.int64(3),
		np.uint8(4),
		np.float32(1.5),
		np.float64(2.5),
		np.bool_(True),
		np.str_("ready"),
	],
)
def test_numpy_scalar_families_project_to_python_values(value: np.generic) -> None:
	assert roundtrip(value) == value.item()


def test_numpy_nan_projects_to_null() -> None:
	assert roundtrip(np.float64("nan")) is None


@pytest.mark.parametrize(
	"value_and_message",
	[
		(pd.Timedelta(seconds=2), "total_seconds"),
		(np.timedelta64(2, "s"), "formatted string"),
		(pd.Period("2026-01"), "str(value)"),
		(pd.Interval(1, 2), "str(value)"),
		(np.complex128(1 + 2j), "real component"),
	],
)
def test_unsupported_pandas_values_have_actionable_errors(
	value_and_message: tuple[object, str],
) -> None:
	value, message = value_and_message

	with pytest.raises(TypeError, match=escape(message)):
		roundtrip(value)


def test_pulse_pandas_plugin_registers_frames_and_numpy_scalars() -> None:
	from pulse import App, Route

	frame = pd.DataFrame({"value": [1]})
	app = App(routes=[Route("/", render=lambda: None)], plugins=[PulsePandas()])

	assert app.serializer.deserialize(app.serializer.serialize(frame)) == [{"value": 1}]
	assert app.serializer.deserialize(app.serializer.serialize(np.float64(1.5))) == 1.5
