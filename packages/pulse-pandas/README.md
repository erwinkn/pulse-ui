# Pulse Pandas

Optional Pandas serialization adapters for Pulse.

```python
import pulse as ps
from pulse_pandas import dataframe_adapter

app = ps.App(
	serializer=ps.Serializer([dataframe_adapter]),
)
```

The adapter projects each `DataFrame` into an ordered `columns` list and `rows`
arrays. It omits the index, requires unique string column names, converts missing
values to `None`, and converts NumPy scalars to Python scalars. Other values
continue through the app's configured serializer.

`Series` and indexes are intentionally unsupported.
