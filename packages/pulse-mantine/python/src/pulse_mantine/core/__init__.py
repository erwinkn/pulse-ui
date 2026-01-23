import pulse as ps

from pulse_mantine.version import __version__

ps.require(
	{
		"pulse-mantine": __version__,
		"@mantine/core": ">=8.0.0",
		"@mantine/hooks": ">=8.0.0",
		"@mantine/notifications": ">=8.0.0",
	}
)

ps.Import(
	"@mantine/core/styles.css",
	side_effect=True,
	before=["@mantine/dates/styles.css", "@mantine/charts/styles.css"],
)
