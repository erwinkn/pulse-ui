# Pulse Pandas

Optional Pandas and NumPy serialization support for Pulse.

```python
import pulse as ps
from pulse_pandas import PulsePandas

app = ps.App(
	plugins=[PulsePandas()],
)
```

`PulsePandas` projects Pandas and NumPy values into the Pulse wire format. The
projection is one-way: the browser receives regular JavaScript values and never
receives a `DataFrame`, `Series`, or other Pandas object back.

## DataFrame formats

DataFrames use records by default:

```python
app = ps.App(plugins=[PulsePandas()])
```

```json
[
	{"product": "Keyboard", "revenue": 1200},
	{"product": "Mouse", "revenue": 850}
]
```

Use columns when a compact, column-oriented payload is more efficient:

```python
app = ps.App(plugins=[PulsePandas(dataframes="columns")])
```

```json
{
	"columns": ["product", "revenue"],
	"rows": [["Keyboard", 1200], ["Mouse", 850]]
}
```

Both formats preserve column and row order and drop the DataFrame index. When
the index matters, pass `series.to_dict()` or an equivalent explicit mapping.
Column names must be unique strings, checked with exact `str` type semantics.

## Supported values

| Value | Wire projection |
|---|---|
| `pd.DataFrame` | Records by default, or `columns` format |
| `pd.Series` | List of values; index dropped |
| `pd.Index` | `tolist()`; includes `DatetimeIndex` and `MultiIndex` |
| `np.ndarray` | Lists, including nested and `datetime64` arrays |
| `ExtensionArray` | `tolist()`; includes categoricals and nullable arrays |
| `pd.Timestamp` | Timezone-aware Pulse timestamp after millisecond validation |
| `np.datetime64` | Timezone-aware Pandas timestamp projection |
| NumPy scalar | Python scalar via `.item()` |
| `pd.NaT`, `pd.NA`, `NaN` | `null` |

Missing values become `null`. Timestamps must be timezone-aware and use exact
millisecond precision. Infinity remains invalid under the core serializer.

## Rejected values

The following values have no duration or structured scalar representation on
the Pulse wire:

| Value | Suggested conversion |
|---|---|
| `pd.Timedelta`, `np.timedelta64` | `.total_seconds()` or a formatted string |
| `pd.Period` | `str(period)` |
| `pd.Interval` | `str(interval)` |
| NumPy complex scalar | A real component or a formatted string |
| Naive Pandas timestamps | `.tz_localize("UTC")` or `.dt.tz_localize("UTC")` |
