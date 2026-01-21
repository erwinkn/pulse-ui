import pulse as ps

ps.Import(
	"@mantine/core/styles.css",
	side_effect=True,
	before=["@mantine/dates/styles.css", "@mantine/charts/styles.css"],
)
