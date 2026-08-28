import numpy as np
import pandas as pd
from pulse.serializer import SerializerAdapter


def _serialize_dataframe(frame: pd.DataFrame) -> dict[str, object]:
	columns = list(frame.columns)
	if not all(type(column) is str for column in columns):
		raise TypeError("DataFrame column names must be strings")
	if len(set(columns)) != len(columns):
		raise ValueError("DataFrame column names must be unique")

	# Bulk-extract cells; per-cell .iat indexing is microseconds per call and
	# blocks the event loop for grid-sized frames.
	missing = frame.isna().to_numpy()
	cells = frame.to_numpy(dtype=object)
	rows: list[list[object]] = []
	for cell_row, missing_row in zip(cells, missing, strict=True):
		row: list[object] = []
		for value, is_missing in zip(cell_row, missing_row, strict=True):
			if is_missing:
				row.append(None)
				continue
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
