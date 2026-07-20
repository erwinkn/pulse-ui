import numpy as np
import pandas as pd
from pulse.serializer import SerializerAdapter


def _serialize_dataframe(frame: pd.DataFrame) -> dict[str, object]:
	columns = list(frame.columns)
	if not all(type(column) is str for column in columns):
		raise TypeError("DataFrame column names must be strings")
	if len(set(columns)) != len(columns):
		raise ValueError("DataFrame column names must be unique")

	missing = frame.isna()
	rows: list[list[object]] = []
	for row_index in range(len(frame.index)):
		row: list[object] = []
		for column_index in range(len(columns)):
			if missing.iat[row_index, column_index]:
				row.append(None)
				continue
			value = frame.iat[row_index, column_index]
			if isinstance(value, pd.Timestamp):
				if value.microsecond % 1000 != 0 or value.nanosecond != 0:
					raise ValueError(
						"Pandas timestamps must have exact millisecond precision"
					)
				value = value.to_pydatetime(warn=False)
			elif isinstance(value, np.generic):
				value = value.item()
			row.append(value)
		rows.append(row)
	return {"columns": columns, "rows": rows}


dataframe_adapter = SerializerAdapter(
	type=pd.DataFrame,
	serialize=_serialize_dataframe,
)

__all__ = ["dataframe_adapter"]
