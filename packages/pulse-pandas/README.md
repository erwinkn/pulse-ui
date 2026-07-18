# Pulse Pandas

Optional Pandas serialization adapters for Pulse.

```python
import pulse as ps
from pulse_pandas import dataframe_records_adapter

app = ps.App(
	serializer=ps.Serializer([dataframe_records_adapter]),
)
```

The adapter projects each `DataFrame` into ordered row records. It omits the
index, requires unique string column names, converts missing values to `None`,
and converts NumPy scalars to Python scalars. Other values continue through the
app's configured serializer.

`Series` and indexes are intentionally unsupported.
