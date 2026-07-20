from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest
from pulse.serializer import Serializer, SerializerAdapter
from pulse_pandas import dataframe_adapter


def serialize(frame: pd.DataFrame) -> object:
	serializer = Serializer([dataframe_adapter])
	return serializer.deserialize(serializer.serialize(frame))


def test_dataframe_becomes_split_shape_without_index() -> None:
	frame = pd.DataFrame(
		{"name": ["Ada", "Grace"], "score": [np.int64(4), np.float64(5.5)]},
		index=[10, 20],
	)

	assert serialize(frame) == {
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

	assert serialize(frame) == {
		"columns": ["ready", "label"],
		"rows": [[True, "done"]],
	}


def test_dataframe_normalizes_all_missing_sentinels() -> None:
	frame = pd.DataFrame(
		{
			"none": [None],
			"nan": [float("nan")],
			"na": [pd.NA],
			"nat": [pd.NaT],
		}
	)

	assert serialize(frame) == {
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

	assert serialize(frame) == {
		"columns": ["timestamp", "date"],
		"rows": [
			[
				datetime(2026, 7, 16, 12, 30, tzinfo=timezone.utc),
				datetime(2026, 7, 16, tzinfo=timezone.utc),
			]
		],
	}


def test_dataframe_preserves_numeric_string_column_order() -> None:
	frame = pd.DataFrame(
		[["ten", "two", "Ada"]],
		columns=["10", "2", "name"],
	)

	result = serialize(frame)

	assert isinstance(result, dict)
	assert result["columns"] == ["10", "2", "name"]
	assert result["rows"] == [["ten", "two", "Ada"]]


@pytest.mark.parametrize("columns", [[1], ["value", "value"]])
def test_dataframe_rejects_invalid_columns(columns: list[object]) -> None:
	frame = pd.DataFrame([[1] * len(columns)], columns=columns)

	with pytest.raises((TypeError, ValueError)):
		serialize(frame)


def test_dataframe_rejects_string_subclass_columns() -> None:
	class Column(str):
		pass

	frame = pd.DataFrame([[1]], columns=[Column("value")])

	with pytest.raises(TypeError, match="column names must be strings"):
		serialize(frame)


def test_dataframe_infinity_is_rejected_by_core_serializer() -> None:
	frame = pd.DataFrame({"value": [float("inf")]})

	with pytest.raises(ValueError, match="finite"):
		serialize(frame)


def test_dataframe_rejects_sub_millisecond_timestamp() -> None:
	frame = pd.DataFrame({"at": [pd.Timestamp("2026-07-16T00:00:00.000000001Z")]})

	with pytest.raises(ValueError, match="millisecond"):
		serialize(frame)


def test_dataframe_values_continue_through_other_adapters() -> None:
	class Label:
		def __init__(self, value: str) -> None:
			self.value: str = value

	frame = pd.DataFrame({"label": [Label("ready")]})
	serializer = Serializer(
		[
			dataframe_adapter,
			SerializerAdapter(type=Label, serialize=lambda label: label.value),
		]
	)

	assert serializer.deserialize(serializer.serialize(frame)) == {
		"columns": ["label"],
		"rows": [["ready"]],
	}
