import { chunk } from "lodash-es";

export function DashboardChart() {
	const data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
	const chunked = chunk(data, 3);
	return (
		<div className="dashboard-chart">
			<h2>Dashboard Chart</h2>
			<p>Data chunks: {chunked.map((c) => `[${c.join(",")}]`).join(" ")}</p>
		</div>
	);
}
