import pandas as pd
import pulse as ps
from pulse.js.react import lazy
from pulse_pandas import dataframe_records_adapter


@ps.react_component(lazy(ps.Import("~/components/data-table", lazy=True)))
def DataTable(*, rows: object): ...


@ps.component
def DataFrameGrid():
	frame = pd.DataFrame(
		{
			"product": ["Keyboard", "Mouse"],
			"revenue": [1200, 850],
			"note": [None, pd.NA],
		}
	)
	return ps.main(className="p-6")[
		ps.h1("Pandas adapter", className="text-2xl font-bold mb-4"),
		DataTable(rows=frame),
	]


app = ps.App(
	routes=[ps.Route("/", DataFrameGrid)],
	serializer=ps.Serializer([dataframe_records_adapter]),
)
