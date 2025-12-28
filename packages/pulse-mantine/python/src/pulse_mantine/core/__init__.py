import pulse as ps

ps.Import(
	"",
	"@mantine/core/styles.css",
	kind="side_effect",
	before=["@mantine/dates/styles.css", "@mantine/charts/styles.css"],
)
