interface DataTableProps {
	rows: Record<string, unknown>[];
}

export default function DataTable({ rows }: DataTableProps) {
	const columns = Object.keys(rows[0] ?? {});
	return (
		<table>
			<thead>
				<tr>
					{columns.map((column) => (
						<th key={column}>{column}</th>
					))}
				</tr>
			</thead>
			<tbody>
				{rows.map((row) => (
					<tr key={String(row.product)}>
						{columns.map((column) => (
							<td key={column}>{String(row[column] ?? "")}</td>
						))}
					</tr>
				))}
			</tbody>
		</table>
	);
}
