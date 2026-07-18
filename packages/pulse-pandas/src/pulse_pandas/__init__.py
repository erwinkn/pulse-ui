from typing import cast

import numpy as np
import pandas as pd
from pulse.serializer import SerializerAdapter


def _python_scalar(value: object) -> object:
	if isinstance(value, pd.Timestamp):
		if value.microsecond % 1000 != 0 or value.nanosecond != 0:
			raise ValueError("Pandas timestamps must have exact millisecond precision")
		return value.to_pydatetime(warn=False)
	if isinstance(value, np.generic):
		return value.item()
	return value


def _serialize_dataframe(frame: pd.DataFrame) -> list[dict[str, object]]:
	columns = list(frame.columns)
	if not all(type(column) is str for column in columns):
		raise TypeError("DataFrame column names must be strings")
	if len(set(columns)) != len(columns):
		raise ValueError("DataFrame column names must be unique")

	missing = frame.isna()
	rows = cast(list[dict[str, object]], frame.to_dict(orient="records"))
	for row_index, row in enumerate(rows):
		for column_index, column in enumerate(columns):
			if missing.iat[row_index, column_index]:
				row[column] = None
			else:
				row[column] = _python_scalar(row[column])
	return rows


dataframe_records_adapter = SerializerAdapter(
	type=pd.DataFrame,
	serialize=_serialize_dataframe,
)

__all__ = ["dataframe_records_adapter"]
