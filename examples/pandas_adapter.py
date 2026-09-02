import pandas as pd
import pulse as ps
from pulse.js.react import lazy
from pulse_pandas import PulsePandas


@ps.react_component(lazy(ps.Import("~/components/data-table", lazy=True)))
def DataTable(*, data: object, mean_revenue: object): ...


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
		ps.h1("Pandas plugin", className="text-2xl font-bold mb-4"),
		DataTable(data=frame, mean_revenue=frame["revenue"].mean()),
	]


app = ps.App(
	routes=[ps.Route("/", DataFrameGrid)],
	plugins=[PulsePandas()],
)
