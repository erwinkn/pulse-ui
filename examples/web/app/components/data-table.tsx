interface DataTableProps {
	data: { columns: string[]; rows: unknown[][] };
}

export default function DataTable({ data: { columns, rows } }: DataTableProps) {
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
					<tr key={String(row[0])}>
						{row.map((cell, columnIndex) => (
							<td key={columns[columnIndex]}>{String(cell ?? "")}</td>
						))}
					</tr>
				))}
			</tbody>
		</table>
	);
}
